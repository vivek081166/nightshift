"""Count the tokens in the log before you send it. Counting is free."""
import json, os, sys, time, urllib.request

MODEL = "gemini-3.8-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}"
HEADERS = {"x-goog-api-key": os.environ["GEMINI_API_KEY"],
           "content-type": "application/json"}


def get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    return json.load(urllib.request.urlopen(req))


def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), HEADERS)
    return json.load(urllib.request.urlopen(req))


t0 = time.time()
limit = get(URL)["inputTokenLimit"]
log = "\n".join(sys.stdin.read().splitlines())
body = {"contents": [{"parts": [{"text": log}]}]}
tokens = post(f"{URL}:countTokens", body)["totalTokens"]
print(f"log             {tokens:,} tokens")
print(f"context window  {limit:,} tokens  (inputTokenLimit)")
print(f"{tokens / limit:.2f}x")
print(f"{MODEL} · countTokens · free · {time.time() - t0:.1f} s")
