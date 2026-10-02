"""EP07 M3: ask Gemini for the next-piece candidates (logprobs), prompt-only and with the schema.

    python3 measure/ep07_logprobs.py          # payments-latency, both modes, saved to runs/ep07/
Env: GEMINI_API_KEY. Stops on HTTP 402.
"""
import datetime, json, os, sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))
from ep07_shape import CASES, body_for, post, cost, OUT  # noqa: E402

case = CASES[0]   # payments-latency, the cold-open alert
out, spent = {"case": case["id"]}, 0.0
for mode in ("prompt", "schema"):
    body = body_for(mode, case["alert"])
    body["generationConfig"].update(responseLogprobs=True, logprobs=10)
    rec = post(body, f"logprobs/{mode}/{case['id']}")
    spent += cost(rec)
    out[mode] = rec
    print(mode, "HTTP", rec.get("status"), (rec.get("error") or "")[:600])
    if rec.get("status") == 200:
        cand = rec["response"]["candidates"][0]
        print("  keys:", list(cand), "logprobsResult" in cand)
path = os.path.join(OUT, f"{datetime.date.today()}-logprobs-gemini-3.8-flash.json")
if os.path.exists(path):
    sys.exit(f"{path} exists: record once")
json.dump(out, open(path, "w"), indent=1, ensure_ascii=False)
print("saved", os.path.relpath(path, ROOT), f"${spent:.4f}")
