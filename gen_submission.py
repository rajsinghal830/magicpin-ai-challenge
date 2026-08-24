import json
import time
from pathlib import Path

from bot import compose, load_dataset

OUT = Path(__file__).resolve().parent / "submission.jsonl"
TARGET_PAIRS = 30
THROTTLE_S = 4
ATTEMPTS = 3


def _pairs(ds: dict) -> list[tuple[str, str]]:
    """(trigger_id, merchant_id) pairs. Every trigger once, then fan out spare
    merchant-scope triggers onto same-category peers until we reach 30."""
    triggers = ds["triggers"]
    merchants = ds["merchants"]

    by_category: dict[str, list[str]] = {}
    for mid, m in merchants.items():
        by_category.setdefault(m.get("category_slug", ""), []).append(mid)

    pairs = [(tid, t.get("merchant_id")) for tid, t in triggers.items() if t.get("merchant_id")]
    seen = set(pairs)

    for tid, t in triggers.items():
        if len(pairs) >= TARGET_PAIRS:
            break
        if t.get("scope") == "customer":
            continue  # customer triggers are bound to one merchant's customer
        owner = merchants.get(t.get("merchant_id"), {})
        for mid in by_category.get(owner.get("category_slug", ""), []):
            if len(pairs) >= TARGET_PAIRS:
                break
            if (tid, mid) not in seen:
                pairs.append((tid, mid))
                seen.add((tid, mid))
                break

    return pairs[:TARGET_PAIRS]


def _compose_pair(ds: dict, trigger_id: str, merchant_id: str) -> dict:
    trigger = ds["triggers"][trigger_id]
    merchant = ds["merchants"][merchant_id]
    category = ds["categories"].get(merchant.get("category_slug"))
    customer = ds["customers"].get(trigger.get("customer_id")) if trigger.get("customer_id") else None
    return compose(category, merchant, trigger, customer)


def main() -> None:
    ds = load_dataset()
    pairs = _pairs(ds)
    if len(pairs) < TARGET_PAIRS:
        print(f"WARNING: only {len(pairs)} pairs available, target is {TARGET_PAIRS}")

    written = 0
    with open(OUT, "w", encoding="utf-8") as fh:
        for i, (tid, mid) in enumerate(pairs, 1):
            test_id = f"T{i:02d}"
            result = None
            for attempt in range(1, ATTEMPTS + 1):
                try:
                    result = _compose_pair(ds, tid, mid)
                    break
                except Exception as exc:
                    print(f"[{test_id}] {tid} attempt {attempt}/{ATTEMPTS} failed: {exc}")
                    if attempt < ATTEMPTS:
                        time.sleep(THROTTLE_S * attempt)
            if not result:
                print(f"[{test_id}] {tid} GAVE UP")
                continue

            trigger = ds["triggers"][tid]
            record = {
                "test_id": test_id,
                "trigger_id": tid,
                "merchant_id": mid,
                "customer_id": trigger.get("customer_id"),
                "kind": trigger.get("kind"),
                "body": result["body"],
                "cta": result["cta"],
                "send_as": result["send_as"],
                "suppression_key": result["suppression_key"],
                "rationale": result["rationale"],
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
            written += 1
            print(f"[{test_id}] {tid} -> {mid}")
            time.sleep(THROTTLE_S)

    print(f"Wrote {written}/{len(pairs)} lines to {OUT}")


if __name__ == "__main__":
    main()
