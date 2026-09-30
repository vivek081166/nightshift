"""Count what the EP06 runs show, from runs/ep06/ only (no API).

    python3 measure/ep06_table.py shape
    python3 measure/ep06_table.py calls
    python3 measure/ep06_table.py loop
"""
import collections, glob, json, os, re, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sorrel.oncall import SERVICES, PROVIDERS, alert_service  # noqa: E402
from measure.ep06 import ACTIONS, check, proposed  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
CASES = {c["id"]: c for c in json.load(open(os.path.join(ROOT, "tickets/incidents.json")))}
TOOL_ACTION = {"roll_back": "roll back", "read_logs": "read logs", "check_provider": "check provider",
               "page_owner": "page owner", "no_action": "no action"}


def files(block):
    return sorted(glob.glob(os.path.join(ROOT, f"runs/ep06/*-{block}-*.json")))


def text_of(rec):
    try:
        return "".join(p.get("text", "") for p in rec["response"]["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError, TypeError):
        return None


def shape():
    for path in files("shape"):
        rows = json.load(open(path))
        c = collections.Counter()
        notes = []
        for row in rows:
            rec, case = row["rec"], CASES[row["case"]]
            c["calls"] += 1
            if rec.get("status") != 200:
                c[f"http {rec.get('status')}"] += 1
                continue
            raw = text_of(rec) or ""
            if raw.lstrip().startswith("```"):
                c["fenced"] += 1
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                c["json.loads fails"] += 1
                notes.append((row["case"], "unparsed", raw[:80]))
                continue
            if not isinstance(obj, dict):
                c["not an object"] += 1
                continue
            if set(obj) != {"severity", "service", "first_move", "reason"}:
                c["keys differ"] += 1
                notes.append((row["case"], "keys", sorted(obj)))
            if obj.get("severity") not in ("P1", "P2", "P3"):
                c["severity off-list"] += 1
                notes.append((row["case"], "severity", obj.get("severity")))
            if obj.get("service") not in SERVICES:
                c["service off-list"] += 1
                notes.append((row["case"], "service", obj.get("service")))
            elif obj.get("service") != alert_service(case):
                c["service valid but wrong"] += 1
                notes.append((row["case"], "service wrong", obj.get("service")))
            if obj.get("first_move") not in ACTIONS:
                c["first_move off-list"] += 1
                notes.append((row["case"], "first_move", obj.get("first_move")))
            elif obj.get("first_move") == case["want"]:
                c["first_move right"] += 1
        print(os.path.basename(path))
        for k, v in c.items():
            print(f"  {k:26} {v}")
        for n in notes:
            print("   ", *n)


def calls():
    for path in files("calls"):
        rows = json.load(open(path))
        c, tools, notes = collections.Counter(), collections.Counter(), []
        for row in rows:
            rec, case = row["rec"], CASES[row["case"]]
            c["calls"] += 1
            if rec.get("status") != 200:
                c[f"http {rec.get('status')}"] += 1
                notes.append((row["case"], "http", (rec.get("error") or "")[:120]))
                continue
            got = proposed(rec)
            if not got:
                c["no function call"] += 1
                notes.append((row["case"], "text", (text_of(rec) or "")[:80]))
                continue
            if len(got) > 1:
                c["more than one call"] += 1
            name, args = got[0]
            tools[name] += 1
            if TOOL_ACTION.get(name) == case["want"]:
                c["first call = wanted action"] += 1
            for n, a in got:
                why = check(n, a, case)
                if why:
                    c["refused by the check"] += 1
                    kind = re.sub(r"'[^']*'|\b[\w-]+\b(?= is over)|d-\d+", "X", why)
                    c[f"  refused: {kind[:60]}"] += 1
                    notes.append((row["case"], n, json.dumps(a), "->", why))
        print(os.path.basename(path))
        for k, v in c.items():
            print(f"  {k:60} {v}")
        print("  tools:", dict(tools))
        for n in notes:
            print("   ", *n)


def loop():
    for path in files("loop"):
        rows = json.load(open(path))
        c = collections.Counter()
        print(os.path.basename(path))
        for row in rows:
            steps = []
            for t in row["trace"]:
                if "call" in t:
                    mark = "REFUSED" if t["refused"] else "ran"
                    steps.append(f"{t['call']}({json.dumps(t['args'], ensure_ascii=False)}) {mark}")
                    c["refused" if t["refused"] else "ran"] += 1
                else:
                    steps.append("text: " + t["text"][:60].replace("\n", " "))
            bad = [r for r in row["calls"] if r.get("status") != 200]
            if bad:
                steps.append(f"HTTP {bad[0].get('status')}")
            print(f"  {row['case']:28} want {row['want']:15}", " -> ".join(steps))
        print("  ", dict(c))


if __name__ == "__main__":
    {"shape": shape, "calls": calls, "loop": loop}[sys.argv[1]]()
