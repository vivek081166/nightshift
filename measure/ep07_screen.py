"""EP07's two no-API screens, read from the saved runs in runs/ep07/.

    python3 measure/ep07_screen.py values     # JSON mode, the thirty twice: what came back where my code looks
    python3 measure/ep07_screen.py choices    # an open model's choices for the next piece, without and with the shape
"""
import ast, collections, glob, json, os, sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
RUNS = os.path.join(ROOT, "runs/ep07")


def text_of(rec):
    return "".join(p.get("text", "") for p in rec["response"]["candidates"][0]["content"]["parts"])


def values():
    sev, move_key, reason_key = collections.Counter(), collections.Counter(), collections.Counter()
    for path in sorted(glob.glob(os.path.join(RUNS, "*-shape-loose-json-run*.json"))):
        for row in json.load(open(path)):
            triage = json.loads(text_of(row["rec"]))
            sev[triage["severity"]] += 1
            keys = list(triage)
            move_key[keys[2]] += 1     # the third field, where the first move went
            reason_key[keys[3]] += 1   # the fourth, where the reason went
    names = lambda c: " · ".join(k for k, _ in c.most_common())
    print("JSON mode, all thirty alerts, two runs\n")
    print(f"  {'my shape has':28} the answers had")
    print(f"  {'\"severity\": P1, P2 or P3':28} {names(sev)}")
    print(f"  {'\"first_move\"':28} {names(move_key)}")
    print(f"  {'\"reason\"':28} {names(reason_key)}")


def choices():
    d = json.load(open(os.path.join(RUNS, "2026-10-02-candidates-qwen3-8b-4bit.json")))
    free = d["runs"]["loose/unconstrained"]["spots"]["spot2_severity_value"]
    shaped = d["runs"]["loose/schema-mask"]["spots"]["spot2_severity_value"]
    top = lambda s, k: s[k] if isinstance(s[k], list) else ast.literal_eval(s[k])
    words = [c for c in top(free, "unconstrained_top10") if c["visible"].isascii()][:6]
    left = [c for c in top(shaped, "masked_renormalised_top10") if c["p"] > 0]
    bar = lambda p: "█" * round(42 * p) if round(42 * p) else "▏"
    print("an open model on my laptop (Qwen3-8B), not the model in the rest of this video")
    print('the alert from before · the answer so far:  { "severity": "\n')
    print("its choices for the next piece")
    for c in words:
        print(f"  {c['visible']:10} {bar(c['p'])}")
    print("\nwith the shape: the severity may only be P1, P2 or P3")
    for c in words:
        print(f"  {c['visible']:10} ✗")
    for c in left:
        print(f"  {c['visible']:10} {bar(c['p'])}   the start of P1, P2 or P3")


if __name__ == "__main__":
    {"values": values, "choices": choices}[sys.argv[1]]()
