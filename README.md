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
    python3 measure/ep06_screen.py shape   # the tables on screen, from runs/ep06 (also: names)

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

The map the course follows: [Andrew Ng's AI Engineering Skills Map](https://www.deeplearning.ai/the-batch/the-ai-engineering-skills-map)

Model ids and the prices behind the cost line are pinned in [PROVENANCE.md](PROVENANCE.md).
