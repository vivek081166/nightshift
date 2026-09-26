"""Table for blocks 2 and 3: one row per run, plus the band per model/setting."""
import json, sys
print("| file | model | thinking | run | score /30 | missed | in | answer | thoughts | cost $ | wall s | p50 s | max s | non-200 | retries |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
bands = []
for f in sys.argv[1:]:
    d = json.load(open(f))
    for s in d["runs"]:
        c = "UNVERIFIED" if s["cost_usd"] is None else f"{s['cost_usd']:.4f}"
        print(f"| {f.split('/')[-1]} | {d['model']} | {d['thinking']} | {s['run']} | {s['score']} | {', '.join(s['missed'])} | "
              f"{s['in']:,} | {s['answer']:,} | {s['thoughts']:,} | {c} | {s['wall_s']} | {s['p50_s']} | {s['max_s']:.2f} | "
              f"{s['http_not_200']} | {s['retries']} |")
    sc = [s["score"] for s in d["runs"]]
    cost = [s["cost_usd"] or 0 for s in d["runs"]]
    bands.append(f"{d['model']} / {d['thinking']}: scores {' '.join(map(str, sc))} (n={len(sc)} runs of 30), "
                 f"low {min(sc)} high {max(sc)}, mean cost/run ${sum(cost)/len(cost):.4f}, "
                 f"mean wall {sum(s['wall_s'] for s in d['runs'])/len(sc):.1f} s, "
                 f"format failures {sum(len(s['format_fail']) for s in d['runs'])}")
print()
for b in bands: print("- " + b)
