"""Ask the model for the exact words it took from each page, then look for those words on that page.

    python3 check.py "<question>"          # keyword search's top five pages go in the call; each claim: found or not
    python3 check.py --cost "<question>"   # the same, and the cost line
    python3 check.py --saved "<question>"  # no call: the answer saved in the measured run, checked again
"""
import json, os, re, sys, textwrap, time, urllib.request
import lookup, search
from rules import SYSTEM

ASK = lookup.ASK + ("\nGive each claim, the id of the page it came from, and the exact words from that page it rests"
                    " on. Copy the words exactly. If no words on a page say it, leave the claim out and put it under"
                    " not_in_pages.")
CLAIM = {"type": "object", "properties": {"claim": {"type": "string"}, "page": {"type": "string"},
                                          "quote": {"type": "string"}}, "required": ["claim", "page", "quote"]}
SHAPE = {"type": "object", "properties": {"claims": {"type": "array", "items": CLAIM},
                                          "not_in_pages": {"type": "array", "items": {"type": "string"}}},
         "required": ["claims", "not_in_pages"]}
WIDTH = min(88, lookup.SCREEN - 1)                    # how wide the answer prints


def ask(question, pages):
    top = search.keyword_search(question, pages, 5)
    system = SYSTEM + "\nThe team's pages that matched the question follow, each with its id.\n" + "".join(
        f"\n----- page {p['id']}: {p['title']} -----\n\n{p['text']}" for p in top)
    reply = call({"systemInstruction": {"parts": [{"text": system}]},
                  "contents": [{"role": "user", "parts": [{"text": ASK.format(q=question)}]}],
                  "generationConfig": {"responseMimeType": "application/json", "responseSchema": SHAPE}})
    text = "".join(part.get("text", "") for part in reply["parts"] if not part.get("thought"))
    return json.loads(text), {p["id"]: p for p in top}


def saved(question, run="runs/ep13/2026-10-12-c2-quotes.json"):
    """the answer the measured run saved for this question, and the five pages it was sent with"""
    row = next(q for q in json.load(open(run))["questions"] if q["question"] == question)
    by_id = {p["id"]: p for p in lookup.pages()}
    return row["answer"], {i: by_id[i] for i in row["pages_in_call"]}


def call(body):
    body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "low"}
    req = urllib.request.Request(f"{lookup.API}/models/{lookup.MODEL}:generateContent", json.dumps(body).encode(),
                                 {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "content-type": "application/json"})
    reply = json.load(urllib.request.urlopen(req))
    lookup.used.append(reply["usageMetadata"])
    return reply["candidates"][0]["content"]


def found(quote, page):  # the find box
    return (squash(quote) in squash(page)
        or squash(plain(quote)) in squash(plain(page)))


def squash(text):
    return re.sub(r"\s+", " ", text.lower()).strip()


def plain(text):  # the words as you read them
    text = re.sub(r"(?m)^\s*([-*]|#+)\s+", "", text)
    text = re.sub(r"[*`#]", "", text)
    return text.translate(STRAIGHT)


STRAIGHT = str.maketrans({
    "\u201c": '"', "\u201d": '"', "\u2018": "'",
    "\u2019": "'", "\u2013": "-", "\u2014": "-"})


def show(answer, sent):
    for n, c in enumerate(answer["claims"], 1):
        page = sent.get(c["page"])
        ok = page and found(c["quote"], page["text"])
        mark = "found" if ok else "NOT ON THE PAGE"
        wrap(f"{n}. {c['claim']}", "   ")
        print(f"   {c['page']} · {mark}")
    if answer["not_in_pages"]:
        print("Not in the pages:")
        for line in answer["not_in_pages"]:
            wrap(f"- {line}", "  ")


def wrap(text, indent):
    rows = textwrap.wrap(text, WIDTH,
                         subsequent_indent=indent)
    print("\n".join(rows))


if __name__ == "__main__":
    t0 = time.time()
    question = " ".join(a for a in sys.argv[1:] if not a.startswith("--"))
    answer, sent = saved(question) if "--saved" in sys.argv else ask(question, lookup.pages())
    show(answer, sent)
    if "--cost" in sys.argv and "--saved" not in sys.argv:
        print(lookup.cost_line(time.time() - t0))
