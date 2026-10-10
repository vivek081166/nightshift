"""EP11 scorer, written from the truth files BEFORE any extractor output was read. Frozen by md5 in the run files.

A page's text is normalised the same way for every method: markdown bold/italic markers, backslash escapes, <br>
and the table bar '|' become nothing or a space, then all whitespace collapses to one space. Matching is
case-sensitive.

ROW INTACT (strict, the number): the row's first cell is found, then each next cell is found after it, IN ORDER, each
cell as one contiguous string, and the text between them (the gaps) holds no cell of any other row of the same table.
So a cell whose words come out split by another column's words is not intact, and two rows run together are not intact.

ROW INTACT (loose, reported beside it): in the raw text, the span from a line that starts with the row's first cell
to the next line that starts with another row's first cell (or 1,500 characters) holds every word of every cell of
the row. Words may be split across lines or interleaved; order is not checked.

PAGE PARSED CORRECTLY = every table row on that page intact (strict) AND every key fact on that page present as an
exact string. Text methods are scored page by page against that page's own text; the model's markdown (P6) has no
page boundaries, so each page's rows and facts are looked for in the whole document.

INVENTED (P5, P6): every number and every capitalised word in the output that does not occur in the source text.
"""
import re

NUM = re.compile(r"\d+(?:[.,:/-]\d+)*")
CAP = re.compile(r"\b[A-Z][A-Za-z]{2,}\b")


def norm(s):
    s = s.replace("\f", "\n")
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|~>])", r"\1", s)
    s = s.replace("**", "").replace("__", "")
    s = s.replace("|", " ")
    return re.sub(r"\s+", " ", s).strip()


def _wb(s):
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(s) + r"(?![A-Za-z0-9])")


def row_intact_strict(text, row, others):
    """text: normalised. row: list of cells. others: the other rows of the same table."""
    cells = [norm(c) for c in row]
    own = " ".join(cells)
    foreign = {norm(c) for r in others for c in r if norm(c) and norm(c) not in own}
    foreign_re = [_wb(f) for f in sorted(foreign, key=len, reverse=True)]
    start = 0
    while True:
        i = text.find(cells[0], start)
        if i < 0:
            return False
        pos, ok = i + len(cells[0]), True
        for c in cells[1:]:
            j = text.find(c, pos)
            if j < 0:
                ok = False
                break
            gap = text[pos:j]
            if any(f.search(gap) for f in foreign_re):
                ok = False
                break
            pos = j + len(c)
        if ok:
            return True
        start = i + 1


def row_intact_loose(raw, row, others):
    lines = raw.replace("\f", "\n").split("\n")
    lead = lambda line: re.sub(r"^[\s|*#>-]+", "", line)
    first = norm(row[0])
    other_firsts = [norm(r[0]) for r in others if norm(r[0]) != first]
    words = set(re.findall(r"\S+", norm(" ".join(row))))
    for k, line in enumerate(lines):
        if not norm(lead(line)).startswith(first):
            continue
        span, n = [], 0
        for line2 in lines[k:]:
            if line2 is not line and any(norm(lead(line2)).startswith(o) for o in other_firsts) and span:
                break
            span.append(line2)
            n += len(line2)
            if n > 1500:
                break
        got = set(re.findall(r"\S+", norm(" ".join(span))))
        if words <= got:
            return True
    return False


def score_doc(truth, pages_raw, whole_doc=False):
    """pages_raw: list of raw page texts (len = truth pages), or one text when whole_doc."""
    n_pages = truth["pages"]
    if whole_doc:
        raw_for = lambda p: pages_raw[0]
    else:
        raw_for = lambda p: pages_raw[p - 1] if p - 1 < len(pages_raw) else ""
    out = []
    for p in range(1, n_pages + 1):
        raw = raw_for(p)
        text = norm(raw)
        rows, bad_rows, bad_rows_loose = 0, [], []
        for tab in truth["tables"]:
            for i, (row, pg) in enumerate(zip(tab["rows"], tab["page_of_row"])):
                if pg != p:
                    continue
                rows += 1
                others = tab["rows"][:i] + tab["rows"][i + 1:]
                if not row_intact_strict(text, row, others):
                    bad_rows.append({"table": tab["name"], "row": row})
                if not row_intact_loose(raw, row, others):
                    bad_rows_loose.append({"table": tab["name"], "row": row})
        facts = [f["text"] for f in truth["facts"] if f["page"] == p]
        missing = [f for f in facts if norm(f) not in text]
        out.append({"page": p, "rows": rows, "rows_intact": rows - len(bad_rows),
                    "rows_intact_loose": rows - len(bad_rows_loose), "facts": len(facts),
                    "facts_present": len(facts) - len(missing), "missing_facts": missing,
                    "bad_rows": bad_rows, "bad_rows_loose": [b["row"][0] for b in bad_rows_loose],
                    "chars": len(raw.strip()) if not whole_doc else None,
                    "correct": not bad_rows and not missing,
                    "correct_loose": not bad_rows_loose and not missing})
    return out


def invented(output, source_text):
    src_nums = set(NUM.findall(source_text))
    src_caps = set(CAP.findall(source_text))
    nums = sorted({n for n in NUM.findall(output) if n not in src_nums})
    caps = sorted({c for c in CAP.findall(output) if c not in src_caps})
    return {"numbers": nums, "words": caps}
