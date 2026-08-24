from typing import Optional

from composer import compose
from store import Store

MAX_ACTIONS_PER_TICK = 20
MAX_UNANSWERED_NUDGES = 3


def _resolve(store: Store, trigger: dict) -> tuple[Optional[dict], Optional[dict], Optional[dict]]:
    merchant = store.merchant(trigger.get("merchant_id")) if trigger.get("merchant_id") else None
    slug = None
    if merchant:
        slug = merchant.get("category_slug")
    if not slug:
        slug = (trigger.get("payload", {}) or {}).get("category")
    category = store.category(slug) if slug else None
    customer = store.customer(trigger.get("customer_id")) if trigger.get("customer_id") else None
    return category, merchant, customer


def _conversation_id(trigger: dict) -> str:
    return f"conv_{trigger.get('id', 'unknown')}"


def _template(trigger: dict, merchant: dict, customer: Optional[dict]) -> tuple[str, list[str]]:
    """First outbound in a session must ride an approved template (WhatsApp 24h rule)."""
    kind = trigger.get("kind", "generic")
    ident = (merchant or {}).get("identity", {}) or {}
    if customer:
        name = ((customer.get("identity", {}) or {}).get("name")) or "there"
        return f"merchant_{kind}_v1", [name, ident.get("name", ""), kind]
    name = ident.get("owner_first_name") or ident.get("name", "")
    return f"vera_{kind}_v1", [name, ident.get("name", ""), kind]


def select(store: Store, trigger_ids: list[str]) -> list[dict]:
    picked = []
    for tid in trigger_ids:
        trigger = store.trigger(tid)
        if not trigger:
            continue
        if trigger.get("suppression_key") in store.suppressed_keys:
            continue
        conv_id = _conversation_id(trigger)
        if conv_id in store.ended_conversations:
            continue
        conv = store.conversations.get(conv_id)
        if conv and conv.get("unanswered", 0) >= MAX_UNANSWERED_NUDGES:
            continue
        picked.append(trigger)

    picked.sort(key=lambda t: t.get("urgency", 0), reverse=True)

    # One action per merchant per tick (testing brief §14), plus the 20-action cap (§5).
    seen_merchants: set[str] = set()
    deduped: list[dict] = []
    for trigger in picked:
        mid = trigger.get("merchant_id")
        if not mid:
            # No merchant attached — skip rather than grouping all under None.
            continue
        if mid in seen_merchants:
            continue
        seen_merchants.add(mid)
        deduped.append(trigger)
        if len(deduped) >= MAX_ACTIONS_PER_TICK:
            break
    return deduped


def build_action(store: Store, trigger: dict) -> Optional[dict]:
    category, merchant, customer = _resolve(store, trigger)
    if not merchant:
        return None

    conv_id = _conversation_id(trigger)
    if conv_id in store.ended_conversations:
        return None

    result = compose(category, merchant, trigger, customer)
    template_name, template_params = _template(trigger, merchant, customer)

    return {
        "conversation_id": conv_id,
        "merchant_id": trigger.get("merchant_id"),
        "customer_id": trigger.get("customer_id"),
        "send_as": result["send_as"],
        "trigger_id": trigger.get("id"),
        "template_name": template_name,
        "template_params": template_params,
        "body": result["body"],
        "cta": result["cta"],
        "suppression_key": result["suppression_key"],
        "rationale": result["rationale"],
    }
