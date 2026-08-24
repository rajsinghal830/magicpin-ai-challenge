import json
import sys
from pathlib import Path

from composer import compose as _compose

DATASET = Path(__file__).resolve().parent.parent / "magicpin-ai-challenge" / "dataset"


def compose(category, merchant, trigger, customer=None) -> dict:
    return _compose(category, merchant, trigger, customer)


def load_dataset() -> dict:
    categories, merchants, customers, triggers = {}, {}, {}, {}
    for f in (DATASET / "categories").glob("*.json"):
        data = json.load(open(f, encoding="utf-8"))
        categories[data.get("slug", f.stem)] = data
    for name, store, container, key in [
        ("merchants_seed.json", merchants, "merchants", "merchant_id"),
        ("customers_seed.json", customers, "customers", "customer_id"),
        ("triggers_seed.json", triggers, "triggers", "id"),
    ]:
        blob = json.load(open(DATASET / name, encoding="utf-8"))
        for item in blob.get(container, []):
            if key in item:
                store[item[key]] = item
    return {"categories": categories, "merchants": merchants, "customers": customers, "triggers": triggers}


def compose_trigger(trigger_id: str, ds: dict | None = None) -> dict:
    ds = ds or load_dataset()
    trigger = ds["triggers"][trigger_id]
    merchant = ds["merchants"].get(trigger.get("merchant_id"))
    slug = merchant.get("category_slug") if merchant else (trigger.get("payload", {}) or {}).get("category")
    category = ds["categories"].get(slug)
    customer = ds["customers"].get(trigger.get("customer_id")) if trigger.get("customer_id") else None
    return compose(category, merchant, trigger, customer)


if __name__ == "__main__":
    tid = sys.argv[1] if len(sys.argv) > 1 else "trg_001_research_digest_dentists"
    print(json.dumps(compose_trigger(tid), ensure_ascii=False, indent=2))


