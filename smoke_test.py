import json
import os
import urllib.request as ur

from bot import load_dataset

BASE = os.getenv("BOT_URL", "http://localhost:8080").rstrip("/")


def _call(method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = ur.Request(f"{BASE}{path}", data=data, method=method,
                     headers={"Content-Type": "application/json"})
    try:
        with ur.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except ur.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def main() -> None:
    ds = load_dataset()

    print("healthz:", _call("GET", "/v1/healthz"))
    print("metadata:", _call("GET", "/v1/metadata")[0])

    for slug, cat in ds["categories"].items():
        _call("POST", "/v1/context", {"scope": "category", "context_id": slug, "version": 1, "payload": cat})
    for mid, m in list(ds["merchants"].items())[:5]:
        _call("POST", "/v1/context", {"scope": "merchant", "context_id": mid, "version": 1, "payload": m})

    tid = next(iter(ds["triggers"]))
    trg = ds["triggers"][tid]
    if trg.get("customer_id") and trg["customer_id"] in ds["customers"]:
        _call("POST", "/v1/context", {"scope": "customer", "context_id": trg["customer_id"], "version": 1, "payload": ds["customers"][trg["customer_id"]]})
    _call("POST", "/v1/context", {"scope": "trigger", "context_id": tid, "version": 1, "payload": trg})

    status, health = _call("GET", "/v1/healthz")
    print("counts:", health.get("contexts_loaded"))

    print("dup push (expect 409):", _call("POST", "/v1/context", {"scope": "trigger", "context_id": tid, "version": 1, "payload": trg})[0])

    status, tick = _call("POST", "/v1/tick", {"now": "2026-07-09T10:00:00Z", "available_triggers": [tid]})
    acts = tick.get("actions", [])
    print(f"tick: {len(acts)} action(s)")
    if acts:
        print("  body:", acts[0]["body"][:120])
        print("  cta:", acts[0]["cta"], "| send_as:", acts[0]["send_as"])

    conv = acts[0]["conversation_id"] if acts else "conv_smoke"
    mid = trg.get("merchant_id")
    for msg, label in [
        ("Yes please, go ahead.", "engaged/intent"),
        ("Thank you for contacting us! We will respond shortly.", "auto-reply"),
        ("Stop messaging me, this is useless spam.", "opt-out"),
    ]:
        _, r = _call("POST", "/v1/reply", {"conversation_id": conv + "_" + label, "merchant_id": mid,
                                           "from_role": "merchant", "message": msg, "turn_number": 2})
        print(f"reply [{label}]:", r.get("action"), "-", (r.get("body") or r.get("rationale", ""))[:80])


if __name__ == "__main__":
    main()
