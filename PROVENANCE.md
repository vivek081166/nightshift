# Provenance

Every number this repo prints comes from a real call. Model ids and prices are pinned per episode,
so a run from six months ago still makes sense after the price has moved.

## ep01

- Model: `gemini-3.8-flash`
- Endpoint: `v1beta/models/{model}:generateContent`, raw HTTP, no SDK
- Prices used by the cost line: $0.75 per million input tokens, $3.75 per million output tokens.
  Google's public list price on 2026-09-12, the introductory rate for `gemini-3.8-flash`
  through 2026-12-31.
- Output tokens include `thoughtsTokenCount`, which the API bills and reports separately.

Every run shown on screen is saved verbatim under `runs/`. Every narration line that quotes a
number comes from that file, never from a plan.

## ep02

- Same model and prices as ep01.
- `runs/ep02/answers-50.json`: 50 answers to the ep01 alert, from 5 real runs on 2026-09-12 and 09-13.
  Severity P1 fifty times; 23 distinct sentences; 4 wrapped in markdown bold.
- `runs/ep02/parse-naive-2026-09-15.txt`: `startswith("P")` counts 46 of 50, `re.search` counts 50.
- `runs/ep02/flip-probe-2026-09-15.json`: 6 alerts x 10 runs x {default, temperature 0}, 120 calls, $0.2402.
  Only the ambiguous `payments-partial` alert moves its severity: P2 five / P1 five at the default,
  P1 nine / P2 one at temperature 0. Temperature 0 did not settle it and inverted which answer won.
  Ten answers at temperature 0 were still ten distinct sentences on five of the six alerts.
