"""Print the episode's tables from the saved run files. Calls no model, costs nothing.

    python3 measure/table.py thinking   # one model, three thinking levels, on the thirty alerts
    python3 measure/table.py models     # four models at their default thinking, on the thirty alerts
    python3 measure/table.py same       # the alerts every model got wrong, in every run, with the same answer, and their text
"""
import json, sys, textwrap

RUNS = "runs/ep05/"
THINKING = [("low", ["block2-gemini-3.8-flash-low.json"]),
            ("default", ["block3-gemini-3.8-flash.json"]),
            ("high", ["block2-gemini-3.8-flash-high-run1.json", "block2-gemini-3.8-flash-high-run2.json"])]
MODELS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.8-flash", "gemini-3.1-pro-preview"]


def load(files):
    runs, calls = [], []
    for f in files:
        d = json.load(open(RUNS + f))
        runs += d["runs"]
        calls += [dict(c, file=f) for c in d["calls"]]
    return runs, calls


def row(name, runs, width):
    scores = " ".join(str(r["score"]) for r in runs)
    cost = sum(r["cost_usd"] for r in runs) / len(runs)
    secs = sum(r["wall_s"] for r in runs) / len(runs)
    print(f"{name:{width}} {scores:10} ${cost:<13.4f} {secs:>5.0f}")


def table(rows, first):
    width = max(len(first), *(len(n) for n, _ in rows))
    print(f"{first:{width}} {'score/30':10} {'cost per run':14} {'seconds per run'}")
    for name, files in rows:
        row(name, load(files)[0], width)


what = sys.argv[1] if len(sys.argv) > 1 else "thinking"
if what == "thinking":
    table(THINKING, "thinking")
    print("\ngemini-3.8-flash · the thirty alerts · one score per run")
elif what == "models":
    table([(m, [f"block3-{m}.json"]) for m in MODELS], "model")
    print("\ndefault thinking · the thirty alerts · one score per run")
elif what == "same":
    alerts = {c["id"]: c["alert"] for c in json.load(open("tickets/incidents.json"))}
    per_model = {m: load([f"block3-{m}.json"]) for m in MODELS}
    n_runs = sum(len(runs) for runs, _ in per_model.values())
    wrong = {}   # alert id -> list of (model, run, got) for every wrong answer
    for m, (runs, calls) in per_model.items():
        for c in calls:
            if c["got"] != c["want"]:
                wrong.setdefault(c["id"], []).append((m, c["run"], c["got"], c["want"]))
    print(f"wrong in all {n_runs} runs, on all {len(MODELS)} models, with the same answer:\n")
    for alert, misses in wrong.items():
        answers = {got for _, _, got, _ in misses}
        if len(misses) == n_runs and len(answers) == 1:
            print(f"  {alert:27} wanted {misses[0][3]:15} got {answers.pop()}")
            print(textwrap.indent(textwrap.fill(alerts[alert], 64), "      ") + "\n")
else:
    sys.exit(__doc__)
