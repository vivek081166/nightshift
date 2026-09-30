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
- The runs ON SCREEN in the episode were recorded live on camera on 2026-09-22, and their terminal text is saved
  verbatim as `runs/ep03/2026-09-22-ep03-camera-{askall,base,fix}.txt`. Every number the episode speaks comes
  from those three files. Five runs each way, nothing changed between the runs in a group, no network failures.

      ask_all.py, free text     30 answers, 30 of them different
      RULES empty  (baseline)   20 · 20 · 21 · 19 · 20     low 19, high 21, two points of wobble
      RULES filled (the change) 24 · 23 · 23 · 24 · 24     low 23, high 24

  The worst run after the change (23) beats the best run before it (21): the two bands do not overlap.
  Per case: 8 improved, 3 broke, 19 unchanged. The three that broke (payments-latency, payments-partial,
  notifier-vendor-5xx) were right in all five runs before and in none after, and all three now answer
  `page owner`: the rule line for it says "when money, customer data or account access is involved, or when
  somebody has to make a decision you are not allowed to make", and it reaches further than intended.
- The earlier runs of 2026-09-21 (`runs/ep03/2026-09-21-ep03-*-run*.txt`: 19 19 21 22 21 before, 24 24 25 24 25
  after) planned the episode and are kept; they tell the same story and are not what the video shows.
- `runs/ep03/freetext-2026-09-21.json` (planning run): the ep01/ep02 prompt asked of all thirty, 30 answers,
  30 distinct sentences; the camera run of 09-22 found the same, 30 of 30 different. That is why `score.py`
  hands the model a list of five words instead of asking for a sentence.
- `runs/ep03/fix-narrowed-2026-09-21.json`: NOT used in the episode. The second turn of the loop, narrowing
  the `page owner` line to damage you cannot undo, scored 30 29 30 30 30. It is left as the exercise because
  a set you score thirty out of thirty on has stopped being able to teach you anything, and because the
  answers and the rules came out of the same head. Kept here so the claim is checkable.
- ⚠️ `score.py` has no retry. About one call in a few hundred is dropped by the network and the script stops.
  Re-run it; nothing is cached, so a re-run is a fresh sample.

## ep04

- Same model and prices as ep01 to ep03: $0.75 per million input tokens, $3.75 per million output tokens,
  thinking billed as output. The pricing page fetched 2026-09-24 shows no long-context price tier for
  `gemini-3.8-flash` (`runs/ep04/2026-09-24-pricing-gemini-3.8-flash.txt`).
- The context window comes from the model itself: `GET v1beta/models/gemini-3.8-flash` returns
  `"inputTokenLimit": 1048576` (`runs/ep04/2026-09-24-model-resource.json`). `count.py` reads it live.
- `logs/sorrel-incident.log` is GENERATED, not a real incident: `python3 sorrel/make_logs.py`, stdlib, seed
  20260923, 40,000 lines, 7,676,813 bytes, md5 `c227166acf2b17df7b16c741186ceb8d`. The calls made on it are real.
  What went wrong in it is fixed before any call: at 13:38:32 the rate-cache refresher thread crashes on
  `KeyError: 'RATE_CACHE_TTL'` (line 32,545), the saved exchange rates expire, and every checkout looks them up live.
- `count.py`: 4,568,958 tokens for the whole log by `countTokens`, which is free and does not enforce the limit.
  4.36 times the context window. Sending the log whole is refused with HTTP 400 INVALID_ARGUMENT and no usage.
- `ask_log.py` sends the same question each time: the alert from ep01, the log, and "What is the root cause?
  Reply in two lines: the cause, then the one log line that shows it, copied exactly."
- `tail -n 875` is the last 100,000 tokens by the average tokens per line (875 lines, 99,895 tokens, the last
  74 seconds). It does not contain the traceback. `tail -n 9180` would, and is 180 tokens over the limit.
- `around_errors.py`: every line that says ` ERROR ` or starts `Traceback`, plus twenty lines either side,
  `...` between gaps. On this log: 127 lines, 13,245 tokens, the traceback inside.
- Planning runs, 2026-09-24 01:37-01:40 (`runs/ep04/2026-09-24-ep04-*.json`), three each:
  the tail 99,979 in, $0.0862-0.0882, named the live lookups as the cause 3 of 3;
  the lines around the errors 13,329 in, $0.0149-0.0170, named the crash and quoted `KeyError: 'RATE_CACHE_TTL'` 3 of 3.
  The whole log: 400 in 8.0 s, nothing returned.
- Dry run of the on-screen files, 2026-09-24 02:15-02:19, verbatim in `runs/ep04/dryrun-*.txt`. The runs ON SCREEN
  are recorded live on camera later; every number the episode speaks comes from those camera files.
- ⚠️ The input-token quota on this key is 2,000,000 per minute. A whole-log attempt made within a minute of other
  calls came back HTTP 429 RESOURCE_EXHAUSTED instead of the 400 (`runs/ep04/dryrun-A-whole-429.txt`, and the two
  `*-429.json` planning files). Wait a minute and send it again; `ask_log.py` has no retry.

## ep05

Measured 2026-09-26 before any script was written, then re-run on camera 2026-09-27. Every number the episode speaks
comes from a file below.

