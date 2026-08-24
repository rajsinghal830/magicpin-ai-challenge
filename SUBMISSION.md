# Vera 2.0

Stateful HTTP bot that composes WhatsApp-quality messages for Indian local-commerce merchants (and their customers), initiates proactively, and handles multi-turn replies.

## Run

```bash
pip install -r requirements.txt
cp .env.example .env   # set GEMINI_API_KEY
python app.py          # serves on PORT (default 8080)
```

## Endpoints

| Endpoint | Method | Job |
|---|---|---|
| `/v1/healthz` | GET | liveness + loaded-context counts |
| `/v1/metadata` | GET | team + model + approach |
| `/v1/context` | POST | store/replace context, idempotent by `(scope, id, version)` |
| `/v1/tick` | POST | inspect state, decide proactive sends |
| `/v1/reply` | POST | merchant replied; returns send / wait / end |
| `/v1/teardown` | POST | wipe all state at end of test |

## Approach

- One composer core (`composer.py`) drives both the live server and the offline artifacts (`bot.py`, `gen_submission.py`).
- Retrieval is direct id lookup: the trigger's `top_item_id` resolves the digest item; no vector DB.
- `router.py` dispatches by `trigger.kind` to a framing variant; the system prompt injects category voice + merchant identity.
- Every draft passes a validator (`validators.py`): URL ban, CTA vocabulary, language match, anti-repetition. On failure the model is reprompted once with the specific fixes.
- Replies (`conversation.py`) handle deterministic exits — opt-out ends, auto-reply streak nudges/waits/ends at 1/2/3× — and switch to action framing on intent transition. Auto-reply streak is keyed on the *merchant*, not the conversation, so a merchant whose canned text arrives across fresh conversation ids is still caught; a verbatim inbound repeated 3× counts as an auto-reply even if it matches no phrase. Language is detected per turn, so a merchant switching English↔Hinglish mid-thread is mirrored.
- `/v1/tick` composes in parallel under a 24s deadline (judge cuts at 30s); stragglers are abandoned rather than awaited. One action per merchant per tick, 20 actions max, and a conversation is dropped after 3 unanswered nudges.
- State is in-memory (`store.py`); contexts are versioned and replaced atomically on a higher version.
- Every model call is wrapped. On 429, timeout, or unparseable JSON, `fallback.py` composes deterministically for all 24 trigger kinds (merchant- and customer-facing) rather than dropping the turn. Each field is read through a presence check: if a fact is absent from the context, the sentence carrying it is dropped, never filled in. Verified across all 25 seed triggers — zero ungrounded numbers, no URLs, CTAs in vocabulary, `send_as` correct.

## Model

Gemini `gemini-2.5-flash` primary, `gemini-2.5-flash-lite` fallback, `temperature=0` for determinism.
Override with `VERA_MODEL` / `VERA_FALLBACK_MODEL`.

## Tradeoffs

- In-memory state: fast and simple, but no persistence across restarts (fine for the test window).
- One-shot reprompt caps latency; we accept a rare invalid draft over unbounded retries.
- Framing variants are hand-tuned per kind — broad coverage, but a brand-new kind falls back to a generic frame.
- The rule composer trades eloquence for safety: it never code-mixes and it says less than the model would, but it cannot fabricate a statistic or a citation. When nothing verifiable exists in context it returns an empty body and the action is dropped — restraint over invention.
- Suppression keys ignore context version, so a re-pushed digest carrying a seen `suppression_key` is skipped. Keying on `(suppression_key, version)` would fix it.

## What extra context would help

- Per-merchant send-time preferences and prior response rates, to time and shape outreach.
- Explicit customer opt-in/consent scope per channel, to remove guesswork on customer-facing sends.
- Outcome feedback (did a sent message convert?) to close the loop and rank triggers by expected value.
