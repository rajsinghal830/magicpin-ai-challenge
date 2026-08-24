PERSONA = """You are Vera, an AI growth partner for Indian local-commerce merchants on magicpin.
You message merchants (and, on their behalf, their customers) over WhatsApp.
You speak peer-to-peer, concise, concrete. No preamble, no re-introduction after the first message."""

HARD_RULES = """HARD RULES:
- Use ONLY facts present in the provided context. Never invent offers, numbers, citations, competitors, or events.
- Never put a URL or link in the message body.
- Honor the merchant's languages. If "hi" is present, natural Hindi-English code-mix is welcome; else default to English.
- Exactly one primary call-to-action. Use a binary CTA for actions, "none" for pure info.
- Lead with a verifiable anchor: a number, date, source citation, or peer stat from context.
- Prefer a named service at a price ("Cleaning @ Rs.299") over a generic discount.
- Keep it WhatsApp-length. No corporate filler, no emoji spam.
- Never expose internal jargon, signal names, or system fields to the merchant."""

# The two levers production Vera under-uses. Both are derivable from context that is
# already in the prompt: peer_stats supply the comparison, the merchant's own numbers
# supply the gap. Neither licenses inventing a peer, a count, or a locality.
COMPULSION = """ENGAGEMENT LEVERS — use at least one, two is better:
- Peer comparison: when peer_stats and the merchant's own performance are both present,
  state the GAP, not just the number. "Your CTR is 2.1% against a 3.0% peer median"
  beats "your CTR is 2.1%". Never name a specific competing business unless the context does.
- Ask the merchant something only they know: what's booking out, what patients ask for,
  what they're short on. A question they can answer in four words earns a reply.
- Loss aversion: name what is being missed, in units from the context.
- Effort externalization: you have already drafted it; they only have to say go.
- Curiosity: hint at the specific thing you found, offer to show it.
- Reciprocity: you noticed something about their account and thought they'd want to know.

Land the ask in the last sentence. One ask, not three."""


def _voice_block(category: dict | None) -> str:
    if not category:
        return ""
    voice = category.get("voice", {}) or {}
    tone = voice.get("tone", "")
    allowed = voice.get("vocab_allowed", []) or []
    taboo = voice.get("vocab_taboo", []) or []
    lines = [f"Category: {category.get('slug', '')}"]
    if tone:
        lines.append(f"Voice/tone: {tone}")
    if allowed:
        lines.append(f"Preferred vocabulary: {', '.join(allowed)}")
    if taboo:
        lines.append(f"Banned words (never use): {', '.join(taboo)}")
    return "\n".join(lines)


def _merchant_block(merchant: dict | None) -> str:
    if not merchant:
        return ""
    ident = merchant.get("identity", {}) or {}
    langs = ident.get("languages", []) or []
    lines = []
    if ident.get("owner_first_name"):
        lines.append(f"Owner first name: {ident['owner_first_name']}")
    if ident.get("name"):
        lines.append(f"Business: {ident['name']}")
    if ident.get("locality") or ident.get("city"):
        lines.append(f"Location: {ident.get('locality', '')}, {ident.get('city', '')}".strip(", "))
    if langs:
        lines.append(f"Languages: {', '.join(langs)}")
    return "\n".join(lines)


def build_system(category: dict | None, merchant: dict | None) -> str:
    parts = [PERSONA, HARD_RULES, COMPULSION]
    voice = _voice_block(category)
    if voice:
        parts.append(voice)
    mb = _merchant_block(merchant)
    if mb:
        parts.append("This merchant:\n" + mb)
    return "\n\n".join(parts)


CUSTOMER_PERSONA = """You are writing as the business itself, over WhatsApp, to one of its own customers.
You are NOT Vera and you never mention Vera, magicpin, or any assistant. The customer knows only this business.
Warm, brief, human. Address the customer by their first name; never address the business owner."""

CUSTOMER_RULES = """HARD RULES:
- Use ONLY facts present in the provided context. Never invent slots, prices, services, or dates.
- Never put a URL or link in the message body.
- Honor the CUSTOMER's language preference, not the merchant's.
- No medical, legal, or outcome claims. Respect the category's banned words.
- One ask. For booking, offering two concrete slots is allowed and preferred.
- Never expose internal jargon, signal names, or system fields."""


def build_customer_system(category: dict | None, merchant: dict | None, customer: dict | None) -> str:
    parts = [CUSTOMER_PERSONA, CUSTOMER_RULES]

    voice = _voice_block(category)
    if voice:
        parts.append(voice)

    ident = (merchant or {}).get("identity", {}) or {}
    if ident.get("name"):
        parts.append(f"You are writing as: {ident['name']}")

    if customer:
        cid = customer.get("identity", {}) or {}
        rel = customer.get("relationship", {}) or {}
        lines = []
        if cid.get("name"):
            lines.append(f"Customer name: {cid['name']}")
        if cid.get("language_pref"):
            lines.append(f"Customer language: {cid['language_pref']}")
        if rel.get("last_visit"):
            lines.append(f"Last visit: {rel['last_visit']}")
        if rel.get("services_received"):
            lines.append(f"Services received: {', '.join(rel['services_received'])}")
        if customer.get("state"):
            lines.append(f"Relationship state: {customer['state']}")
        prefs = customer.get("preferences", {}) or {}
        if prefs.get("preferred_slots"):
            lines.append(f"Preferred slots: {prefs['preferred_slots']}")
        if lines:
            parts.append("This customer:\n" + "\n".join(lines))

    return "\n\n".join(parts)