- Camera runs, terminal verbatim: `runs/ep05/2026-09-27-ep05-camera-a.txt` (`plan.py 512`, MAX_TOKENS),
  `-camera-c.txt` (`plan.py 512` with the check, stopped), `-camera-d1.txt` (`plan.py 2048`, STOP),
  `-camera-d2.txt` (`plan.py 512 low`, STOP, 0 thinking).
- The page owner line narrowed (`score.py --narrowed`): `runs/ep05/block4-gemini-3.8-flash-narrowed.json` (30, 30) and
  the re-check `runs/ep05/block5-*-narrowed.json` (3.8-flash low 30, 30; 3.1-flash-lite 25, 26; 3.5-flash-lite 26, 26).
- The temperature table (`measure/table.py temperature`) reads `runs/ep02/flip-probe-2026-09-15.json`.

- Models: `gemini-3.8-flash` (all blocks), `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3.1-pro-preview`.
  `modelVersion` in every response matched the id asked for. `gemini-pro-latest` was not used: it is not on the pricing
  page and its model resource names no concrete model (`runs/ep05/model-resource-gemini-pro-latest.json`).
- Prices (Standard paid tier, per million tokens, prompts <= 200k, thinking billed as output), from
  https://ai.google.dev/gemini-api/docs/pricing fetched 2026-09-26, text saved as `runs/ep05/2026-09-26-pricing.txt`:
  gemini-3.8-flash $0.75 in / $3.75 out (through 2026-12-31; $1.50 / $7.50 from 2027-01-01);
  gemini-3.5-flash-lite $0.30 / $2.50; gemini-3.1-flash-lite $0.25 / $1.50; gemini-3.1-pro-preview $2.00 / $12.00.
- Harness (not episode code): `measure/record.py` saves each call with the generationConfig sent, HTTP status,
  finishReason, full usageMetadata, modelVersion, text or error body, latency, UTC time, retries.
  `measure/score_runs.py` takes the prompt out of `score.py` itself, so it is the same prompt byte for byte.
- `plan.py`: the ep01 alert as a JSON action plan with `responseSchema`; optional output limit from argv.
- Run files, `runs/ep05/`:
  - `block1-pilot.json`: HTTP 402, prepaid credit depleted, before the top-up. No usage.
  - `block1-thinking-probe.json`: thinkingLevel minimal refused (HTTP 400), low/medium/high and thinkingBudget 0/128/1024/-1 accepted.
  - `block1-grid.json` (54 calls) and `block1-grid-1024.json` (6): maxOutputTokens x thinking level, 3 calls per cell.
  - `2026-09-26-plan-py-64.txt`, `2026-09-26-plan-py-512.txt`: `plan.py` itself, terminal verbatim (KeyError, JSONDecodeError).
  - `block3-pilot-*.json`, `block3-gemini-*.json`: the thirty at the API-default thinking, 3/2/2/1 runs.
  - `block2-pilot-{low,high}.json`, `block2-gemini-3.8-flash-low.json`, `block2-gemini-3.8-flash-high-run{1,2}.json`:
    the thirty at thinkingLevel low (2 runs) and high (2 runs); the default is the Block 3 3.8-flash file (3 runs).
- Spend for all of it: $1.43. Findings and tables: `content/ai-engineering-course/qc/ep05/measure.md` in the vivek-ai repo.

## ep06

Measured 2026-09-29/30 before the script was final, then run on camera 2026-09-30. Every number the episode speaks
comes from a file below.

- Camera runs, terminal verbatim: `runs/ep06/2026-09-30-ep06-camera-a.txt` (`tools.py payments-provider-timeout`:
  `check_provider('card provider')` refused, `'card-provider'` ran, 3 calls), `-camera-b.txt` (`triage.py`: the answer
  in a ```json fence, JSONDecodeError; `-camera-b-r1.txt` is the first take, same result, re-recorded for framing),
  `-camera-c.txt` (`triage.py schema`: bare JSON, parsed), `-camera-d.txt` (`tools.py payments-latency --list`:
  `list_deploys`, then `roll_back('d-2989')`, the id the lookup printed).
- The two tables on screen are `measure/ep06_screen.py shape` and `names`, printed from the saved runs below (no API call).
- Run files, `runs/ep06/`, all `gemini-3.8-flash` at thinkingLevel low, the thirty alerts, `rules.py` SYSTEM:
  - `*-shape-prompt-*` (3 runs): JSON asked for in the prompt only, 0 of 30 parsed each run, all 90 in a fence.
  - `*-shape-json-*`, `*-shape-schema-*`: JSON mode, and JSON mode + responseSchema: 30 of 30 parsed, 28 first moves right.
  - `*-calls-*`: the first tool call only, plain strings (AUTO) and enum names (AUTO / ANY / VALIDATED).
  - `*-loop-free-*` (3 runs): the loop with plain-string names, 140 tool calls, 14 made-up provider names, 14 refused,
    14 fixed on the next call. `*-loop-enum-*` (2 runs): names as an enum, 92 tool calls, 0 made up.
  - `*-sig-*`: the second turn sent back without the model's thoughtSignature: HTTP 400.
  - `dry-2026-09-30/`: the on-screen commands run once before the camera takes.
- Harness (not episode code): `measure/ep06.py` records every call; `measure/ep06_table.py` counts from the files.
- Prices as for ep05 (gemini-3.8-flash $0.75 in / $3.75 out per million, thinking billed as output). Spend for all of
  it: 654 calls, $0.98.
