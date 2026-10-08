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

Measured 2026-09-29/30, re-measured 2026-10-01 with the real provider names, and run on camera 2026-10-01. The
episode is tool calls only; `triage.py` and the `shape` runs are for the next one (structured output). Every number
the episode speaks comes from a file below.

- Camera runs in the episode, terminal verbatim (2026-10-01): `runs/ep06/2026-10-01-ep06v6-camera-a.txt`
  (`tools.py payments-provider-timeout`: `check_provider('card provider')` refused with our names, `'stripe'` ran,
  3 requests), `-ep06v6-camera-alist.txt` (the same alert with `--list`: `'stripe'` on the first request),
  `-ep06v6-camera-d.txt` (`tools.py payments-latency --list`: `read_logs`, then `roll_back('d-2989')`, the id the
  logs printed), `-ep06v6-table-fixes.txt` (`measure/ep06_screen.py fixes`: each made-up name and the next try).
- (2026-09-30, the old made-up ids, not in the episode) `runs/ep06/2026-09-30-ep06-camera-a.txt` (`'card-provider'`
  ran), `-camera-b.txt` (`triage.py`: the answer in a ```json fence, JSONDecodeError; `-camera-b-r1.txt` is the
  first take), `-camera-c.txt` (`triage.py schema`: bare JSON, parsed), `-camera-d.txt` (`list_deploys` first).
- `measure/ep06_screen.py fixes` is the screen in the episode and `names` prints the counts in its description, both
  from the saved runs below (no API call). `shape` prints the structured output tables.
- Run files, `runs/ep06/`, all `gemini-3.8-flash` at thinkingLevel low, the thirty alerts, `rules.py` SYSTEM:
  - `*-shape-prompt-*` (3 runs): JSON asked for in the prompt only, 0 of 30 parsed each run, all 90 in a fence.
  - `*-shape-json-*`, `*-shape-schema-*`: JSON mode, and JSON mode + responseSchema: 30 of 30 parsed, 28 first moves right.
  - `*-calls-*`: the first tool call only, plain strings (AUTO) and enum names (AUTO / ANY / VALIDATED).
  - (09-30, the OLD made-up ids, superseded for the episode by the 10-01 realnames runs below) `*-loop-free-*` (3 runs): the loop with plain-string names, 140 tool calls, 14 made-up provider names, 14 refused,
    14 fixed on the next call. `*-loop-enum-*` (2 runs): names as an enum, 92 tool calls, 0 made up.
  - `*-sig-*`: the second turn sent back without the model's thoughtSignature: HTTP 400.
  - `dry-2026-09-30/`: the on-screen commands run once before the camera takes.
- ⚠️ 2026-10-01 RE-MEASURE WITH REAL PROVIDER NAMES (the episode's numbers come from these, not the 09-30 loop runs):
  `sorrel/oncall.py` PROVIDERS changed from made-up ids (card-provider, sms-vendor, ...) to stripe, twilio, sendgrid,
  cloudflare, aws; the alerts were not changed. `*-loop-free-*-runrealnames{1,2,3}.json`: 131 tool calls, 14 made-up
  names, 14 refused, 14 fixed on the next call; `*-loop-enum-*-runrealnames{1,2}.json`: 91 tool calls, none made up;
  30 roll backs, all passed the check. `-runrealnames-pilot1.json` = the six provider alerts first. Spend $0.57.
  `measure/ep06_screen.py names|fixes` read only the realnames runs: the 09-30 loop runs used the old ids, and the
  current check would re-score them wrong. `tools.py`'s loop variables renamed (contents -> conversation, asks ->
  tool_calls), then `call` -> `ask_model` and the footer's "calls" -> "requests" (10-01 panel: "call" collided with
  "tool call"), logic unchanged. The counts come from measure/ep06.py's check, which also refuses on the alert's
  service and on minutes: 1 refusal per enum run that tools.py would have run; the name and roll back counts are the same.
- Harness (not episode code): `measure/ep06.py` records every call; `measure/ep06_table.py` counts from the files.
- Prices as for ep05 (gemini-3.8-flash $0.75 in / $3.75 out per million, thinking billed as output). Spend for all of
  it: 654 calls, $0.98.

## ep07

Structured output. Measured 2026-10-02, run on camera 2026-10-03. One prompt for the whole episode: `triage.py`'s
`ASK` (line 19) is the natural request, "Reply in JSON with the severity, the service, the first move, and why."
Every number the episode speaks comes from a file below.

- Camera runs in the episode, terminal verbatim (2026-10-03), `runs/ep07/2026-10-03-ep07-camera-*`:
  `-a.txt` (`cat answer.json` + `read.py`: the saved JSON-mode answer for payments-latency, `wake someone now: False`,
  `KeyError: 'first_move'`; no API call), `-b.txt` + `-b-read.txt` (`triage.py`, words only: the answer in a ```json
  fence, `JSONDecodeError ... line 1 column 1`), `-ball.txt` (`triage.py --all`: valid JSON 0 / 30), `-call.txt`
  (`triage.py json --all`: valid JSON 30 / 30, in my shape 0 / 30), `-d.txt` (`triage.py schema` + `read.py`: P1,
  roll back, `reason`; `wake someone now: True`), `-eall.txt` (`triage.py schema --all`: 30 / 30, 30 / 30, first move
  right 28 / 30; disk-slow-burn and notifier-night wanted no action, got read logs), `-values.txt` and `-choices.txt`
  (the two `measure/ep07_screen.py` screens, no API call). `-*-answer.json` / `-*-answers.json` = what each run saved.
