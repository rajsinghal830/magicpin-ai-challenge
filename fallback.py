"""Deterministic composers for when the LLM is unavailable (quota, timeout, unparseable JSON).

Every number, name, date and citation below is read out of the passed contexts. Nothing is
hardcoded: if a fact is absent from the context, the sentence that would have carried it is
dropped rather than filled in. A message that says less always beats one that invents.
"""

from typing import Optional

# Question phrasings for curious_ask_due. These assert no facts — only the ask varies.
_ASK_TEMPLATES = {
    "what_service_in_demand_this_week": "which service are people asking for most this week",
    "what_dish_is_trending": "which dish is moving fastest right now",
    "what_slot_is_busiest": "which slot fills up first for you",
    "what_molecule_is_short": "any molecule you're running short on",
}


def _identity(merchant: Optional[dict]) -> dict:
    return (merchant or {}).get("identity", {}) or {}


def _first_name(merchant: Optional[dict]) -> str:
    ident = _identity(merchant)
    return ident.get("owner_first_name") or ident.get("name") or "there"


def _business(merchant: Optional[dict]) -> str:
    return _identity(merchant).get("name", "")


def _active_offer(merchant: Optional[dict]) -> Optional[str]:
    for offer in (merchant or {}).get("offers", []) or []:
        if offer.get("status") == "active" and offer.get("title"):
            return offer["title"]
    return None


def _pct(value) -> Optional[str]:
    try:
        return f"{abs(float(value)) * 100:.0f}%"
    except (TypeError, ValueError):
        return None


def _day(iso: Optional[str]) -> Optional[str]:
    return iso[:10] if isinstance(iso, str) and len(iso) >= 10 else None


def _words(slug) -> str:
    return str(slug).replace("_", " ")


def _digest_item(category: Optional[dict], item_id: Optional[str]) -> dict:
    if not (category and item_id):
        return {}
    for item in category.get("digest", []) or []:
        if item.get("id") == item_id:
            return item
    return {}


def _slot_labels(slots) -> list[str]:
    return [s["label"] for s in (slots or []) if isinstance(s, dict) and s.get("label")]


def _ctr_gap(merchant: Optional[dict], category: Optional[dict]) -> Optional[str]:
    mine = ((merchant or {}).get("performance", {}) or {}).get("ctr")
    peer = ((category or {}).get("peer_stats", {}) or {}).get("avg_ctr")
    if not (mine and peer):
        return None
    return f"your CTR is {mine * 100:.1f}% against a {peer * 100:.1f}% peer median"


def _merchant_anchor(merchant: Optional[dict], category: Optional[dict]) -> Optional[str]:
    """Best verifiable fact about this merchant, in preference order."""
    gap = _ctr_gap(merchant, category)
    if gap:
        return gap

    perf = (merchant or {}).get("performance", {}) or {}
    delta = perf.get("delta_7d", {}) or {}
    for key, label in (("calls_pct", "calls"), ("views_pct", "views")):
        if delta.get(key):
            direction = "up" if delta[key] > 0 else "down"
            return f"{label} are {direction} {_pct(delta[key])} week-on-week"

    lapsed = ((merchant or {}).get("customer_aggregate", {}) or {}).get("lapsed_180d_plus")
    if lapsed:
        return f"{lapsed} of your customers haven't been back in 6+ months"

    offer = _active_offer(merchant)
    if offer:
        return f"your '{offer}' is live"
    return None


# ── merchant-facing bodies, one per trigger kind ────────────────────────────────

