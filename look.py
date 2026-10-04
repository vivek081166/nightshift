"""Ask the model one question about a picture, a PDF, or a file of numbers.

    python3 look.py arch/latency.png "At what time was payments v2.31 deployed?"
    python3 look.py arch/latency.png "At what time was payments v2.31 deployed?" --detail low
    python3 look.py postmortems/payments-timeout.pdf "At what time was payments v2.31 deployed?"
    python3 look.py arch/latency.csv "What was the highest payments p95 latency of the night, in milliseconds?"
"""
import base64, json, os, sys, time, urllib.request
from pathlib import Path

MODEL = "gemini-3.8-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
PRICE_IN, PRICE_OUT = 0.75, 3.75   # dollars per million tokens; thinking is billed as out
TYPES = {".png": "image/png", ".pdf": "application/pdf"}
SHORT = "Reply with only the answer, as short as possible. No explanation."


def look(path, question, detail=None):
    file = Path(path)
    if file.suffix == ".csv":
        label, first = "text", {"text": file.read_text()}          # the numbers themselves, as text
    else:
        label = TYPES[file.suffix]                                 # what kind of file it is
        first = {"inline_data": {"mime_type": label,
                                 "data": base64.b64encode(file.read_bytes()).decode()}}   # the file's bytes, as text
    parts = [first, {"text": f"{question}\n{SHORT}"}]
    config = {"thinkingConfig": {"thinkingLevel": "low"}}
    if detail:
        config["mediaResolution"] = f"MEDIA_RESOLUTION_{detail.upper()}"   # how many tokens the picture may become
    body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": config}
    print(f"sending {path} as {label}")
    req = urllib.request.Request(URL, json.dumps(body).encode(),
                                 {"x-goog-api-key": os.environ["GEMINI_API_KEY"],
                                  "content-type": "application/json"})
    return json.load(urllib.request.urlopen(req))


def cost_line(usage, secs):
    n_in = usage["promptTokenCount"]
    n_out = usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)
    image = sum(d["tokenCount"] for d in usage.get("promptTokensDetails", []) if d["modality"] in ("IMAGE", "DOCUMENT"))
    of_them = f" (image {image:,})" if image else ""
    return (f"{MODEL} · {n_in:,} in{of_them} / {n_out:,} out · "
            f"${(n_in * PRICE_IN + n_out * PRICE_OUT) / 1e6:.4f} · {secs:.1f} s")


if __name__ == "__main__":
    detail = sys.argv[sys.argv.index("--detail") + 1] if "--detail" in sys.argv else None
    t0 = time.time()
    r = look(sys.argv[1], sys.argv[2], detail)
    print("".join(p["text"] for p in r["candidates"][0]["content"]["parts"] if not p.get("thought")))
    print(cost_line(r["usageMetadata"], time.time() - t0))
