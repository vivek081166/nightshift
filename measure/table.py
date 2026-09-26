"""Print the episode's tables from the saved run files. Calls no model, costs nothing.

    python3 measure/table.py thinking   # one model, three thinking levels, on the thirty alerts
    python3 measure/table.py models     # four models at their default thinking, on the thirty alerts
    python3 measure/table.py same         # the alerts wrong in every run (4 models + low and high thinking), and their text
    python3 measure/table.py temperature  # the borderline alert, ten answers at the default and ten at temperature 0
    python3 measure/table.py narrowed     # score.py's rules against the page owner line narrowed (score.py --narrowed)
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
    print(f"{name:{width}} {len(runs):>4}  {scores:10} ${cost:<13.4f} {secs:>5.0f}")


def table(rows, first):
    width = max(len(first), *(len(n) for n, _ in rows))
    print(f"{first:{width}} {'runs':>4}  {'score/30':10} {'cost per run':14} {'seconds per run'}")
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
    groups = [(m, [f"block3-{m}.json"]) for m in MODELS] + \
             [("gemini-3.8-flash low", ["block2-gemini-3.8-flash-low.json"]),
              ("gemini-3.8-flash high", THINKING[2][1])]
    loaded = [load(files) for _, files in groups]
    n_runs = sum(len(runs) for runs, _ in loaded)
    wrong = {}   # alert id -> every wrong answer, one per run
    for runs, calls in loaded:
        for c in calls:
            if c["got"] != c["want"]:
                wrong.setdefault(c["id"], []).append((c["got"], c["want"]))
    print(f"wrong in all {n_runs} runs, with the same answer:")
    print(f"  {len(MODELS)} models at their default thinking, and gemini-3.8-flash at low and high\n")
    for alert, misses in wrong.items():
        answers = {got for got, _ in misses}
        if len(misses) == n_runs and len(answers) == 1:
            print(f"  {alert:27} wanted {misses[0][1]:15} got {answers.pop()}")
            print(textwrap.indent(textwrap.fill(alerts[alert], 64), "      ") + "\n")
elif what == "temperature":
    probe = json.load(open("runs/ep02/flip-probe-2026-09-15.json"))
    rows = [r for r in probe["results"] if r["alert"] == "payments-partial"]
    print(f"payments-partial, {probe['model']}, {probe['n']} answers at each setting ({probe['date']})\n")
    print(f"{'temperature':12} {'P1 wake someone':16} {'P2 can wait':12} {'worded differently'}")
    for r in rows:
        t = "default" if r["temperature"] is None else f"{r['temperature']:g}"
        print(f"{t:12} {r['tally'].get('P1', 0):>15}  {r['tally'].get('P2', 0):>11}  "
              f"{r['distinct_texts']:>9} of {len(r['answers'])}")
elif what == "narrowed":
    base_runs, base = load(["block3-gemini-3.8-flash.json"])
    new_runs, new = load(["block4-gemini-3.8-flash-narrowed.json"])
    print(f"gemini-3.8-flash, default thinking {'':10} runs  score/30")
    print(f"{'score.py rules':45} {len(base_runs):>4}  {' '.join(str(r['score']) for r in base_runs)}")
    print(f"{'page owner line narrowed':45} {len(new_runs):>4}  {' '.join(str(r['score']) for r in new_runs)}\n")
    print(f"  {'':27} {'wanted':15} {'score.py rules':17} narrowed")
    for alert in ["payments-partial", "payments-provider-timeout", "payments-region-cloud"]:
        got = lambda calls: ", ".join(sorted({c["got"] for c in calls if c["id"] == alert}))
        want = next(c["want"] for c in base if c["id"] == alert)
        print(f"  {alert:27} {want:15} {got(base):17} {got(new)}")
else:
    sys.exit(__doc__)
