import logging
import re

import validators
from composer import run_model
from fallback import customer_reply_fallback, reply_fallback
from prompts.system import build_customer_system, build_system
from store import Store


_AUTO_REPLY = [
    "thank you for contacting",
    "will respond shortly",
    "will get back to you",
    "out of office",
    "away from",
    "currently unavailable",
    "auto-reply",
    "automated response",
    "automated assistant",
    "team tak pahuncha",
    "jaankari ke liye",
    # Additional missed patterns
    "i am currently away",
    "this is an automated",
    "kindly be informed",
    "please note that",
    "business hours",
    "during our working hours",
    "our team will",
    "we will get back",
    "your message has been received",
]


_OPTOUT = [
    "stop messaging",
    "stop sending",
    "not interested",
    "unsubscribe",
    "leave me alone",
    "don't message",
    "do not message",
    "this is useless",
    "useless spam",
    "why are you bothering",
]


_INTENT = [
    "let's do it",
    "lets do it",
    "let's go",
    "go ahead",
    "sounds good",
    "ok do it",
    "yes please",
    "let's start",
    "i'm in",
    "sign me up",
    "judrna hai",
    "join karna hai",
    # Additional Hindi/Hinglish commitment phrases
    "kar do",
    "abhi karo",
    "haan karo",
    "start karo",
    "chalu karo",
    "chalao",
    "approve",
    "approved",
    "done deal",
    "shuruaat karo",
    "shuruaat kar",
    "haan bilkul",
    "bilkul karo",
    "please proceed",
    "go for it",
    "do it",
    "start it",
]


_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")

_HINGLISH = [
    " hai",
    " hain",
    " kar ",
    " kya ",
    " nahi",
    " aap ",
    " mujhe ",
    " karo",
    " chahiye",
    " theek",
    " accha",
    " bhej",
    " batao",
]


def _hit(text: str, phrases: list[str]) -> bool:
    t = text.lower()
    return any(p in t for p in phrases)


def _normalize(message: str) -> str:
    return re.sub(r"\s+", " ", (message or "").strip().lower())


def is_auto_reply(message: str) -> bool:
    return _hit(message, _AUTO_REPLY)


def is_optout(message: str) -> bool:
    return _hit(message, _OPTOUT)


def is_intent_transition(message: str) -> bool:
    return _hit(message, _INTENT)


def detect_language(message: str) -> str:
    """What the merchant used on THIS turn, regardless of their profile default."""
    if _DEVANAGARI_RE.search(message or ""):
        return "hi-script"

    padded = f" {_normalize(message)} "

    if any(w in padded for w in _HINGLISH):
        return "hi-en mix"

    return "en"


def _merchant_key(conv_id: str, conv: dict) -> str:
    return conv.get("merchant_id") or conv_id


def _record_inbound(store: Store, key: str, message: str) -> tuple[bool, int]:
    """Returns (is_auto_reply, streak). Verbatim repeat 3+ times counts as auto-reply."""
    slot = store.merchant_slot(key)
    norm = _normalize(message)

    slot["inbound"].append(norm)
    verbatim_count = slot["inbound"].count(norm)

    auto = is_auto_reply(message) or verbatim_count >= 3

    if not auto:
        slot["auto_streak"] = 0
    else:
        # A verbatim repeat is itself proof of a machine.
        slot["auto_streak"] = max(slot["auto_streak"] + 1, verbatim_count)

    return auto, slot["auto_streak"]


def _reply_system(store: Store, conv: dict, turn_language: str) -> str:
    merchant = (
        store.merchant(conv.get("merchant_id"))
        if conv.get("merchant_id")
        else None
    )

    category = None

    if merchant and merchant.get("category_slug"):
        category = store.category(merchant["category_slug"])

    system = build_system(category, merchant)

    if turn_language == "en":
        system += "\n\nThis turn: the merchant wrote in English. Reply in English."
    elif turn_language == "hi-script":
        system += (
            "\n\nThis turn: the merchant wrote in Devanagari Hindi. "
            "Reply in Hindi — Devanagari script is fine, or Hindi-English mix in Latin script."
        )
    else:
        system += (
            "\n\nThis turn: the merchant wrote Hindi-English mix. "
            "Mirror that code-mix in Latin script."
        )

    return system