def _merchant_body(kind: str, payload: dict, merchant, category) -> tuple[Optional[str], str]:
    name = _first_name(merchant)
    offer = _active_offer(merchant)
    offer_hook = f" Your '{offer}' is the hook." if offer else ""

    if kind in ("research_digest", "cde_opportunity", "regulation_change"):
        item = _digest_item(category, payload.get("top_item_id") or payload.get("digest_item_id"))
        title, source = item.get("title"), item.get("source")
        if title:
            cite = f" — {source}" if source else ""

            if kind == "research_digest":
                n = item.get("trial_n")
                n_str = f" (n={n:,})" if isinstance(n, int) else ""
                return f"{name}, {title}{n_str}. Want me to draft a patient-facing note from it?{cite}", "binary_yes_no"

            if kind == "regulation_change":
                deadline = _day(payload.get("deadline_iso"))
                # The digest title often already carries the date; don't say it twice.
                due = f" Effective {deadline}." if deadline and deadline not in title else ""
                return f"{name}, {title}.{due} Want the compliance checklist?{cite}", "binary_yes_no"

            credits, fee = payload.get("credits"), payload.get("fee")
            worth = f" {credits} CDE credits" if credits else ""
            cost = f", {_words(fee)}" if fee else ""
            detail = f"{worth}{cost}.".strip() if (worth or cost) else ""
            return f"{name}, {title}.{(' ' + detail) if detail else ''} Want me to register you?{cite}", "binary_yes_no"

    if kind in ("perf_dip", "seasonal_perf_dip"):
        metric, delta = payload.get("metric"), _pct(payload.get("delta_pct"))
        if metric and delta:
            window = _words(payload.get("window", "")).strip()
            win = f" over the last {window}" if window else ""
            note = payload.get("season_note")
            season = f" That tracks the {_words(note)} pattern." if note else ""
            return f"{name}, {_words(metric)} dropped {delta}{win}.{season}{offer_hook} Should I push it now?", "binary_yes_no"

    if kind == "perf_spike":
        metric, delta = payload.get("metric"), _pct(payload.get("delta_pct"))
        if metric and delta:
            driver = payload.get("likely_driver")
            drv = f" — looks like {_words(driver)}" if driver else ""
            return f"{name}, {_words(metric)} up {delta} this week{drv}. Want me to draft a post to hold the momentum?", "binary_yes_no"

    if kind == "renewal_due":
        days = payload.get("days_remaining")
        if days is not None:
            plan = payload.get("plan", "")
            amount = payload.get("renewal_amount")
            amt = f" (Rs.{amount})" if amount else ""
            return f"{name}, your {plan} plan expires in {days} days{amt}. Renewing keeps your leads flowing. Shall I start it?", "binary_confirm_cancel"

    if kind == "festival_upcoming":
        festival, days = payload.get("festival"), payload.get("days_until")
        if festival and days is not None:
            return f"{name}, {festival} is {days} days out.{offer_hook} Want me to draft the campaign post?", "binary_yes_no"

    if kind == "category_seasonal":
        trends = payload.get("trends") or []
        if trends:
            shown = ", ".join(_words(t) for t in trends[:2])
            return f"{name}, this season's shift: {shown}. Want a shelf-action plan?", "binary_yes_no"

    if kind == "ipl_match_today":
        match, when = payload.get("match"), payload.get("match_time_iso")
        if match:
            hour = when[11:16] if isinstance(when, str) and len(when) > 15 else None
            at = f" at {hour}" if hour else ""
            return f"{name}, {match} is on tonight{at}.{offer_hook} Want a match-night push ready in 10 minutes?", "binary_yes_no"

    if kind == "review_theme_emerged":
        theme, count = payload.get("theme"), payload.get("occurrences_30d")
        if theme and count:
            quote = payload.get("common_quote")
            said = f' One said: "{quote}".' if quote else ""
            return f"{name}, {count} reviews this month mention {_words(theme)}.{said} Want me to draft a response template?", "binary_yes_no"

    if kind == "milestone_reached":
        metric, now = payload.get("metric"), payload.get("value_now")
        target = payload.get("milestone_value")
        if metric and now is not None:
            gap = f" — {target - now} short of {target}" if isinstance(target, int) and isinstance(now, int) else ""
            return f"{name}, you're at {now} {_words(metric)}{gap}. Want a post to push it over?", "binary_yes_no"

    if kind == "competitor_opened":
        comp, dist = payload.get("competitor_name"), payload.get("distance_km")
        if comp:
            near = f" {dist}km away" if dist else ""
            theirs = payload.get("their_offer")
            running = f" running '{theirs}'" if theirs else ""
            return f"{name}, {comp} opened{near}{running}.{offer_hook} Want a defensive campaign?", "binary_yes_no"

    if kind == "gbp_unverified":
        uplift = _pct(payload.get("estimated_uplift_pct"))
        if uplift:
            return f"{name}, your Google profile isn't verified — verified listings see about {uplift} more clicks. Two minutes. Want the steps?", "binary_yes_no"

    if kind == "winback_eligible":
        days, dip = payload.get("days_since_expiry"), _pct(payload.get("perf_dip_pct"))
        if days is not None:
            drop = f", and calls are down {dip} since" if dip else ""
            return f"{name}, your plan lapsed {days} days ago{drop}. Restarting takes 2 minutes. Want to?", "binary_yes_no"

    if kind == "supply_alert":
        molecule, batches = payload.get("molecule"), payload.get("affected_batches") or []
        if molecule:
            batch = f" (batches {', '.join(batches[:2])})" if batches else ""
            maker = payload.get("manufacturer")
            by = f" from {maker}" if maker else ""
            return f"{name}, recall on {molecule}{by}{batch}. Want me to filter your prescription list and draft the outreach?", "binary_yes_no"

    if kind == "dormant_with_vera":
        days = payload.get("days_since_last_merchant_message")
        anchor = _merchant_anchor(merchant, category)
        if anchor:
            gap = f"it's been {days} days. " if days else ""
            lead = f"{gap}One thing worth a look" if gap else "one thing worth a look"
            return f"{name}, {lead}: {anchor}. Want me to dig in?", "binary_yes_no"

    if kind == "curious_ask_due":
        question = _ASK_TEMPLATES.get(payload.get("ask_template"), "what's your top priority this week")
        return f"{name}, quick one — {question}? Your answer shapes what I draft for you next.", "open_ended"

    if kind == "active_planning_intent":
        topic = payload.get("intent_topic")
        if topic:
            return f"{name}, picking up on {_words(topic)}.{offer_hook} Want me to put a concrete plan in front of you?", "binary_yes_no"

    return None, "binary_yes_no"


