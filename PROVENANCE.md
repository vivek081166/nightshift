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
