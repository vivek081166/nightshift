"""Block 1, step 1: which thinking controls does gemini-3.8-flash accept? One plan.py call each."""
import json, sys
sys.path[:0] = [".", "measure"]; sys.argv = ["plan.py"]
import plan, record

OUT = "runs/ep05/block1-thinking-probe.json"
PROBES = [("API default", None)]
PROBES += [(f"thinkingLevel={v}", {"thinkingLevel": v}) for v in ["minimal", "low", "medium", "high"]]
PROBES += [(f"thinkingBudget={v}", {"thinkingBudget": v}) for v in [0, 128, 1024, -1]]

records = []
for name, thinking in PROBES:
    config = dict(plan.config)
    if thinking is not None:
        config["thinkingConfig"] = thinking
    rec = record.send(plan.MODEL, plan.PROMPT, config, {"probe": name})
    records.append(rec)
    record.save(OUT, records)
    u = rec.get("usageMetadata") or {}
    print(f"{name:24} http {rec['http']} {rec.get('finishReason')} thoughts {u.get('thoughtsTokenCount')} "
          f"answer {u.get('candidatesTokenCount')} {rec['latency_s']}s ${rec.get('cost_usd')}")
    if rec["http"] == 402:
        sys.exit("402: credits depleted, stopping")
    if rec["error"]:
        print("   ", json.loads(rec["error"])["error"]["message"] if rec["error"].startswith("{") else rec["error"])
print("total $", sum(r.get("cost_usd") or 0 for r in records))
