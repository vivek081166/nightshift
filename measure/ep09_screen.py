"""EP09's screens from the saved runs (calls no model).

    python3 measure/ep09_screen.py hits     an earlier run of the thirty alerts, one row each, as cache.py prints them
    python3 measure/ep09_screen.py close    the module close

The same thirty alerts with the same handbook, word for word, sent twice: with only the automatic cache
(runs/ep09/2026-10-05-m6-fixed.json), then every call pointed at a cache I made (2026-10-05-m7-explicit-scored.json).
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, "runs", "ep09")
PRICE_IN = 0.75   # dollars per million: the cache's own tokens, counted once at the input rate when it is made
WANT = {c["id"]: c["want"] for c in json.load(open(os.path.join(ROOT, "tickets", "incidents.json")))}


def load(name):
    return json.load(open(os.path.join(RUNS, f"2026-10-05-{name}.json")))


def misses(calls):
    return [c["id"] for c in calls if json.loads(c["text"]).get("first_move") != WANT[c["id"]]]


def hits():
    run = load("m1-baseline")   # handbook first, then the alert and the ask, nothing else changes: the automatic cache only
    print("an earlier run · the same thirty alerts\n")
    for c in run["calls"]:
        print(f"{c['id']:28} sent {c['prompt']:,}   cached {c['cached']:,}")


def close():
    auto, made = load("m6-fixed"), load("m7-explicit-scored")
    bill_auto = sum(c["cost_usd"] for c in auto["calls"])
    making = made["create"]["response"]["usageMetadata"]["totalTokenCount"] * PRICE_IN / 1e6
    bill_made = sum(c["cost_usd"] for c in made["calls"]) + making + made["storage"]["usd"]
    miss_auto, miss_made = misses(auto["calls"]), misses(made["calls"])
    n = len(WANT)
    print("same thirty alerts · same handbook, word for word\n")
    print(f"automatic cache only    right {n - len(miss_auto)}/{n}    bill ${bill_auto:.3f}")
    print(f"a cache I made          right {n - len(miss_made)}/{n}    bill ${bill_made:.3f}   (making it and keeping it included)")
    if miss_auto == miss_made:
        print(f"\nmissed (both): {' · '.join(miss_auto)}")
    else:
        print(f"\nmissed: automatic {' · '.join(miss_auto)} | made {' · '.join(miss_made)}")


if __name__ == "__main__":
    {"hits": hits, "close": close}[sys.argv[1]]()
