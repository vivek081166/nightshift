"""Find the team's pages for a question: by its words, by its meaning, or both.

    python3 search.py --keyword "<question>"    # pages that hold the question's words, rare words counting most
    python3 search.py --meaning "<question>"    # pages whose meaning sits closest (one embedding call: the question)
    python3 search.py --both "<question>"       # the two lists merged
"""
import hashlib, json, math, os, re, sys, urllib.request
from collections import Counter
from pathlib import Path
import lookup

EMBED = "gemini-embedding-2"
QUERY = "task: search result | query: "    # the docs' wording for a search query
VECTORS = Path("search/vectors.json")
LIMIT = 8192 * 3          # the embedding model reads 8,192 tokens; at about 3 characters a token, a piece this long fits
K1, B = 1.5, 0.75         # BM25's usual settings: how fast repeats stop counting, how much a long page is held back
used = []


def words(text):
    """lowercase words; a code like pay-4031 counts whole and as its parts"""
    out = []
    for w in re.findall(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*", text.lower()):
        out.append(w)
        if not w.isalnum():
            out += re.split(r"[-_.]", w)
    return out


def keyword_search(question, pages, n=5):
    """a rare word counts far more than a common one"""
    docs, holds, avg = count_words(pages)
    scores = []
    for p, d in zip(pages, docs):
        score = 0
        for w in set(words(question)):
            if w in d:
                rare = rarity(holds[w], len(docs))
                score += rare * repeats(d, w, avg)
        if score > 0:
            scores.append((score, p))
    return best_first(scores, n)


def meaning_search(question, pages, n=5):
    """the pages whose numbers sit closest"""
    vecs = page_vectors(pages)    # each page's numbers
    q = embed(QUERY + question)   # question's numbers
    scores = []
    for p in pages:
        near = max(cosine(q, v) for v in vecs[p["id"]])
        scores.append((near, p))
    return best_first(scores, n)


def count_words(pages):
    """each page's word counts, how many pages hold each word, and the average page length in words"""
    docs = [Counter(words(p["title"] + "\n" + p["text"])) for p in pages]
    holds = Counter(w for d in docs for w in d)                  # word -> how many pages hold it
    return docs, holds, sum(sum(d.values()) for d in docs) / len(docs)


def rarity(held, total):
    """BM25's weight for a word: the fewer pages hold it, the bigger"""
    return math.log(1 + (total - held + 0.5) / (held + 0.5))


def repeats(d, w, avg):
    """BM25: each repeat of a word on a page counts less than the last, and a long page is held back a little"""
    return d[w] * (K1 + 1) / (d[w] + K1 * (1 - B + B * sum(d.values()) / avg))


def best_first(scores, n):
    return [p for score, p in sorted(scores, key=lambda s: -s[0])][:n]


def page_vectors(pages):
    """one vector per page (per piece, if long), kept on disk: a page that has not changed is never sent again"""
    saved = json.loads(VECTORS.read_text()) if VECTORS.exists() else {}
    for p in pages:
        key = p["id"] + " " + hashlib.md5(p["text"].encode()).hexdigest()
        if key not in saved:
            saved[key] = [embed(f"title: {p['title']} | text: {piece}") for piece in pieces(p["text"])]
            VECTORS.write_text(json.dumps(saved))
    return {p["id"]: saved[p["id"] + " " + hashlib.md5(p["text"].encode()).hexdigest()] for p in pages}


def pieces(text):
    """a page longer than the model reads is cut at its '## ' headings into pieces that fit"""
    if len(text) <= LIMIT:
        return [text]
    out = [""]
    for section in re.split(r"\n(?=## )", text):
        if out[-1] and len(out[-1]) + len(section) > LIMIT:
            out.append("")
        out[-1] += section + "\n"
    return out


def embed(text):
    body = {"content": {"parts": [{"text": text}]}}
    req = urllib.request.Request(f"{lookup.API}/models/{EMBED}:embedContent", json.dumps(body).encode(),
                                 {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "content-type": "application/json"})
    reply = json.load(urllib.request.urlopen(req))
    used.append(reply.get("usageMetadata", {}))
    return reply["embedding"]["values"]


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b)) / math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))


def both(question, pages, n=5):
    """reciprocal rank fusion: each list gives a page 1 / (60 + its rank there), and the two are added"""
    score = Counter()
    for ranked in (keyword_search(question, pages, len(pages)), meaning_search(question, pages, len(pages))):
        for rank, p in enumerate(ranked, 1):
            score[p["id"]] += 1 / (60 + rank)
    by_id = {p["id"]: p for p in pages}
    return [by_id[i] for i, s in score.most_common(n)]


if __name__ == "__main__":
    how = {"--keyword": keyword_search, "--meaning": meaning_search, "--both": both}
    flag = next((a for a in sys.argv[1:] if a in how), "--both")
    question = " ".join(a for a in sys.argv[1:] if not a.startswith("--"))
    for rank, p in enumerate(how[flag](question, lookup.pages()), 1):
        print(f"{rank}  {p['id']}")                                # the id is one row on a narrow screen
    if used:
        print(f"embedding · {sum(u.get('promptTokenCount', 0) for u in used):,} tokens in")
