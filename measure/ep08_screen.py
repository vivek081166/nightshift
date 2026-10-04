"""EP08's two no-API screens, read from the saved runs (nothing calls the model).

    python3 measure/ep08_screen.py readings   # the dashboard: every answer from five runs of the picture, and the truth
    python3 measure/ep08_screen.py pdf        # the postmortem PDF: ten questions, three runs, how many came back right
"""
import json, os, sys

RUNS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runs", "ep08")
# arch/latency.png at the default detail (graph-A) and at HIGH (the same 1,100 tokens). graph-B is a different picture.
PICTURE_RUNS = ["graph-A-run1", "graph-A-run2", "graph-A-run3", "graph-res-high-run1", "graph-res-high-run2"]
NAMES = {"Q1": "first over 2 s", "Q2": "peak", "Q3": "peak time", "Q4": "deploy", "Q5": "over 1 s before/after deploy",
         "Q6": "rollback started", "Q7": "back under 500 ms", "Q8": "api at the peak", "Q9": "payments at 01:30",
         "Q10": "minutes above 2 s"}


def load(name):
    return json.load(open(os.path.join(RUNS, f"2026-10-03-{name}.json")))


def short(text):
    return text.strip().replace(" ms", "").replace(" minutes", "").lower()


def readings():
    runs = [{r["qid"]: r for r in load(name)} for name in PICTURE_RUNS]
    print(f"the dashboard, five times · {len(NAMES)} questions\n")
    for qid, name in NAMES.items():
        cells = "  ".join(f"{short(run[qid]['text']):>5}" for run in runs)
        truth = str(runs[0][qid]["score"]["truth"]).lower()
        print(f"{name:<29} {cells}   · truth {truth}")


def pdf():
    rows = [r for i in (1, 2, 3) for r in load(f"pdf-pdf-run{i}")]
    right = sum(1 for r in rows if r["score"]["ok"])
    print(f"{len({r['qid'] for r in rows})} questions · 3 runs · right {right} / {len(rows)}")


if __name__ == "__main__":
    {"readings": readings, "pdf": pdf}[sys.argv[1]]()
