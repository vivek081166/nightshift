"""Block 1, step 2: plan.py at six output limits x three thinking settings, 3 calls per cell."""
import json, sys
sys.path[:0] = [".", "measure"]
ARGS, sys.argv = sys.argv[1:], ["plan.py"]
import plan, record

OUT = "runs/ep05/block1-grid.json"
LIMITS = [None, 2048, 512, 256, 128, 64]
THINKING = [("API default", None), ("low (lowest accepted)", {"thinkingLevel": "low"}),
            ("high (highest accepted)", {"thinkingLevel": "high"})]
if ARGS == ["--refine"]:   # the gap between 512 (cut) and 2048 (whole) at default and high
    OUT, LIMITS, THINKING = "runs/ep05/block1-grid-1024.json", [1024], [THINKING[0], THINKING[2]]

records = []
for tname, thinking in THINKING:
    for limit in LIMITS:
        for i in range(3):
            config = {"responseMimeType": "application/json", "responseSchema": plan.SCHEMA}
            if limit is not None:
                config["maxOutputTokens"] = limit
            if thinking is not None:
                config["thinkingConfig"] = thinking
            rec = record.send(plan.MODEL, plan.PROMPT, config,
                              {"thinking": tname, "maxOutputTokens": limit, "call": i + 1})
            text = rec.get("text") or ""
            try:
                json.loads(text); rec["json_ok"] = True
            except Exception as e:
                rec["json_ok"] = False; rec["json_error"] = f"{type(e).__name__}: {e}"
            rec["text_len"] = len(text); rec["first60"] = text[:60]; rec["last60"] = text[-60:]
            records.append(rec)
            record.save(OUT, records)
            u = rec.get("usageMetadata") or {}
            print(f"{tname[:12]:12} {str(limit):5} #{i+1} http {rec['http']} {rec.get('finishReason')} "
                  f"think {u.get('thoughtsTokenCount')} ans {u.get('candidatesTokenCount')} "
                  f"json {rec['json_ok']} len {len(text)} naive {rec.get('naive_parts')} {rec['latency_s']}s")
            if rec["http"] == 402:
                sys.exit("402: credits depleted, stopping")
print("total $", round(sum(r.get("cost_usd") or 0 for r in records), 4))
