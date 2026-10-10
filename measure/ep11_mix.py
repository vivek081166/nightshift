"""EP11 L-mix: per FILE, P1 (pypdf default) when P1 gave any characters, else P6 run 1. Same loop as l-P1 / l-P6.

    python3 measure/ep11_mix.py        # writes runs/ep11/2026-10-08-l-mix.json
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ep11  # noqa: E402  (chdir, key from .env, recorder, spend ledger)
from ep11 import (LIB_PDFS, PARSED, QUESTIONS, Stop, grade, lookup, md5, pdf_path, register_pages, run_lookup,  # noqa
                  save, spent, truth_of, report_set)


def mix_pages():
    pages, routes = lookup.pages(), {}
    for slug in LIB_PDFS:
        p1 = open(os.path.join(PARSED, "P1", slug + ".txt")).read()
        chars = len(p1.replace("\f", "").strip())
        if chars > 0:
            text = "\n\n".join(p.strip("\n") for p in p1.split("\f"))
            routes[slug] = {"route": "P1", "p1_chars": chars}
        else:
            text = open(os.path.join(PARSED, "P6-run1", slug + ".txt")).read()
            routes[slug] = {"route": "P6-run1", "p1_chars": chars}
        routes[slug]["text_md5"] = md5(text)
        pages.append({"id": slug, "title": truth_of(slug)["title"], "updated": None,
                      "source": os.path.relpath(pdf_path(slug), ep11.ROOT), "text": text})
    return pages, routes


def main():
    pages, routes = mix_pages()
    register_pages(pages, "mix")
    out = {"variant": "mix", "rule": "P1 output if P1 gave any characters for the file, else P6 run 1 output",
           "routes": routes, "pages": len(pages), "contents_list_md5": md5(lookup.contents_list(pages)),
           "questions": []}
    for q in QUESTIONS:
        r = run_lookup(q["question"], pages, "L-mix")
        r.update({"id": q["id"], "kind": q["kind"], "question": q["question"], "page": q["page"],
                  "opened_right_page": q["page"] in r["opened"] if q["page"] else None, **grade(q, r["answer"])})
        out["questions"].append(r)
        save("l-mix", out)
        print("mix", q["id"], "opened", r["opened"], r["code_right"], r["wrong_terms"], "|",
              r["answer"].replace("\n", " ")[:160], f"spent ${spent():.3f}")
    print(save("l-mix", out))


if __name__ == "__main__":
    try:
        main()
    except Stop as e:
        print("STOP:", e)
        sys.exit(3)
