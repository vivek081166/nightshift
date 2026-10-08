# Nightshift

The code from the AI Engineering course. One git tag per episode, so `git checkout ep01` gives you
exactly what is on screen in episode 1.

You can write a Python function and call an HTTP API. No machine learning needed.

## Run it

    export GEMINI_API_KEY=...
    python3 ten_runs.py           # one on-call alert, ten times, with the tally and the cost line
    python3 ask_all.py            # all thirty alerts, one sentence each, nothing you can count
    python3 score.py              # all thirty scored against the answers you wanted, and the misses
    node js/ep01/first_call.mjs   # the same first call in Node

    python3 ask_log.py < logs/sorrel-incident.log                # the whole log: refused, over the context window
    python3 count.py < logs/sorrel-incident.log                  # how many tokens it is, against what fits (free)
    tail -n 875 logs/sorrel-incident.log | python3 ask_log.py    # just the tail, with its cost line
    python3 around_errors.py | python3 ask_log.py                # only the lines around the errors

    python3 plan.py 512           # the plan as JSON, cut off by the output limit: the check stops it
    python3 plan.py 2048          # room above the thinking, the whole plan
    python3 plan.py 512 low       # the same limit, thinking low
    python3 score.py --narrowed   # the thirty with the page owner line narrowed
    python3 measure/table.py thinking   # the tables on screen, from runs/ (also: models, same, narrowed, temperature)

    python3 triage.py                 # JSON asked for in words: the answer comes back in backticks and json.loads fails
    python3 triage.py schema          # JSON mode and the shape: bare JSON, parsed (also: json; --all for the thirty)
    python3 tools.py payments-provider-timeout   # a tool call with a made-up name, refused, then fixed
    python3 tools.py payments-latency --list     # the names as a list: it looks around, then rolls back
    python3 tools.py --all            # all thirty: what the check refused, and what came next (--list for the names as a list)
    python3 measure/ep06_screen.py fixes   # each made-up name and the next try, from runs/ep06 (also: names, shape)
    python3 read.py answer.json       # my on-call code: wake someone now? and the first move (KeyError if the field is missing)
    python3 measure/ep07_screen.py values   # the names and values the answers had, from runs/ep07 (also: choices)
    python3 measure/ep07_shape.py count     # recount the episode's numbers from the saved runs, no API call

    python3 look.py arch/latency.png "For how many minutes in total was the payments p95 latency above 2 seconds?"   # the picture: a reading
    python3 look.py arch/latency.csv "For how many minutes in total was the payments p95 latency above 2 seconds?"   # the numbers as text
    python3 look.py postmortems/payments-timeout.pdf "How many payments failed?"   # the PDF: the number it prints
    python3 look.py arch/latency.png "At what time was payments v2.31 deployed?" --detail low   # fewer tokens for the picture
    python3 measure/ep08_screen.py readings   # every answer from five runs of the picture, and the truth, from runs/ep08 (also: pdf)

    python3 cache.py                  # thirty alerts, the handbook first: how much of each call the model reused (the automatic cache)
    python3 cache.py --time-first     # the current time on the first line, above the handbook: ten alerts
    python3 cache.py --make           # make a cache with the handbook (it lives 5 minutes), then point all thirty calls at it
    python3 cache.py --again          # one call to that cache; once it has run out: a 403, then it makes the cache again
    python3 measure/ep09_screen.py hits   # an earlier run of the thirty, from runs/ep09, no API call (also: close, the module close)

    python3 lookup.py "payments checkout errors jumped right after the last deploy, 12 minutes ago. How exactly do I roll payments back?"   # look it up: the contents list, the pages it opened, the answer
    python3 lookup.py --carry "<the same question>"   # carry it all: every page in the call
    python3 lookup.py --list                          # the contents list, exactly as the call sends it (--dates adds each page's last-updated day)
    python3 measure/ep10_screen.py sizes              # text sent with that question, from runs/ep10, no API call (also: trap, questions, tally, gate)

The `ep03` tag holds `score.py` as the episode leaves it, with RULES filled in. The first five runs in
the video used the same file with `RULES = ""` on line 14. Replace the RULES block with that one line
to run them yourself.