- Run files, `runs/ep07/2026-10-02-*`, `gemini-3.8-flash` at thinkingLevel low, the thirty alerts, `rules.py` SYSTEM:
  - `shape-loose-prompt-run1`: the natural words only: 0 of 30 valid JSON, 30 of 30 open with ```json.
  - `shape-loose-json-run{1,2}`: JSON mode + the natural words: 30 of 30 valid both runs, 0 of 30 in my shape; severity
    never P1/P2/P3 in 60 of 60, the last field `why` in 60 of 60, run1 has 5 answers keyed `action` / `first move`.
  - `shape-loose-schema-run{1,2}`: the shape (responseSchema): 30 of 30 in my shape, 28 first moves right both runs,
    the same two wrong.
  - `shape-{prompt,json,schema}-run1`: the same three with every field and value spelled out in the words; there JSON
    mode alone already got 30 of 30 in my shape, so the episode never says the shape beat careful words.
  - `logprobs-gemini-3.8-flash.json`: Gemini refuses to show its choices (HTTP 400, "Logprobs is not enabled").
  - `candidates-qwen3-8b-4bit.json`: the choices screen, an open model (mlx-community/Qwen3-8B-4bit) on a laptop, not
    Gemini: after `{"severity": "` the top choice is `high` (0.990); with only P1/P2/P3 allowed, `P` is the one left.
  - `dry-2026-10-02/`: the on-screen commands run once before the camera takes.
- Spend: the measurement runs $0.17, the five camera runs that call the model $0.07.

## ep08

Images and PDFs. Measured 2026-10-03, run on camera 2026-10-04. `look.py` sends the file as the first part (its bytes
in base64 + `mime_type` from `TYPES`; a `.csv` goes as text) and the question second, `gemini-3.8-flash` at
thinkingLevel low. The dashboard (`arch/latency.png`, from `arch/make_graph.py`) and the postmortem
(`postmortems/payments-timeout.pdf`, from `postmortems/make_pdf.py`) are synthetic; the answers come from
`arch/latency.csv` and `postmortems/payments-timeout.truth.json`. Every number the episode speaks comes from a file below.

- Camera runs in the episode, terminal verbatim (2026-10-04), `runs/ep08/2026-10-04-ep08-camera-*`:
  `-a.txt` (`look.py arch/latency.png`, the duration question three times: 33, 35, 35 minutes; no 34, so "None of the
  three was right"; `(image 1,100)` on every cost line), `-d.txt` (`look.py arch/latency.csv`, the same question three
  times: 34, 34, 34), `-e.txt` (`look.py postmortems/payments-timeout.pdf "How many payments failed?"`: 1,184, sent as
  `application/pdf`, `(image 1,064)` for the 2 pages; then `measure/ep08_screen.py pdf`: 10 questions, 3 runs, right
  30 / 30, no API call), `-readings.txt` (`measure/ep08_screen.py readings`, no API call).
- The truth, 34 minutes: `arch/latency.csv` has 34 rows with `payments_p95_ms` over 2,000, one run of minutes from 02:28
  to 03:01. "Two seconds" is the question's threshold.
- Twenty minutes between time labels: `arch/make_graph.py` sets the x axis to `MultipleLocator(20)`, one minute per row.
- 1,184: the PDF's page 2 timeline prints "03:12 1,184 failed payments replayed from the retry queue."
  (`runs/ep08/2026-10-03-pdf-extracted.txt`); question P7 answered 1,184 in all 3 PDF runs and in both PDF calls of `look-probe2`.
- Run files, `runs/ep08/2026-10-03-*`, the file first and the question second:
  - `graph-A-run{1,2,3}`, `graph-res-high-run{1,2}`: `arch/latency.png` at 1,100 image tokens, the ten dashboard
    questions (Q1-Q10), 50 of 50 inside the tolerances fixed before any call (times +-2 min, ms +-10%, minutes +-3),
    0 exact. Minutes above 2 s: 35, 34, 35, 33, 34. These five are the readings screen.
  - `look-probe2`: `look.py`'s exact request bodies. The picture: 1,100 image tokens, 34 text tokens for the question;
    with graph-A and res-high, the duration answers on `latency.png` are 33 x3, 34 x4, 35 x4.
  - `look-probe`: `look.py`'s exact bodies for the deploy question, 10 at `--detail low` (264 image tokens), 5 at the
    default.
  - `graph-res-low-run{1,2}` (264 image tokens) and `graph-res-medium-run{1,2}` (527): 9 of 10 inside tolerance in each
    run; the default (1,100) had none outside.
  - `graph-csv-run1`: the numbers as text, 12 of 12 exact, minutes above 2 s = 34.
  - `pdf-pdf-run{1,2,3}`: the PDF, 1,064 image tokens, 10 questions, 30 of 30 right. `pdf-text-run1`: the extracted
    text instead, 10 of 10.
  - `graph-B-run{1,2,3}` is a different picture (`arch/latency-rate.png`), `graph-800-run{1,2}` the dashboard at 800 px,
    `graph-tokens.json` countTokens and the per-part resolution probe; none of them is a number in the episode.
- Harness (not episode code): `measure/ep08.py` records every call (requests saved without the base64, md5 kept).
- Spend: the measurement runs $0.66 (`2026-10-03-spend.json`), the two look.py probes $0.10, the seven camera calls $0.04.

## ep09

Prompt caching. Measured and run on camera 2026-10-05. `cache.py` sends `runbooks/handbook.md` (the five-action rules,
then the handbook: 13,338 tokens) as the systemInstruction and the ask above the alert as the contents,
`gemini-3.8-flash` at thinkingLevel low. The handbook is synthetic, written for the course (its company is made up); a
frozen copy is `runs/ep09/2026-10-05-handbook-frozen.md`. Every number the episode speaks comes from a file below.

- Camera runs in the episode, terminal verbatim (2026-10-05), `runs/ep09/2026-10-05-ep09-camera-*`:
  `-a.txt` (`cache.py`, thirty alerts: `cached 0` on all 30, so "not one of the thirty"), `-b.txt` (`cache.py
  --time-first`, ten alerts: `cached 0` on all 10), `-c.txt` (`cache.py --make`, ttl 300 s: `cached 13,338` on all 30),
  `-d.txt` (`cache.py --again` after the five minutes, before the fix: `403 PERMISSION_DENIED: CachedContent not found
  (or permission denied)`), `-e.txt` (the same terminal after the fix lines went into `again()`: the 403 from d, then
  `cache ran out: making it again`, a new cache, `cached 13,338`).
- "An earlier run", "a bit more than half": `m1-baseline` (`measure/ep09_screen.py hits`), the handbook first and nothing
  else changed: 7 of 30 calls reused 8,169 tokens of 13,386-13,413 sent (61 %), the first at call 15 (`api-region-dns`).
  The other runs set up the same way: `m3-serial` 5 of 30 (8,169 each), `m6-fixed` 7 of 30 (8,006 each, JSON schema
  mode), `m2-fix` + `m2-fix-ext` 2 of 30 (8,169 each): 21 of 120 across the four, none of them the whole handbook.
- "About a tenth": `2026-10-05-m0-docs-pricing.md`, gemini-3.8-flash input $0.75 per 1M tokens, context caching $0.075
  (both double on 2027-01-01; the ratio holds).
- "Doesn't guarantee you'll pay less": `2026-10-05-m0-docs-caching.md`, "Implicit caching (automatically enabled on
  Gemini 2.5 and newer models, no cost saving guarantee)". "The limit is an hour": the same page, "If not set, the TTL
  defaults to 1 hour".
