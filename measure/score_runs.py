"""Measurement harness: score.py's exact prompt, N full runs on one model, every call saved.

    python3 measure/score_runs.py MODEL RUNS OUT.json [low|high]     # thinking level optional
    python3 measure/score_runs.py MODEL pilot OUT.json [low|high]    # one call, for the cost estimate
"""
import json, statistics, sys, time
sys.path[:0] = [".", "measure"]
import record

# Take CASES, ACTIONS, RULES and prompt() from score.py itself, so the prompt is byte-for-byte the same.
src = open("score.py").read()
ns = {}
exec(src[:src.index("\ndef ask(")] + "\n" + src[src.index("\ndef prompt("):src.index("\ndef ask(")], ns)
CASES, ACTIONS, prompt = ns["CASES"], ns["ACTIONS"], ns["prompt"]

model, runs, out = sys.argv[1], sys.argv[2], sys.argv[3]
level = sys.argv[4] if len(sys.argv) > 4 else None
config = {"thinkingConfig": {"thinkingLevel": level}} if level else None
pilot = runs == "pilot"
cases = CASES[:1] if pilot else CASES
records, summaries = [], []
for run in range(1 if pilot else int(runs)):
    t0, score, missed = time.time(), 0, []
    for case in cases:
        rec = record.send(model, prompt(case["alert"]), config,
                          {"run": run + 1, "id": case["id"], "want": case["want"], "thinking": level or "API default"})
        got = (rec.get("text") or "").strip().lower().strip(".")
        rec["got"], rec["right"], rec["format_ok"] = got, got == case["want"], got in ACTIONS
        score += rec["right"]
        if not rec["right"]:
            missed.append(case["id"])
        records.append(rec)
        record.save(out, {"model": model, "thinking": level or "API default", "runs": summaries, "calls": records})
        if rec["http"] == 402:
            sys.exit("402: credits depleted, stopping")
        if rec["http"] != 200:
            print("  HTTP", rec["http"], case["id"], (rec["error"] or "")[:200])
    calls = [r for r in records if r["run"] == run + 1]
    u = [r.get("usageMetadata") or {} for r in calls]
    lat = [r["latency_s"] for r in calls]
    s = {"run": run + 1, "score": score, "of": len(cases), "missed": missed,
         "format_fail": [(r["id"], r.get("text")) for r in calls if not r["format_ok"]],
         "in": sum(x.get("promptTokenCount", 0) for x in u),
         "answer": sum(x.get("candidatesTokenCount", 0) for x in u),
         "thoughts": sum(x.get("thoughtsTokenCount", 0) for x in u),
         "cost_usd": round(sum(r.get("cost_usd") or 0 for r in calls), 5) if model in record.PRICES else None,
         "wall_s": round(time.time() - t0, 1), "p50_s": round(statistics.median(lat), 2), "max_s": max(lat),
         "http_not_200": sum(r["http"] != 200 for r in calls), "retries": sum(len(r["retries"]) for r in calls),
         "modelVersion": sorted({r.get("modelVersion") or "-" for r in calls})}
    summaries.append(s)
    record.save(out, {"model": model, "thinking": level or "API default", "runs": summaries, "calls": records})
    print(json.dumps(s))
