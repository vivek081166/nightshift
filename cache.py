"""Send each alert with the on-call handbook in front, and print how much of every call the model reused.

    python3 cache.py                 # the automatic cache: the handbook first, the alert last, thirty alerts
    python3 cache.py --time-first    # the current time on the first line, above the handbook, ten alerts
    python3 cache.py --make          # make a cache with the handbook, then point every call at it
    python3 cache.py --again         # the first alert again, against the cache --make made
"""
import json, os, sys, time, urllib.error, urllib.request
from datetime import datetime
from pathlib import Path

MODEL = "gemini-3.8-flash"
API = "https://generativelanguage.googleapis.com/v1beta"
PRICE_IN, PRICE_CACHED, PRICE_OUT = 0.75, 0.075, 3.75    # dollars per million tokens; thinking is billed as out
HANDBOOK = Path("runbooks/handbook.md").read_text()       # the five rules, then the handbook: the text that never changes
ALERTS = json.load(open("tickets/incidents.json"))
ASK = "Reply in JSON with the severity, the service, the first move, and why."
LAST_CACHE = Path(".last_cache")
used = []


class APIError(Exception):
    def __init__(self, code, status, message):
        super().__init__(f"{code} {status}: {message}")
        self.code = code


def post(path, body):
    req = urllib.request.Request(f"{API}/{path}", json.dumps(body).encode(),
                                 {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "content-type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e:
        err = json.loads(e.read())["error"]
        raise APIError(err["code"], err["status"], err["message"]) from None


def make():
    cache = post("cachedContents", {"model": f"models/{MODEL}", "ttl": "300s",           # it lives five minutes
                                    "systemInstruction": {"parts": [{"text": HANDBOOK}]}})  # the handbook, sent once
    LAST_CACHE.write_text(cache["name"])
    print(f"made {cache['name']}, lives 5 min")
    return cache["name"]


def call(alert, first="", cache=None):
    body = {"contents": [{"role": "user", "parts": [{"text": f"{ASK}\nAlert:\n{alert}"}]}],   # the alert goes last
            "generationConfig": {"thinkingConfig": {"thinkingLevel": "low"}}}
    if cache:
        body["cachedContent"] = cache                                         # the handbook, by its name
    else:
        body["systemInstruction"] = {"parts": [{"text": first + HANDBOOK}]}   # the handbook, in full
    usage = post(f"models/{MODEL}:generateContent", body)["usageMetadata"]
    used.append(usage)
    return usage


def row(case, usage, first=""):
    sent, cached = usage["promptTokenCount"], usage.get("cachedContentTokenCount", 0)   # a miss has no cached count
    print(f"{first}{case['id']:28} sent {sent:,}   cached {cached:,}")


def again():
    case = ALERTS[0]
    try:
        usage = call(case["alert"], cache=LAST_CACHE.read_text())
    except APIError as e:
        if e.code != 403:                          # not found, or permission denied: the cache ran out
            raise
        print("cache ran out: making it again")
        usage = call(case["alert"], cache=make())
    row(case, usage)


def cost_line(secs):
    sent = sum(u["promptTokenCount"] for u in used)
    cached = sum(u.get("cachedContentTokenCount", 0) for u in used)
    out = sum(u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0) for u in used)
    usd = ((sent - cached) * PRICE_IN + cached * PRICE_CACHED + out * PRICE_OUT) / 1e6
    return f"{MODEL} · {sent:,} sent / {cached:,} cached / {out:,} out · ${usd:.4f} · {secs:.0f} s"


if __name__ == "__main__":
    t0 = time.time()
    if "--again" in sys.argv:
        again()
    elif "--time-first" in sys.argv:
        for case in ALERTS[:10]:
            first = f"It is now {datetime.now():%H:%M:%S}.\n"     # changes on every call
            row(case, call(case["alert"], first=first), first=first.strip() + "   ")
    else:
        name = make() if "--make" in sys.argv else None
        for case in ALERTS:
            row(case, call(case["alert"], cache=name))
    print(cost_line(time.time() - t0))
