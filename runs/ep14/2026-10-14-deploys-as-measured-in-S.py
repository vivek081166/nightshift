"""Ask a question about deploys. The model writes one query; this code runs it on the deploy table.

    python3 deploys.py "how many deploys went out last week?"
    python3 deploys.py --cost "<question>"    # the same, and the cost line
"""
import json, os, sqlite3, sys, textwrap, time, urllib.request
import lookup
from rules import SYSTEM

DB = "deploys/deploys.db"
TODAY = "Today is Monday 2026-10-12 (JST). Last week means Monday 2026-10-05 to Sunday 2026-10-11."
WIDTH = min(55, lookup.SCREEN) - 1
SHAPE = {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]}


def table():
    """the table's CREATE line and its first three rows: what the model is told about the table"""
    db = open_db()
    create = db.execute("SELECT sql FROM sqlite_master WHERE name = 'deploys'").fetchone()[0]
    rows = db.execute("SELECT * FROM deploys LIMIT 3").fetchall()
    return create + "\n" + "\n".join(str(r) for r in rows)


def open_db():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)    # read-only: no query can change the table


def ask(question):
    system = (SYSTEM + "\n" + TODAY + "\nThe deploy history is one SQLite table:\n\n" + table() +
              "\n\nWrite one SQLite SELECT that answers the question.")
    reply = call({"systemInstruction": {"parts": [{"text": system}]},
                  "contents": [{"role": "user", "parts": [{"text": "Question from the on-call engineer:\n" + question}]}],
                  "generationConfig": {"responseMimeType": "application/json", "responseSchema": SHAPE}})
    text = "".join(part.get("text", "") for part in reply["parts"] if not part.get("thought"))
    return json.loads(text)["sql"]


def call(body):
    body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "low"}
    req = urllib.request.Request(f"{lookup.API}/models/{lookup.MODEL}:generateContent", json.dumps(body).encode(),
                                 {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "content-type": "application/json"})
    reply = json.load(urllib.request.urlopen(req))
    lookup.used.append(reply["usageMetadata"])
    return reply["candidates"][0]["content"]


def refuse(sql):
    """None if the query may run, otherwise why not"""
    words = sql.strip().rstrip(";").lower()
    if ";" in words:
        return "more than one statement"
    if not words.startswith(("select", "with")):
        return "not a SELECT"
    return None


def run(sql):
    return open_db().execute(sql).fetchall()     # one statement only: execute refuses two


def show(sql, rows):
    for line in sql.strip().split("\n"):
        print("\n".join(textwrap.wrap(line, WIDTH, subsequent_indent="  ")))
    print()
    for r in rows:
        print("  ".join(str(v) for v in r))


if __name__ == "__main__":
    t0 = time.time()
    question = " ".join(a for a in sys.argv[1:] if not a.startswith("--"))
    sql = ask(question)
    why = refuse(sql)
    if why:
        print(sql)
        print("refused:", why)
    else:
        show(sql, run(sql))
    if "--cost" in sys.argv:
        print(lookup.cost_line(time.time() - t0))
