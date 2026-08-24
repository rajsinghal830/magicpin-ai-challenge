import json
import logging
import re
import time
from typing import Any, Optional

from google import genai
from google.genai import types

import config
import validators
from fallback import compose_fallback
from prompts.system import build_system
from prompts.variants import variant_for

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def _resolve_digest_item(category: Optional[dict], item_id: Optional[str]) -> Optional[dict]:
    if not category or not item_id:
        return None
    for item in category.get("digest", []) or []:
        if item.get("id") == item_id:
            return item
    return None


def _facts_block(category, merchant, trigger, customer) -> str:
    lines: list[str] = []
    tpayload = (trigger or {}).get("payload", {}) or {}

    item = _resolve_digest_item(category, tpayload.get("top_item_id"))
    if item:
        lines.append("Digest item:")
        for k in ("title", "summary", "source", "actionable"):
            if item.get(k):
                lines.append(f"  {k}: {item[k]}")

    if tpayload:
        lines.append(f"Trigger payload: {json.dumps(tpayload, ensure_ascii=False)}")

    if merchant:
        perf = merchant.get("performance", {}) or {}
        if perf:
            lines.append(f"Performance: {json.dumps(perf, ensure_ascii=False)}")
        offers = [o for o in merchant.get("offers", []) or [] if o.get("status") == "active"]
        if offers:
            lines.append("Active offers: " + json.dumps(offers, ensure_ascii=False))
        if merchant.get("customer_aggregate"):
            lines.append("Customer aggregate: " + json.dumps(merchant["customer_aggregate"], ensure_ascii=False))
        if merchant.get("review_themes"):
            lines.append("Review themes: " + json.dumps(merchant["review_themes"], ensure_ascii=False))
        # Derived signals (stale_posts, ctr_below_peer_median, dormant, etc.)
        if merchant.get("signals"):
            lines.append("Merchant signals: " + json.dumps(merchant["signals"], ensure_ascii=False))
        # Last few Vera turns so the LLM avoids repeating the same angle
        history = merchant.get("conversation_history", {}) or {}
        recent_turns = (history.get("turns") or history.get("messages") or [])[-4:]
        if recent_turns:
            lines.append("Recent conversation history (last 4 turns): " + json.dumps(recent_turns, ensure_ascii=False))

    if category:
        if category.get("offer_catalog"):
            lines.append("Offer catalog: " + json.dumps(category["offer_catalog"], ensure_ascii=False))
        if category.get("peer_stats"):
            lines.append("Peer stats: " + json.dumps(category["peer_stats"], ensure_ascii=False))
        # Seasonal beats give timing-specific hooks (e.g. "exam-stress bruxism Nov-Feb")
        if category.get("seasonal_beats"):
            lines.append("Seasonal beats: " + json.dumps(category["seasonal_beats"], ensure_ascii=False))
        # Trend signals give search-volume / demand hooks
        if category.get("trend_signals"):
            lines.append("Trend signals: " + json.dumps(category["trend_signals"], ensure_ascii=False))
        # Content the merchant can reshare with their customers
        if category.get("patient_content_library"):
            lines.append("Reshare-able content library: " + json.dumps(category["patient_content_library"], ensure_ascii=False))

    if customer:
        lines.append("Customer: " + json.dumps({
            "identity": customer.get("identity", {}),
            "relationship": customer.get("relationship", {}),
            "state": customer.get("state"),
            "preferences": customer.get("preferences", {}),
        }, ensure_ascii=False))

    return "\n".join(lines)


def _user_prompt(category, merchant, trigger, customer) -> tuple[str, dict]:
    kind = (trigger or {}).get("kind", "")
    variant = variant_for(kind)
    facts = _facts_block(category, merchant, trigger, customer)
    prompt = f"""Trigger kind: {kind}
Framing: {variant['frame']}

FACTS (use only these):
{facts}

Write one WhatsApp message. Respond as JSON only:
{{"body": "<message text, no URLs>", "cta": "<one of: open_ended, binary_yes_no, binary_confirm_cancel, multi_choice_slot, none>", "rationale": "<why this message, for the judge>"}}
Suggested CTA if unsure: {variant['cta']}."""
    return prompt, variant


def _is_retryable(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    s = str(exc)
    return code in (429, 503) or "RESOURCE_EXHAUSTED" in s or "UNAVAILABLE" in s


def _retry_delay(exc: Exception, default: float) -> float:
    m = re.search(r"retry in ([\d.]+)s", str(exc))
    return float(m.group(1)) + 1 if m else default


def _call_model(system: str, prompt: str, model: str, attempts: int = 2, max_sleep: float = 4) -> str:
    last: Optional[Exception] = None
    for i in range(attempts):
        try:
            resp = _get_client().models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0,
                    response_mime_type="application/json",
                ),
            )
            return resp.text or ""
        except Exception as exc:
            last = exc
            if _is_retryable(exc) and i < attempts - 1:
                time.sleep(min(_retry_delay(exc, 2 * (2 ** i)), max_sleep))
                continue
            raise
    raise last  # type: ignore[misc]


def _parse(raw: str) -> dict:
    raw = raw.strip()
    # Try a direct parse first — avoids choking on `}` inside the message body.
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Fall back: extract the outermost JSON object.
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        return json.loads(raw[start: end + 1])
    raise ValueError(f"No JSON object found in model output: {raw[:200]!r}")


def _generate(system: str, prompt: str, attempts: int = 2) -> dict:
    try:
        raw = _call_model(system, prompt, config.MODEL, attempts=attempts)
    except Exception:
        raw = _call_model(system, prompt, config.FALLBACK_MODEL, attempts=attempts)
    return _parse(raw)


def run_model(system: str, prompt: str, attempts: int = 2) -> dict:
    """attempts=1 on the reply path: the judge cuts at 30s and a retry sleep plus a
    fallback-model call can stack past it. Failing fast into the rule composer is cheaper."""
    return _generate(system, prompt, attempts=attempts)


def _content_problems(data: dict, merchant) -> list[str]:
    body, cta = data.get("body", ""), data.get("cta", "")
    problems = []
    if not (body or "").strip():
        problems.append("empty body")
    if validators.has_url(body):
        problems.append("remove the URL or link from the body")
    if not validators.valid_cta(cta):
        problems.append("use a cta from the allowed vocabulary")
    if not validators.language_ok(body, merchant):
        problems.append("do not use Hindi script; this merchant is English-only")
    return problems


def compose(category, merchant, trigger, customer=None) -> dict[str, Any]:
    system = build_system(category, merchant)
    prompt, variant = _user_prompt(category, merchant, trigger, customer)

    try:
        data = _generate(system, prompt)
        problems = _content_problems(data, merchant)
        if problems:
            fix = prompt + "\n\nYour previous draft had these problems: " + "; ".join(problems) + ".\nRewrite the message fixing them. JSON only."
            data = _generate(system, fix)
    except Exception as exc:
        # Quota, timeout, unparseable JSON — degrade to the rule composer rather than
        # dropping the action. A grounded plain message outscores no message at all.
        logging.warning("compose falling back for trigger %s: %s", (trigger or {}).get("id"), exc)
        return compose_fallback(category, merchant, trigger, customer)

    if not (data.get("body") or "").strip():
        return compose_fallback(category, merchant, trigger, customer)

    send_as = "merchant_on_behalf" if (trigger or {}).get("scope") == "customer" else "vera"
    return {
        "body": data.get("body", "").strip(),
        "cta": data.get("cta") or variant["cta"],
        "send_as": send_as,
        "suppression_key": (trigger or {}).get("suppression_key", ""),
        "rationale": data.get("rationale", ""),
    }
