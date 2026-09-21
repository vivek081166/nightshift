"""Ask all thirty alerts once, and count how many first actions match the one you wanted.

    python3 score.py

Prints the score, then the ones it got wrong. The total tells you almost nothing on its
own; the list underneath is the part you read.
"""
import json, os, re, time, urllib.request

CASES = json.load(open("tickets/incidents.json"))
ACTIONS = ["roll back", "read logs", "check provider", "page owner", "no action"]

# What the five actions mean here. Empty until you have read the misses once.
RULES = """At this company the five actions mean:
- roll back: undo the most recent deploy, when that deploy is recent enough to be the cause.
- read logs: go and read the service's own output, when nobody knows yet what happened.
- check provider: look at an outside service we depend on, when the alert already points at one.
- page owner: wake the person who owns this service, when money, customer data or account access is involved, or when somebody has to make a decision you are not allowed to make.
- no action: write it down and move on, when nothing has failed and no customer is affected.
"""

MODEL = "gemini-3.8-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
PRICE_IN, PRICE_OUT = 0.75, 3.75    # dollars per million tokens


def prompt(alert):
    return (f"You are the on-call assistant. Alert:\n{alert}\n{RULES}"
            f"Reply with exactly one of these and nothing else: {', '.join(ACTIONS)}.")


def ask(text):
    body = {"contents": [{"parts": [{"text": text}]}]}
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"],
                 "content-type": "application/json"},
    )
    r = json.load(urllib.request.urlopen(req))
    answer = "".join(p["text"] for p in r["candidates"][0]["content"]["parts"])
    usage = r["usageMetadata"]
    return answer, usage["promptTokenCount"], usage["candidatesTokenCount"] + usage.get("thoughtsTokenCount", 0)


score, missed, tokens_in, tokens_out, t0 = 0, [], 0, 0, time.time()
for case in CASES:
    answer, n_in, n_out = ask(prompt(case["alert"]))
    got = answer.strip().lower().strip(".")
    tokens_in, tokens_out = tokens_in + n_in, tokens_out + n_out
    if got == case["want"]:
        score += 1
    else:
        missed.append((case["id"], case["want"], got if got in ACTIONS else repr(answer.strip())))

print(f"\n{score} / {len(CASES)}\n")
print("missed:")
for name, want, got in missed:
    print(f"  {name:26} wanted {want:15} got {got}")

cost = (tokens_in * PRICE_IN + tokens_out * PRICE_OUT) / 1e6
print(f"\n{MODEL} · {tokens_in:,} in / {tokens_out:,} out · ${cost:.4f} · {time.time() - t0:.1f} s")
