import re

CTA_VOCAB = {"open_ended", "binary_yes_no", "binary_confirm_cancel", "multi_choice_slot", "none"}

_URL_RE = re.compile(r"https?://|www\.|\b[\w-]+\.(?:com|in|org|net|co|io|app)\b", re.IGNORECASE)
_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")


def has_url(body: str) -> bool:
    return bool(_URL_RE.search(body or ""))


def valid_cta(cta: str) -> bool:
    return cta in CTA_VOCAB


def language_ok(body: str, merchant: dict | None) -> bool:
    langs = ((merchant or {}).get("identity", {}) or {}).get("languages", []) or []
    if "hi" in langs:
        return True
    return not _DEVANAGARI_RE.search(body or "")


def is_repeat(store, conversation_id: str, body: str) -> bool:
    conv = store.conversations.get(conversation_id)
    if not conv:
        return False
    return (body or "").strip() in conv.get("sent_bodies", [])


def validate(action: dict, merchant: dict | None, store) -> list[str]:
    body = action.get("body", "")
    problems: list[str] = []
    if not body.strip():
        problems.append("empty body")
    if has_url(body):
        problems.append("body contains a URL or link; remove it")
    if not valid_cta(action.get("cta", "")):
        problems.append("cta not in allowed vocabulary")
    if not language_ok(body, merchant):
        problems.append("message uses Hindi script but merchant is English-only")
    if is_repeat(store, action.get("conversation_id", ""), body):
        problems.append("body repeats a message already sent in this conversation")
    return problems
