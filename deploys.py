"""Ask a question about deploys. The model writes one query; this code runs it on the deploy table.

    python3 deploys.py "how many deploys went out last week?"
    python3 deploys.py --plain "<question>"   # the model sees only the CREATE line and three rows
    python3 deploys.py --cost "<question>"    # the same, and the cost line
    python3 deploys.py --saved "<question>"   # no model call: rerun the query the model wrote in the saved run
"""
import json, os, re, sqlite3, sys, time, urllib.request
import lookup
from rules import SYSTEM

DB = "deploys/deploys.db"
TODAY = "Today is Monday 2026-10-12 (JST). Last week means Monday 2026-10-05 to Sunday 2026-10-11."
WIDTH = min(55, lookup.SCREEN) - 1
SHAPE = {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]}
SAVED = {"plain": "runs/ep14/2026-10-14-s-sql.json", "words": "runs/ep14/2026-10-14-s2-words.json"}


def table():
    """the table's CREATE line and its first three rows: what the model is told about the table"""
    db = open_db()
    create = db.execute("SELECT sql FROM sqlite_master WHERE name = 'deploys'").fetchone()[0]
    rows = db.execute("SELECT * FROM deploys LIMIT 3").fetchall()
    return create + "\n" + "\n".join(str(r) for r in rows)


# what each column holds, in plain words: the model reads these next to the CREATE line
COLUMNS = {
    "id": "d-NNNN = a deploy in the old deploy tool; r-NNN = a Shipyard release (api and payments since 2026-09-28)",
    "service": "the one service the deploy changed",
    "started": "when it started going out, JST, YYYY-MM-DDTHH:MM",
    "finished": "when it stopped going out, JST, YYYY-MM-DDTHH:MM",
    "author": "who wrote the change",
    "state": "live = running now; superseded = went out, later replaced; rolled back = went out, then undone; "
             "failed = started, never finished going out",
    "note": "what changed, in a few words",
}


def words_in_table(db):
    """every value of each short text column: the exact words a WHERE has to match"""
    out = []
    for name in [c[1] for c in db.execute("PRAGMA table_info(deploys)")]:
        if db.execute(f"SELECT COUNT(DISTINCT {name}) FROM deploys").fetchone()[0] < 10:
            values = [v for (v,) in db.execute(f"SELECT DISTINCT {name} FROM deploys ORDER BY {name}")]
            out.append(f"{name}: " + ", ".join(repr(v) for v in values))
    return "\n".join(out)


def table_with_words():
    """the CREATE line with a comment per column, three rows, and the words the short columns use"""
    db = open_db()
    cols = [(name, kind) for _, name, kind, *_ in db.execute("PRAGMA table_info(deploys)")]
    lines = [f"  {name} {kind}{',' if i < len(cols) - 1 else ''} -- {COLUMNS[name]}" for i, (name, kind) in enumerate(cols)]
    rows = db.execute("SELECT * FROM deploys LIMIT 3").fetchall()
    return ("CREATE TABLE deploys (\n" + "\n".join(lines) + "\n)\n" + "\n".join(str(r) for r in rows) +
            "\n\nThe only values in these columns:\n" + words_in_table(db))


def open_db():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)    # read-only: no query can change the table


def ask(question, words=True):
    system = (SYSTEM + "\n" + TODAY + "\nThe deploy history is one SQLite table:\n\n" +
              (table_with_words() if words else table()) +
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


def saved(question, words=True):
    """the query the model wrote for this question in the saved run: no model call"""
    items = json.load(open(SAVED["words" if words else "plain"]))["items"]
    return next(item["sql"] for item in items if item["question"] == question)


def wrap(line):
    """lines of at most WIDTH characters; a quoted value like 'rolled back' never splits"""
    out, now = [], ""
    for word in re.findall(r"'[^']*'\S*|\S+", line):
        if now and len(now) + 1 + len(word) > WIDTH:
            out.append(now)
            now = "  " + word
        else:
            now = f"{now} {word}" if now else word
    return out + [now]


def show(sql, rows):
    for line in sql.strip().split("\n"):
        print("\n".join(wrap(line)))
    print()
    for r in rows:
        print("  ".join(str(v) for v in r))


if __name__ == "__main__":
    t0 = time.time()
    question = " ".join(a for a in sys.argv[1:] if not a.startswith("--"))
    words = "--plain" not in sys.argv
    sql = saved(question, words) if "--saved" in sys.argv else ask(question, words)
    why = refuse(sql)
    if why:
        print(sql)
        print("refused:", why)
    else:
        show(sql, run(sql))
    if "--cost" in sys.argv:
        print(lookup.cost_line(time.time() - t0))
