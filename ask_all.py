"""Ask all thirty alerts the question episodes 1 and 2 asked, and print what comes back.

    python3 ask_all.py

Thirty answers, thirty sentences. There is nothing here a program can count, which is
the reason score.py hands the model a list of five words instead.
"""
import json, os, time, urllib.request

CASES = json.load(open("tickets/incidents.json"))

MODEL = "gemini-3.8-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
PRICE_IN, PRICE_OUT = 0.75, 3.75    # dollars per million tokens


def ask(alert):
    prompt = (f"You are the on-call assistant. Alert:\n{alert}\n"
              "Reply in one line: P1 or P2, then the first action.")
    body = {"contents": [{"parts": [{"text": prompt}]}]}
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


answers, tokens_in, tokens_out, t0 = [], 0, 0, time.time()
for case in CASES:
    answer, n_in, n_out = ask(case["alert"])
    answers.append(answer.strip().splitlines()[0])
    tokens_in, tokens_out = tokens_in + n_in, tokens_out + n_out
    print(answers[-1])

cost = (tokens_in * PRICE_IN + tokens_out * PRICE_OUT) / 1e6
print(f"\n{len(answers)} answers, {len(set(answers))} of them different"
      f" · {tokens_in:,} in / {tokens_out:,} out · ${cost:.4f} · {time.time() - t0:.1f} s")