def _reply_problems(
    data: dict,
    merchant,
    sent: list[str],
    turn_language: str,
) -> list[str]:
    body = (data.get("body") or "").strip()
    problems: list[str] = []

    if not body:
        problems.append("empty body")

    if not validators.valid_cta(data.get("cta", "")):
        problems.append("use a cta from the allowed vocabulary")

    if turn_language == "en" and _DEVANAGARI_RE.search(body):
        problems.append("the merchant wrote English this turn; reply in English")

    if not validators.language_ok(body, merchant):
        problems.append("do not use Hindi script; this merchant is English-only")

    if body and body in sent:
        problems.append(
            "this repeats a message you already sent; write something new"
        )

    return problems


def _generate_reply(
    store: Store,
    conv: dict,
    message: str,
    frame: str,
    turn_language: str,
) -> dict:
    system = _reply_system(store, conv, turn_language)

    merchant = (
        store.merchant(conv.get("merchant_id"))
        if conv.get("merchant_id")
        else None
    )

    sent = conv.get("sent_bodies", [])

    prompt = f"""The merchant just replied: "{message}"

{frame}

Do not repeat any message you already sent: {sent}

Respond as JSON only:
{{"body": "<reply text>", "cta": "<open_ended, binary_yes_no, binary_confirm_cancel, multi_choice_slot, or none>", "rationale": "<why, for the judge>"}}"""

    result = run_model(system, prompt, attempts=1)

    problems = _reply_problems(
        result,
        merchant,
        sent,
        turn_language,
    )

    if problems:
        fix = (
            prompt
            + "\n\nYour previous draft had these problems: "
            + "; ".join(problems)
            + ".\nRewrite fixing them. JSON only."
        )

        result = run_model(
            system,
            fix,
            attempts=1,
        )

    return result


def _respond_as_merchant_to_customer(
    store: Store,
    conv: dict,
    message: str,
) -> dict:
    """
    The customer replied to a message we sent on the merchant's behalf.

    Nothing about Vera's merchant-facing voice applies here: the customer
    has never heard of Vera, and the sender is the business.
    """

    merchant = (
        store.merchant(conv.get("merchant_id"))
        if conv.get("merchant_id")
        else None
    )

    customer = (
        store.customer(conv.get("customer_id"))
        if conv.get("customer_id")
        else None
    )

    category = (
        store.category(merchant["category_slug"])
        if merchant and merchant.get("category_slug")
        else None
    )

    sent = conv.get("sent_bodies", [])

    system = build_customer_system(
        category,
        merchant,
        customer,
    )

    prompt = f"""The customer just replied: "{message}"

Reply as the business. If they accepted a slot, confirm it back exactly and say what to bring
or expect. If they declined, offer to reschedule without pressure. If they asked about price or
service, answer only from the context. Keep it short.

Do not repeat any message already sent: {sent}

Respond as JSON only:
{{"body": "<reply text>", "cta": "<open_ended, binary_yes_no, binary_confirm_cancel, multi_choice_slot, or none>", "rationale": "<why, for the judge>"}}"""

    try:
        result = run_model(
            system,
            prompt,
            attempts=1,
        )

        body = (result.get("body") or "").strip()

        if (
            not body
            or not validators.valid_cta(result.get("cta", ""))
            or validators.has_url(body)
            or body in sent
        ):
            raise ValueError("customer reply failed validation")

        return {
            "action": "send",
            "body": body,
            "cta": result["cta"],
            "rationale": result.get("rationale", ""),
        }

    except Exception as exc:
        logging.warning(
            "customer reply falling back: %s",
            exc,
        )

        return customer_reply_fallback(
            merchant,
            customer,
            message,
            sent,
        )


