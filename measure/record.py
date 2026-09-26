"""Measurement harness, not episode code: send one request, save everything about it.

Every call returns a dict with the model, the generationConfig sent, the HTTP status, finishReason,
the full usageMetadata, the text (or the error body verbatim), latency, UTC time, and any retries.
The key is read from the environment and never written anywhere.
"""
import json, os, socket, time, urllib.error, urllib.request
from datetime import datetime, timezone

# Dollars per million tokens, Standard paid tier, prompts <= 200k.
# Source: https://ai.google.dev/gemini-api/docs/pricing fetched 2026-09-26 (runs/ep05/2026-09-26-pricing.txt)
PRICES = {
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.1-pro-preview": (2.00, 12.00),
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.30, 2.50),
}


def cost(model, usage):
    """Dollars for one call, or None when the model's price is not on the page (UNVERIFIED)."""
    if model not in PRICES or not usage:
        return None
    p_in, p_out = PRICES[model]
    out = usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)
    return (usage.get("promptTokenCount", 0) * p_in + out * p_out) / 1e6


def send(model, text, config=None, extra=None):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {"contents": [{"parts": [{"text": text}]}]}
    if config is not None:
        body["generationConfig"] = config
    headers = {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "content-type": "application/json"}
    retries, net_retry_used = [], False
    while True:
        req = urllib.request.Request(url, json.dumps(body).encode(), headers)
        stamp, t0 = datetime.now(timezone.utc).isoformat(timespec="seconds"), time.time()
        try:
            raw = urllib.request.urlopen(req, timeout=300).read()
            status, r, err = 200, json.loads(raw), None
        except urllib.error.HTTPError as e:
            status, r, err = e.code, None, e.read().decode(errors="replace")
            if status == 429 and len(retries) < 5:
                retries.append({"why": "HTTP 429", "at": stamp, "body": err})
                time.sleep(60)
                continue
            if status in (500, 503) and not net_retry_used:
                net_retry_used = True
                retries.append({"why": f"HTTP {status}", "at": stamp, "body": err})
                time.sleep(5)
                continue
        except (urllib.error.URLError, socket.timeout, ConnectionError, TimeoutError) as e:
            if not net_retry_used:
                net_retry_used = True
                retries.append({"why": f"network: {e!r}", "at": stamp})
                time.sleep(5)
                continue
            status, r, err = None, None, f"network: {e!r}"
        secs = round(time.time() - t0, 3)
        break
    rec = {"model": model, "generationConfig": config, "http": status, "utc": stamp,
           "latency_s": secs, "retries": retries, "error": err}
    if r is not None:
        cand = (r.get("candidates") or [{}])[0]
        content = cand.get("content") or {}
        parts = content.get("parts")
        rec["finishReason"] = cand.get("finishReason")
        rec["usageMetadata"] = r.get("usageMetadata")
        rec["modelVersion"] = r.get("modelVersion")
        rec["text"] = "".join(p.get("text", "") for p in parts) if parts else ""
        # What a naive reader hits: r["candidates"][0]["content"]["parts"]
        try:
            r["candidates"][0]["content"]["parts"]
            rec["naive_parts"] = "ok"
        except (KeyError, IndexError, TypeError) as e:
            rec["naive_parts"] = f"{type(e).__name__}: {e}"
            rec["candidate_raw"] = cand
        rec["cost_usd"] = cost(model, rec["usageMetadata"])
    if extra:
        rec.update(extra)
    return rec


def save(path, records):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(records, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)