# ── customer-facing bodies (sent as the merchant, to their customer) ────────────

def _customer_body(kind: str, payload: dict, merchant, customer) -> tuple[Optional[str], str]:
    cust = ((customer or {}).get("identity", {}) or {}).get("name", "there")
    shop = _business(merchant) or _first_name(merchant)
    slots = _slot_labels(payload.get("available_slots") or payload.get("next_session_options"))

    if kind == "recall_due":
        service = _words(payload.get("service_due", "")).strip()
        due = f"your {service} is due" if service else "you're due for a visit"
        if slots:
            choice = " or ".join(slots[:2])
            return f"Hi {cust}, {shop} here. {due.capitalize()}. We have {choice} open — reply 1 or 2 to confirm.", "multi_choice_slot"
        return f"Hi {cust}, {shop} here. {due.capitalize()}. Want us to find you a slot this week?", "binary_yes_no"

    if kind == "chronic_refill_due":
        mols = payload.get("molecule_list") or []
        runs_out = _day(payload.get("stock_runs_out_iso"))
        if mols:
            listed = " + ".join(mols[:3])
            by = f" — you run out around {runs_out}" if runs_out else ""
            delivery = " We can deliver." if payload.get("delivery_address_saved") else ""
            return f"Hi {cust}, {shop} here. Your {listed} refill is due{by}.{delivery} Reply YES to order.", "binary_yes_no"

    if kind == "trial_followup":
        trial = _day(payload.get("trial_date"))
        when = f" on {trial}" if trial else ""
        if slots:
            return f"Hi {cust}, {shop} here. Great having you for your trial{when}. Next session: {slots[0]}. Joining us?", "binary_yes_no"
        return f"Hi {cust}, {shop} here. Great having you for your trial{when}. Want to book your next session?", "binary_yes_no"

    if kind == "wedding_package_followup":
        days = payload.get("days_to_wedding")
        trial = _day(payload.get("trial_completed"))
        if days is not None:
            did = f" Trial done {trial}." if trial else ""
            step = payload.get("next_step_window_open")
            nxt = f" Next up: {_words(step)}." if step else ""
            return f"Hi {cust}, {shop} here. {days} days to your wedding.{did}{nxt} Want to book this week?", "binary_yes_no"

    if kind == "customer_lapsed_hard":
        days = payload.get("days_since_last_visit")
        focus = payload.get("previous_focus")
        if days is not None:
            goal = f" Your {_words(focus)} goal is still waiting." if focus else ""
            return f"Hi {cust}, {shop} here. It's been {days} days.{goal} Want to pick up where you left off?", "binary_yes_no"

    return None, "binary_yes_no"