Every call is raw HTTP on purpose. No SDK, nothing to install past the key.
The demo calls Gemini. The OpenAI and Anthropic APIs take the same kind of request, and nothing in
the course depends on the vendor.

## Episodes

| Tag | Episode | What it adds |
|---|---|---|
| `ep01` | [AI Engineering Roadmap 2026](https://youtu.be/5dW1jMOYbMY) | The 40-line v0: one alert, ten runs, tokens and cost |
| `ep02` | [Ten Answers to One Question](https://youtu.be/o4MtpnO2Av8) | Fifty answers, the parser that drops four, and the alert whose verdict moves |
| `ep03` | [Your First Eval Set](https://youtu.be/r8X-KKHGxhc) | Thirty cases, the noise the score moves by, and one change measured against it |
| `ep04` | [Tokens and the Context Window](https://youtu.be/VFQ0xTwhi3Y) | Count a 40,000-line log (generated, `sorrel/make_logs.py`), send it whole and get refused, send the tail, then only the lines around the errors, with the cost of each |
| `ep05` | [Your LLM Cut Its Own Answer Short and Said OK](https://youtu.be/KRcB3oFzEWU) | `plan.py` gets cut off at 512 and still says HTTP 200; the finish-reason check; thinking low/default/high and four models on the thirty; the page owner line that every model followed too far |
| `ep06` | [LLM Tool Calling Explained: It Made Up a Name, My Code Said No](https://youtu.be/0qm6Zav9udM) | `tools.py`: six function descriptions, the check before any tool call runs, and the loop. A made-up provider name refused with the real ones and fixed on the next try; `--list` sends the names as an enum; roll back gets the strictest check. `triage.py` is the start of the next episode |
| `ep07` | [LLM Structured Output Explained: Valid JSON, and My Code Still Crashed (JSON Mode vs Schema)](https://youtu.be/N99lJy9cojs) | `triage.py` asks for the same answer three ways: in words only (backticks, valid JSON 0 of 30), with JSON mode (valid 30 of 30, in my shape 0 of 30) and with the shape (30 of 30, first move right 28 of 30). `read.py` is the on-call code that crashed. `measure/ep07_screen.py choices` shows an open model's choices crossed out by the shape |
| `ep08` | [Send Images and PDFs to an LLM: Why Chart Readings Change](https://youtu.be/_c2H98LSzKc) | `look.py` sends a picture or a PDF as its bytes in base64 plus a label for its type, next to the question. The dashboard picture gives a reading that moves (33, 35, 35; the truth is 34); the numbers as text give 34 every time; the PDF gives the number it prints (1,184), 30 of 30 right. `--detail low` sets how many tokens the picture becomes. `measure/ep08_screen.py` shows the readings and the PDF count |
| `ep09` | [Prompt Caching: Make a Cache That Hits Every Call (LLM Context Caching)](https://youtu.be/Cwb9SbTJCOk) | `cache.py` sends the handbook (`runbooks/handbook.md`, the five rules on top) first and the alert last, and prints how many tokens each call sent and how many the model reused. The automatic cache reused nothing on camera (0 of 30; 21 of 120 across four earlier runs, never the whole handbook); the time on the first line stops it (0 of 30); a cache you make (`--make`) is reused on 30 of 30; after its 5 minutes the call fails with 403 "CachedContent not found (or permission denied)", and `--again` makes the cache again. `measure/ep09_screen.py` shows the earlier run and the module close: 27 of 30 right both ways, the bill about a fifth |
| `ep10` | [RAG vs Long Context: I Tested Both on the Same Question](https://youtu.be/7BOy-hvyrlA) | `lookup.py` gives the model the team's 67 pages two ways: every page in the call (`--carry`), or a contents list of titles plus one function, `read_page`, and it prints each page the model opened. Looked up, the rollback question opened only the 2024 runbook and gave the retired command 10 of 10; carried, 10 of 10 right at 34 times the text. Dates in the list (`--dates`) 7 of 10, a RETIRED line on the old page 10 of 10, the old page moved out 10 of 10. `measure/ep10_screen.py` replays the saved runs |

The map the course follows: [Andrew Ng's AI Engineering Skills Map](https://www.deeplearning.ai/the-batch/the-ai-engineering-skills-map)

Model ids and the prices behind the cost line are pinned in [PROVENANCE.md](PROVENANCE.md).
