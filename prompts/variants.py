DEFAULT = {
    "frame": "State why this matters to this merchant right now, tied to the trigger. Offer one concrete next step.",
    "cta": "binary_yes_no",
}

VARIANTS: dict[str, dict[str, str]] = {
    "research_digest": {
        "frame": "Surface the single most relevant digest item. Lead with its headline stat and cite the source. Offer to turn it into something the merchant can use.",
        "cta": "open_ended",
    },
    "regulation_change": {
        "frame": "Flag the compliance change and its deadline plainly. State the concrete action needed. Do not alarm; be matter-of-fact.",
        "cta": "binary_yes_no",
    },
    "recall_due": {
        "frame": "Remind the customer their service is due, using time since last visit. Offer the available slots and a service-at-price. Keep it warm and personal.",
        "cta": "multi_choice_slot",
    },
    "chronic_refill_due": {
        "frame": "Remind the customer a refill is due before they run out. Offer pickup or delivery in one step.",
        "cta": "binary_yes_no",
    },
    "perf_dip": {
        "frame": "Name the specific metric drop with numbers and window. Propose one lever tied to their offers to recover it.",
        "cta": "binary_yes_no",
    },
    "seasonal_perf_dip": {
        "frame": "Attribute the dip to the seasonal beat, so it reads as expected not alarming. Suggest one timely counter-move.",
        "cta": "binary_yes_no",
    },
    "perf_spike": {
        "frame": "Celebrate the specific gain with numbers, then suggest one move to capitalize while momentum is up.",
        "cta": "binary_yes_no",
    },
    "milestone_reached": {
        "frame": "Acknowledge the milestone with the exact figure. Suggest one way to build on it.",
        "cta": "binary_yes_no",
    },
    "category_seasonal": {
        "frame": "Tie the seasonal beat to a specific offer or content the merchant can run now.",
        "cta": "binary_yes_no",
    },
    "festival_upcoming": {
        "frame": "Name the festival and days remaining. Propose one festival-specific offer or post from context.",
        "cta": "binary_yes_no",
    },
    "ipl_match_today": {
        "frame": "Tie today's match to a same-day offer or footfall play. Time-sensitive, act now.",
        "cta": "binary_yes_no",
    },
    "cde_opportunity": {
        "frame": "Present the professional development opportunity with date and relevance. Offer to register or remind.",
        "cta": "binary_yes_no",
    },
    "competitor_opened": {
        "frame": "State the competitor development factually, without fear-mongering. Propose one defensive move from their strengths.",
        "cta": "binary_yes_no",
    },
    "curious_ask_due": {
        "frame": "Re-open with the specific thing the customer showed interest in. Low-pressure, single question.",
        "cta": "open_ended",
    },
    "customer_lapsed_hard": {
        "frame": "Win back a long-lapsed customer. Reference their history, offer a specific reason to return now.",
        "cta": "binary_yes_no",
    },
    "winback_eligible": {
        "frame": "Offer a concrete win-back incentive tied to the customer's past service. One clear ask.",
        "cta": "binary_yes_no",
    },
    "dormant_with_vera": {
        "frame": "Re-engage a merchant who went quiet. Lead with one fresh, useful item, not a nag.",
        "cta": "binary_yes_no",
    },
    "gbp_unverified": {
        "frame": "Prompt the verification step with the concrete benefit of completing it. One action.",
        "cta": "binary_yes_no",
    },
    "renewal_due": {
        "frame": "Note days remaining on the plan and the value already delivered. Offer the renewal step.",
        "cta": "binary_confirm_cancel",
    },
    "review_theme_emerged": {
        "frame": "Surface the recurring review theme with the count. Suggest one operational or messaging response.",
        "cta": "binary_yes_no",
    },
    "supply_alert": {
        "frame": "Flag the supply/stock issue with specifics. Offer the reorder or substitute action.",
        "cta": "binary_yes_no",
    },
    "trial_followup": {
        "frame": "Follow up after a trial with the customer. Reference the trial, offer the conversion step.",
        "cta": "binary_yes_no",
    },
    "wedding_package_followup": {
        "frame": "Follow up on wedding-package interest with the specific package and date. Offer to hold a slot.",
        "cta": "binary_yes_no",
    },
    "active_planning_intent": {
        "frame": "Customer is actively planning. Move straight to helping them decide, offer concrete options.",
        "cta": "multi_choice_slot",
    },
}


def variant_for(kind: str) -> dict[str, str]:
    return VARIANTS.get(kind, DEFAULT)