- One changing line on top: `m2-time` 0 of 10 + `m2-time-ext` 0 of 20 (`It is now HH:MM:SS.` as the first line), and
  camera b.
- The cache you make: `m5-explicit` (ttl 300 s), 30 of 30 calls reused 13,338 tokens each; after `expireTime` the call, a
  GET and a DELETE each returned 403 PERMISSION_DENIED "CachedContent not found (or permission denied)". It never says
  the cache ran out.
- Module close (`measure/ep09_screen.py close`): `m6-fixed` (the automatic cache only, 7 of 30 reused) and
  `m7-explicit-scored` (the same prompt text, every call pointed at a cache made with it, 30 of 30 reused): both 27 of 30
  right against `tickets/incidents.json`, the same three missed (api-slo-edge, disk-slow-burn, notifier-vendor-quota).
  Bill $0.274 and $0.050 (18 %, "about a fifth"); the second counts making the cache ($0.0100, its tokens at the input
  rate: the docs list no charge for making one, so this is the run's assumption) and keeping it 82 s.
- Not numbers in the episode: calls that reused the handbook were not faster (`m1-baseline` median 3.07 s against
  2.96 s); `m4-*` (handbook cut to sizes from 0.7k to 9.2k tokens: nothing reused at 4.7k or below), `m3-burst-*`, `m6-bust`,
  `m6-plain`, `m5-explicit-small` (400 under the 1,024-token floor for a cache you make).
- Harness (not episode code): `measure/ep09.py` records every call.
- Spend: the measurement runs $3.33 (`2026-10-05-spend.json`), the camera takes $0.64 (a $0.3890, b $0.1387, c $0.1123,
  e $0.0036; d failed before any tokens).

## ep10

Carry it, or look it up. Measured 2026-10-07, run on camera 2026-10-07 and 2026-10-08. `gemini-3.8-flash` at
thinkingLevel low, raw HTTP. The team's pages are `runbooks/handbook.md` (revision 2026-10-07a) split into its 18 `## `
sections, plus the 49 pages in `library/` (old runbooks, handover notes, outage write-ups), listed in `library/INDEX.json`
order: 67 pages, 67 lines in the contents list. All of it is synthetic, written for the course (the company is made up);
`runs/ep10/2026-10-07-a-freeze.json` holds the md5 of every page as measured, and `measure/ep10_screen.py gate` checks
`lookup.py` against it (13 checks). The question is `sy-trap-how` in `tickets/questions.json`: "payments checkout errors
jumped right after the last deploy, 12 minutes ago. How exactly do I roll payments back?" Right and wrong are the hand
grades (`m4-hand-grades.json`, `m2-hand-grades.json`), not the code grades.

- Camera runs in the episode, terminal verbatim, `runs/ep10/*-ep10-camera-*`: `-a.txt` (looked up: `opened
  payments-rollback-runbook` alone, then `dtool revert sorrel/payments --to <previous deploy id> --drain-checkouts`),
  `-c.txt` (`--carry`: `carried  every page`, 162,037 sent, `shipyard rollback payments`), `-d.txt` (`--dates`: the old
  runbook first, then the Shipyard page, a Shipyard answer), `-e.txt` (the RETIRED line on line 1 of
  `library/payments-rollback-runbook.md`: old runbook, then Shipyard, a Shipyard answer), `-f.txt` (the old runbook moved
  to `retired/`: `opened  deploying-with-shipyard` first, a Shipyard answer), and the no-API screens `-list.txt`,
  `-sizes.txt`, `-questions.txt`. After the takes the notice came out and the page went back, so `library/` is the
  measured one.
- "Every time I asked, the model opened that page, and only that page": `m4-model-50`, both wordings of the trap x 5 runs,
  10 of 10 opened only `payments-rollback-runbook` and answered with `dtool`; 4,749-4,771 tokens sent a question.
- "Right, on every run": `m4-carry-50`, 10 of 10 right (Shipyard), 162,026-162,037 tokens sent a question.
- "More than thirty times as much text" (this question only): 162,037 / 4,771 = 34 (`measure/ep10_screen.py sizes`, run
  1 of `m4-carry-5`, `m4-carry-50`, `m4-model-50`; carrying the handbook + 4 pages sent 20,015). Over all twenty questions
  (`m2-carry-50` against `m2-model-50`) carrying sent about 17 times the text in total (median 28 times; 9 of 20 over 30).
  The input limit is 1,048,576 (`m0-models-get.json`), so every page fits.
- "Twenty different questions ... only two came back wrong": `m2-model-50`, 15 right, 2 wrong (the two trap wordings),
  1 half answered (`two-api-incident`: it said the pages don't give the count; the rollback-queue write-up does, and it
  never opened it), 2 the pages don't cover, where it said so. Carried (`m2-carry-50`): 18 right and the same 2 said so.
- The three changes, ten runs each, both wordings x 5: `m4-fix-dates` (`(last updated YYYY-MM-DD)` on every list line):
  7 right, 3 wrong, the old runbook opened first 10 of 10, then the Shipyard page 7. `m4-fix-notice` (`> RETIRED
  2026-09-28: payments no longer deploys or rolls back with dtool. See the page "Deploying with Shipyard".` above the
  title): 10 right, old runbook then Shipyard 10 of 10. `m4-fix-archived` (the old runbook out of the list and out of
  `read_page`): 10 right, the Shipyard page first 10 of 10 (once it also opened `handbook-11`).
- "When it opened only the old page, the answer was old too": 15 of 15 runs that opened only the old runbook were wrong
  (`m4-model-50` 10, `m4-fix-dates` 3, `m2-model-50` 2); 18 of 18 that also opened the Shipyard page were right
  (`m4-fix-dates` 7, `m4-fix-notice` 10, `m2-model-50` 1).
- Not numbers in the episode: with only the handbook, on the thirty alerts (`m3-carry-1` 29 of 30, `m3-model-1` 30 of 30,
  14,128 against 8,794 tokens an alert). My code picking pages by service name (`m4-code-50`, `m2-code-50`) never gave
  the old command, but found no page for 11 of 18 answerable questions. Median wall time over the twenty: carry 3.0 s,
  look it up 4.9 s.
- Harness (not episode code): `measure/ep10.py` records every call; `measure/ep10_screen.py` replays the saved runs.
- Spend: the measurement runs $3.05 (`2026-10-07-spend.json`: drafting the pages $1.03, M1 $0.16, M2 $0.62, M3 $0.60,
  M4 $0.64), the camera takes $0.17 (a $0.0057, c $0.1229, d $0.0231, e $0.0087, f $0.0051).
