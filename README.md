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

The map the course follows: [Andrew Ng's AI Engineering Skills Map](https://www.deeplearning.ai/the-batch/the-ai-engineering-skills-map)

Model ids and the prices behind the cost line are pinned in [PROVENANCE.md](PROVENANCE.md).
