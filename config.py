import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL = os.getenv("VERA_MODEL", "gemini-2.5-flash")
FALLBACK_MODEL = os.getenv("VERA_FALLBACK_MODEL", "gemini-2.5-flash-lite")
PORT = int(os.getenv("PORT", "8080"))

TEAM = {
    "team_name": "Vera 2.0",
    "team_members": ["Raj Singhal"],
    "model": MODEL,
    "approach": "single-prompt composer with id-lookup retrieval over digest items, dispatch by trigger.kind, post-LLM validator on both compose and reply paths (language + CTA + no-URL + anti-repeat), merchant-keyed auto-reply detection, deadline-bounded parallel tick",
    "contact_email": os.getenv("CONTACT_EMAIL", ""),
    "version": "1.1.0",
    "submitted_at": "2026-07-09T00:00:00Z",
}