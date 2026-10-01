"""The EP06 tables on screen, printed from the saved runs in runs/ep06/. Calls no model.

    python3 measure/ep06_screen.py shape    # JSON asked for three ways, all thirty
    python3 measure/ep06_screen.py names    # plain-text names against names given as a list
    python3 measure/ep06_screen.py fixes    # each name it made up, and what it asked for on the next try

Only the runs made with the real provider names (runrealnames1, 2, 3); the 09-30 runs used made-up ids.
"""
import glob, json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorrel.oncall import SERVICES, PROVIDERS  # noqa: E402

RUNS = os.path.join(os.path.dirname(__file__), "..", "runs", "ep06")


def text(rec):
    return "".join(p.get("text", "") for p in rec["response"]["candidates"][0]["content"]["parts"])


def shape():
    print(f"{'asked for JSON':26}{'run':>5}{'parsed':>10}{'right on what to do first':>28}")
    for mode, label in (("prompt", "asked in words only"), ("json", "with JSON mode"), ("schema", "JSON mode + the shape")):
        for path in sorted(glob.glob(f"{RUNS}/*-shape-{mode}-*.json")):
            rows = json.load(open(path))
            parsed = right = 0
            for row in rows:
                try:
                    triage = json.loads(text(row["rec"]))
                except json.JSONDecodeError:
                    continue
                parsed += 1
                right += triage.get("first_move") == row["want"]
            run = path.rsplit("runrealnames", 1)[1].split(".")[0]
            print(f"{label:26}{run:>5}{f'{parsed} / {len(rows)}':>10}"
                  f"{(f'{right} / {len(rows)}' if parsed else '-'):>28}")


def made_up(args):
    return ("service" in args and args["service"] not in SERVICES) or \
           ("provider" in args and args["provider"] not in PROVIDERS)


def loop_runs(variant):
    return sorted(glob.glob(f"{RUNS}/*-loop-{variant}-*-runrealnames[0-9].json"))


def fixes():
    pairs = []
    for path in loop_runs("free"):
        for row in json.load(open(path)):
            steps = [t for t in row["trace"] if "call" in t]
            for t, nxt in zip(steps, steps[1:]):
                if made_up(t["args"]) and nxt["call"] == t["call"] and not made_up(nxt["args"]):
                    key = "provider" if "provider" in t["args"] else "service"
                    pair = (t["args"][key], nxt["args"][key])
                    if pair not in pairs:
                        pairs.append(pair)
    order = PROVIDERS + SERVICES
    pairs.sort(key=lambda p: order.index(p[1]) if p[1] in order else len(order))
    print(f"{'it asked for':18}the next try")
    for bad, good in pairs:
        print(f"{bad:18}{good}")


def names():
    print(f"{'names given as':16}{'run':>5}{'tool calls':>12}{'made up':>9}{'fixed next call':>17}")
    seen = []
    for variant, label in (("free", "plain text"), ("enum", "a list")):
        tot = [0, 0, 0]
        for path in loop_runs(variant):
            calls = bad = fixed = 0
            for row in json.load(open(path)):
                steps = [t for t in row["trace"] if "call" in t]
                calls += len(steps)
                for i, t in enumerate(steps):
                    if made_up(t["args"]):
                        assert t["refused"], "a made-up name that the check let through"
                        bad += 1
                        seen.append(t["args"].get("provider", t["args"].get("service")))
                        nxt = steps[i + 1] if i + 1 < len(steps) else None
                        fixed += bool(nxt and nxt["call"] == t["call"] and not made_up(nxt["args"]))
            run = path.rsplit("runrealnames", 1)[1].split(".")[0]
            tot = [tot[0] + calls, tot[1] + bad, tot[2] + fixed]
            print(f"{label:16}{run:>5}{calls:>12}{bad:>9}{(fixed if bad else '-'):>17}")
        print(f"{'':16}{'all':>5}{tot[0]:>12}{tot[1]:>9}{(tot[2] if tot[1] else '-'):>17}")
    print("\nthe names it made up: " + ", ".join(sorted(set(seen))) + " (every one refused by the check)")


if __name__ == "__main__":
    {"shape": shape, "names": names, "fixes": fixes}[sys.argv[1]]()