def respond(
    store: Store,
    conv_id: str,
    message: str,
    from_role: str = "merchant",
) -> dict:

    conv = store.conversations.setdefault(
        conv_id,
        {
            "sent_bodies": [],
            "unanswered": 0,
        },
    )

    conv["unanswered"] = 0

    key = _merchant_key(
        conv_id,
        conv,
    )

    # Conversation already closed.
    if conv_id in store.ended_conversations:
        return {
            "action": "end",
            "rationale": "Conversation already closed.",
        }

    # ---------------------------------------------------------
    # CUSTOMER REPLY
    # ---------------------------------------------------------
    if from_role == "customer":

        if is_optout(message):
            store.ended_conversations.add(conv_id)

            return {
                "action": "end",
                "rationale": "Customer asked to stop; closing and honoring the opt-out.",
            }

        out = _respond_as_merchant_to_customer(
            store,
            conv,
            message,
        )

        conv["sent_bodies"].append(
            out["body"]
        )

        return out

    # ---------------------------------------------------------
    # MERCHANT OPT-OUT
    # ---------------------------------------------------------
    if is_optout(message):

        store.ended_conversations.add(conv_id)

        store.merchant_slot(key)["auto_streak"] = 0

        return {
            "action": "end",
            "rationale": (
                "Merchant opted out or expressed frustration; "
                "closing and suppressing further sends."
            ),
        }

    # ---------------------------------------------------------
    # AUTO-REPLY DETECTION
    # ---------------------------------------------------------
    auto, streak = _record_inbound(
        store,
        key,
        message,
    )

    if auto:

        if streak >= 3:

            store.ended_conversations.add(conv_id)

            return {
                "action": "end",
                "rationale": (
                    f"Auto-reply {streak}x from this merchant; "
                    "no human on the line. Closing rather than burning turns."
                ),
            }

        if streak == 2:

            return {
                "action": "wait",
                "wait_seconds": 86400,
                "rationale": (
                    "Same auto-reply twice; owner not at the phone. "
                    "Waiting 24h before one more attempt."
                ),
            }

        body = (
            "Looks like an auto-reply. When the owner sees this, "
            "just reply YES and I'll pick up where we left off."
        )

        conv["sent_bodies"].append(body)

        return {
            "action": "send",
            "body": body,
            "cta": "binary_yes_no",
            "rationale": (
                "Detected WhatsApp Business auto-reply; "
                "one plain prompt for the owner, no model call spent."
            ),
        }

    # ---------------------------------------------------------
    # NORMAL MERCHANT REPLY
    # ---------------------------------------------------------
    turn_language = detect_language(message)

    is_intent = is_intent_transition(message)

    if is_intent:
        frame = (
            "The merchant just committed. Stop qualifying. "
            "Switch to action: state the concrete next step you are "
            "taking now, with measurable scope, and a single confirm CTA. "
            "Do not ask another qualifying question."
        )
    else:
        frame = (
            "Reply helpfully and specifically, tied to the original trigger. "
            "If the ask is outside your scope (taxes, filing, unrelated), "
            "decline politely and redirect to the trigger. Keep one primary CTA."
        )

    merchant = (
        store.merchant(conv.get("merchant_id"))
        if conv.get("merchant_id")
        else None
    )

    category = (
        store.category(merchant["category_slug"])
        if merchant and merchant.get("category_slug")
        else None
    )

    # ---------------------------------------------------------
    # BOTH INTENT AND NORMAL REPLIES: try LLM first (attempts=1
    # keeps us well within the 30s judge budget), fall back to
    # the rule composer only on failure.
    # ---------------------------------------------------------
    try:

        result = _generate_reply(
            store,
            conv,
            message,
            frame,
            turn_language,
        )

        body = (result.get("body") or "").strip()

        if not body:
            raise ValueError(
                "model returned an empty body"
            )

        out = {
            "action": "send",
            "body": body,
            "cta": result.get(
                "cta",
                "binary_confirm_cancel" if is_intent else "open_ended",
            ),
            "rationale": result.get(
                "rationale",
                "",
            ),
        }

    except Exception as exc:

        logging.warning(
            "reply falling back for %s: %s",
            conv_id,
            exc,
        )

        out = reply_fallback(
            merchant,
            category,
            message,
            conv.get("sent_bodies", []),
            intent=is_intent,
        )

    # ---------------------------------------------------------
    # SAVE RESPONSE
    # ---------------------------------------------------------
    conv["sent_bodies"].append(
        out["body"]
    )

    return out