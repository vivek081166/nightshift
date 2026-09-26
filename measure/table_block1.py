"""Block 1 table: per cell, finishReason, thoughts vs answer tokens, JSON parses, naive reader."""
import json
R = json.load(open("runs/ep05/block1-grid.json")) + json.load(open("runs/ep05/block1-grid-1024.json"))
order = [None, 2048, 1024, 512, 256, 128, 64]
print("| thinking | maxOutputTokens | n | finishReason | thoughts (each) | answer tokens (each) | json.loads ok | naive parts KeyError | text len (each) |")
print("|---|---|---|---|---|---|---|---|---|")
for t in ["API default", "low (lowest accepted)", "high (highest accepted)"]:
    for lim in order:
        c = [r for r in R if r["thinking"] == t and r["maxOutputTokens"] == lim]
        if not c: continue
        u = [r.get("usageMetadata") or {} for r in c]
        fr = "/".join(sorted({r.get("finishReason") or str(r["http"]) for r in c}))
        th = ",".join(str(x.get("thoughtsTokenCount", 0)) for x in u)
        an = ",".join(str(x.get("candidatesTokenCount", 0)) for x in u)
        ok = sum(r["json_ok"] for r in c); ke = sum(r.get("naive_parts") != "ok" for r in c)
        ln = ",".join(str(r["text_len"]) for r in c)
        print(f"| {t} | {lim or 'unset'} | {len(c)} | {fr} | {th} | {an} | {ok}/{len(c)} | {ke}/{len(c)} | {ln} |")
print("\nhttp statuses:", sorted({r["http"] for r in R}), " retries:", sum(len(r["retries"]) for r in R),
      " cost $", round(sum(r.get("cost_usd") or 0 for r in R), 4))
