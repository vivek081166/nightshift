"""Ask the model one question about the team's pages, and print which pages it opened.

    python3 lookup.py "<question>"            # look it up: the call sends a contents list, the model opens pages
    python3 lookup.py --carry "<question>"    # carry it all: every page goes in the call
    python3 lookup.py --list                  # the contents list, exactly as the call sends it
    python3 lookup.py --dates ...             # each line of the list ends with the day the page last changed
"""
import json, os, re, shutil, sys, textwrap, time, urllib.request
from pathlib import Path
from rules import SYSTEM

MODEL = "gemini-3.8-flash"
API = "https://generativelanguage.googleapis.com/v1beta"
PRICE_IN, PRICE_OUT = 0.75, 3.75                       # dollars per million tokens; thinking is billed as out
INDEX = json.load(open("library/INDEX.json"))         # every page: id, title, last updated, where its text lives
ASK = "Question from the on-call engineer:\n{q}\nAnswer from the pages. If the pages do not say, say so."
READ_PAGE = {"name": "read_page", "description": "Read one of the team's pages by its id from the contents list.",
             "parameters": {"type": "object", "properties": {
                 "id": {"type": "string", "description": "the page id, exactly as the contents list gives it"}},
                 "required": ["id"]}}
used = []
SCREEN = shutil.get_terminal_size((89, 24)).columns   # the terminal's width; 89 under a pipe


def handbook():
    """the handbook, one page per '## ' section; page 1 also carries the revision line and the title"""
    first, rest = Path("runbooks/handbook.md").read_text().split("\n## ", 1)
    intro = first.split("\n")[0] + "\n\n" + first[first.index("# Sorrel"):].strip() + "\n\n"
    sections = ["## " + s for s in rest.split("\n## ")]
    return {"handbook-" + re.match(r"## (\d+)\.", s).group(1): (intro if i == 0 else "") + s.strip() + "\n"
            for i, s in enumerate(sections)}


def pages():
    """every page in the list's order, skipping any page whose file is gone"""
    hb, out = handbook(), []
    for row in INDEX:
        if row["id"] in hb:
            out.append({**row, "text": hb[row["id"]]})
        elif Path(row["source"]).exists():
            out.append({**row, "text": Path(row["source"]).read_text()})
    return out


def contents_list(pages, dates=False):
    return "\n".join(f"{p['id']}: {p['title']}" + (f" (last updated {p['updated']})" if dates else "") for p in pages)


def call(body):
    body["generationConfig"] = {"thinkingConfig": {"thinkingLevel": "low"}}
    req = urllib.request.Request(f"{API}/models/{MODEL}:generateContent", json.dumps(body).encode(),
                                 {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "content-type": "application/json"})
    reply = json.load(urllib.request.urlopen(req))
    used.append(reply["usageMetadata"])
    return reply["candidates"][0]["content"]


def look_it_up(question, pages, dates=False):
    system = (SYSTEM + "\nThe team's pages are listed below, one per line as id: title. To read a page, call "
              "read_page with its id. You may read up to 4 pages.\n\n" + contents_list(pages, dates))
    by_id = {p["id"]: p for p in pages}
    turns = [{"role": "user", "parts": [{"text": ASK.format(q=question)}]}]
    opened = 0
    while True:
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": turns,
                "tools": [{"functionDeclarations": [READ_PAGE]}]}
        if opened >= 4:
            body["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}       # four pages opened: now it answers
        reply = call(body)
        asks = [part["functionCall"] for part in reply["parts"] if "functionCall" in part]
        if not asks:
            return "".join(part.get("text", "") for part in reply["parts"] if not part.get("thought"))
        turns.append(reply)                                                      # its turn goes back as it came
        answers = []
        for ask in asks:
            page_id = ask["args"]["id"]
            if opened >= 4:
                page = {"error": "read limit reached: 4 pages. Answer from the pages you have read."}
            elif page_id in by_id:
                print("opened ", page_id)
                opened += 1
                page = {k: by_id[page_id][k] for k in ("id", "title", "text")}  # my code sends the page back
            else:
                page = {"error": f"no page with id {page_id!r}"}
            answers.append({"functionResponse": {"name": "read_page", "response": page,
                                                 **({"id": ask["id"]} if "id" in ask else {})}})
        turns.append({"role": "user", "parts": answers})


def carry(question, pages):
    others = [p for p in pages if not p["id"].startswith("handbook-")]
    system = Path("runbooks/handbook.md").read_text() + "\n\nThe team's other pages follow.\n" + "".join(
        f"\n----- page: {p['title']} -----\n\n{p['text']}" for p in others)               # every page, whole
    print("carried  every page")
    reply = call({"systemInstruction": {"parts": [{"text": system}]},
                  "contents": [{"role": "user", "parts": [{"text": ASK.format(q=question)}]}]})
    return "".join(part.get("text", "") for part in reply["parts"] if not part.get("thought"))


def show(answer, most=30):
    """the answer wrapped to the screen, at most 30 lines, but a code block is never cut or wrapped"""
    lines, in_code = [], False
    for line in answer.strip().split("\n"):
        if line.lstrip().startswith("```"):
            in_code = not in_code
        if in_code or line.lstrip().startswith("```"):
            lines.append((line, True))
        else:
            indent = " " * (len(line) - len(line.lstrip()) + (2 if re.match(r"\s*([*-]|\d+\.) ", line) else 0))
            lines += [(w, False) for w in textwrap.wrap(line, min(88, SCREEN - 1), subsequent_indent=indent, break_on_hyphens=SCREEN > 88) or [""]]
    shown = 0
    for i, (line, code) in enumerate(lines):
        if shown >= most and not code:
            print(f"... {len(lines) - i} more lines")
            break
        print(line)
        shown += 1


def cost_line(secs):
    sent = sum(u["promptTokenCount"] for u in used)
    out = sum(u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0) for u in used)
    usd = (sent * PRICE_IN + out * PRICE_OUT) / 1e6
    line = f"{MODEL} · {len(used)} calls · {sent:,} sent / {out:,} out · ${usd:.4f} · {secs:.0f} s"
    cut = line.rfind(" · ", 0, SCREEN + 2)                 # a narrow screen: two rows, split at the last " · " that fits
    return line[:cut] + "\n" + line[cut + 3:] if len(line) > SCREEN - 1 and cut > 0 else line


if __name__ == "__main__":
    t0 = time.time()
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    question = " ".join(a for a in sys.argv[1:] if not a.startswith("--"))
    if "--list" in flags:
        print(contents_list(pages(), dates="--dates" in flags))
    else:
        answer = carry(question, pages()) if "--carry" in flags else look_it_up(question, pages(), "--dates" in flags)
        show(answer)
        print(cost_line(time.time() - t0))
