import conversation
from store import Store

_store = Store()


def respond(state: dict, merchant_message: str) -> dict:
    conv_id = state.get("conversation_id", "conv_offline")

    if state.get("merchant"):
        m = state["merchant"]
        _store.push("merchant", m.get("merchant_id", "m_offline"), 1, m)
    if state.get("category"):
        c = state["category"]
        _store.push("category", c.get("slug", "cat_offline"), 1, c)

    conv = _store.conversations.setdefault(conv_id, {"sent_bodies": [], "unanswered": 0})
    merchant_id = state.get("merchant_id") or (state.get("merchant") or {}).get("merchant_id")
    conv["merchant_id"] = merchant_id
    if "sent_bodies" in state:
        conv["sent_bodies"] = list(state["sent_bodies"])
    if "auto_streak" in state:
        _store.merchant_slot(merchant_id or conv_id)["auto_streak"] = state["auto_streak"]

    return conversation.respond(_store, conv_id, merchant_message)
