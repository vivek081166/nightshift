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

## ep03

- Same model and prices as ep01 and ep02.
- `tickets/incidents.json`: 30 alerts with the first move wanted beside each. The first six are the six
  alerts from ep02, so the set the viewer already saw is still in this one. The five allowed first moves are
  `roll back`, `read logs`, `check provider`, `page owner`, `no action`.
- Every score below is `score.py` on this machine, 2026-09-21, saved verbatim as
  `runs/ep03/2026-09-21-ep03-*-run*.txt`. Five runs each way, nothing changed between the runs in a group.

      RULES empty  (baseline)   19 · 19 · 21 · 22 · 21     low 19, high 22, three points of wobble
      RULES filled (the change) 24 · 24 · 25 · 24 · 25     low 24, high 25, one point

  The highest baseline run is below the lowest run after the change, so the two do not overlap. That gap is
  the only reason the change can be called an improvement rather than a lucky run.
- Per case across those ten runs: 11 came right, 4 went backwards, 1 stayed wrong, 14 were right throughout.
  All four that went backwards now answer `page owner`, because the rule line says "when money, customer data
  or account access is involved" and a payments alert always involves money.
- `runs/ep03/freetext-2026-09-21.json`: the ep01/ep02 prompt asked of all thirty, 30 answers, 30 distinct
  sentences. That is why `score.py` hands the model a list of five words instead of asking for a sentence.
- `runs/ep03/fix-narrowed-2026-09-21.json`: NOT used in the episode. The second turn of the loop, narrowing
  the `page owner` line to damage you cannot undo, scored 30 29 30 30 30. It is left as the exercise because
  a set you score thirty out of thirty on has stopped being able to teach you anything, and because the
  answers and the rules came out of the same head. Kept here so the claim is checkable.
- ⚠️ `score.py` has no retry. About one call in a few hundred is dropped by the network and the script stops.
  Re-run it; nothing is cached, so a re-run is a fresh sample.