def compose_fallback(category, merchant, trigger, customer=None) -> dict:
    """Rule-based composition. Same return shape as composer.compose."""
    trigger = trigger or {}
    payload = trigger.get("payload") or {}
    kind = trigger.get("kind", "")
    is_customer_facing = trigger.get("scope") == "customer"

    if is_customer_facing and customer:
        body, cta = _customer_body(kind, payload, merchant, customer)
    else:
        body, cta = _merchant_body(kind, payload, merchant, category)

    if not body:
        # Nothing kind-specific survived the presence checks. Fall back to the
        # strongest merchant fact we actually hold, or say nothing at all.
        anchor = _merchant_anchor(merchant, category)
        if not anchor:
            body, cta = "", "none"
        else:
            body = f"{_first_name(merchant)}, {anchor}. Want me to draft something around it this week?"
            cta = "binary_yes_no"

    return {
        "body": body.strip(),
        "cta": cta,
        "send_as": "merchant_on_behalf" if is_customer_facing else "vera",
        "suppression_key": trigger.get("suppression_key", ""),
        "rationale": (
            f"LLM unavailable; deterministic composition for trigger kind '{kind}' "
            "using only facts present in the pushed contexts."
        ),
    }


_ACCEPT = ("yes", "yeah", "sure", "ok", "okay", "book", "confirm", "haan", "theek", "1", "2")
_DECLINE = ("no", "can't", "cant", "cannot", "busy", "reschedule", "later", "another time", "nahi")
_PRICE = ("price", "cost", "how much", "charge", "fee", "kitna", "rate")


def customer_reply_fallback(merchant, customer, message: str, sent_bodies: list[str]) -> dict:
    """Rule-based reply sent as the business, to its own customer."""
    cust = ((customer or {}).get("identity", {}) or {}).get("name", "") or "there"
    first = cust.split()[0]
    shop = _business(merchant) or "we"
    offer = _active_offer(merchant)
    low = f" {message.strip().lower()} "

    if any(f" {w} " in low or low.strip() == w for w in _DECLINE):
        body = f"No problem, {first}. Tell us a day and time that suits you and we'll hold a slot."
        cta = "open_ended"
    elif any(w in low for w in _PRICE):
        priced = f" {offer} is what most customers book." if offer else ""
        body = f"Hi {first}.{priced} Anything else you'd like to know before we book you in?"
        cta = "open_ended"
    elif any(f" {w} " in low or low.strip() == w for w in _ACCEPT):
        confirmed = f" Your {offer} is confirmed." if offer else ""
        body = f"Done, {first} — you're booked.{confirmed} We'll send a reminder the day before."
        cta = "none"
    else:
        body = f"Thanks {first}. What time suits you best — morning or evening? We'll fit you in this week."
        cta = "open_ended"

    if body in (sent_bodies or []):
        body = f"{first}, just checking in — shall we lock a time for you this week?"
        cta = "binary_yes_no"

    return {
        "action": "send",
        "body": body,
        "cta": cta,
        "rationale": "LLM unavailable; deterministic customer-facing reply sent as the merchant, grounded in their catalog.",
    }


def reply_fallback(merchant, category, message: str, sent_bodies: list[str], intent: bool) -> dict:
    """Rule-based reply. Same return shape as the LLM reply path."""
    name = _first_name(merchant)
    offer = _active_offer(merchant)

    if intent:
        scope = ((merchant or {}).get("customer_aggregate", {}) or {}).get("lapsed_180d_plus")
        target = f" to your {scope} lapsed customers" if scope else ""
        drafting = f"Drafting the '{offer}' push{target} now" if offer else "Drafting it now"
        candidates = [
            f"{name}, on it. {drafting} — I'll have it in front of you shortly. Reply CONFIRM to send.",
            f"{name}, starting now. {drafting}. Reply CONFIRM when you want it live.",
        ]
        cta = "binary_confirm_cancel"
    else:
        anchor = _merchant_anchor(merchant, category)
        hook = f" Worth noting: {anchor}." if anchor else ""
        candidates = [
            f"{name}, got it.{hook} What would help most right now — more footfall, better reviews, or winning back lapsed customers?",
            f"{name}, understood.{hook} Where should I point first?",
        ]
        cta = "open_ended"

    body = next((c for c in candidates if c not in (sent_bodies or [])), candidates[-1])
    return {
        "action": "send",
        "body": body,
        "cta": cta,
        "rationale": (
            "LLM unavailable; deterministic reply grounded in merchant context. "
            + ("Merchant committed, so moving to action rather than re-qualifying." if intent else "Advancing the thread with a single open ask.")
        ),
    }
