import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Store:
    def __init__(self) -> None:
        self._start = time.time()
        self._contexts: dict[tuple[str, str], dict[str, Any]] = {}
        self.conversations: dict[str, dict[str, Any]] = {}
        self.suppressed_keys: set[str] = set()
        self.ended_conversations: set[str] = set()
        self.merchant_state: dict[str, dict[str, Any]] = {}

    # --- context store with idempotency ---

    def push(self, scope: str, context_id: str, version: int, payload: dict) -> dict:
        key = (scope, context_id)
        existing = self._contexts.get(key)
        if existing and version == existing["version"]:
            return {
                "ok": True,
                "ack_id": f"ack_{context_id}_v{version}",
                "stored_at": existing["stored_at"],
            }
        if existing and version < existing["version"]:
            return {
                "ok": False,
                "reason": "stale_version",
                "current_version": existing["version"],
            }
        self._contexts[key] = {
            "version": version,
            "payload": payload,
            "stored_at": _now_iso(),
        }
        return {
            "ok": True,
            "ack_id": f"ack_{context_id}_v{version}",
            "stored_at": self._contexts[key]["stored_at"],
        }

    def get(self, scope: str, context_id: str) -> Optional[dict]:
        entry = self._contexts.get((scope, context_id))
        return entry["payload"] if entry else None

    def category(self, slug: str) -> Optional[dict]:
        return self.get("category", slug)

    def merchant(self, merchant_id: str) -> Optional[dict]:
        return self.get("merchant", merchant_id)

    def customer(self, customer_id: str) -> Optional[dict]:
        return self.get("customer", customer_id)

    def trigger(self, trigger_id: str) -> Optional[dict]:
        return self.get("trigger", trigger_id)

    # --- per-merchant conversational state (survives conversation_id churn) ---

    def merchant_slot(self, merchant_key: str) -> dict[str, Any]:
        return self.merchant_state.setdefault(merchant_key, {"auto_streak": 0, "inbound": deque(maxlen=50)})

    def reset(self) -> None:
        self._contexts.clear()
        self.conversations.clear()
        self.suppressed_keys.clear()
        self.ended_conversations.clear()
        self.merchant_state.clear()

    # --- health/counts ---

    def counts(self) -> dict[str, int]:
        out = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        for scope, _ in self._contexts:
            if scope in out:
                out[scope] += 1
        return out

    def uptime_seconds(self) -> int:
        return int(time.time() - self._start)


store = Store()
