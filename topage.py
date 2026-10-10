"""Turn the team's PDFs into pages the model can look up: one page per PDF, in pages/.

    python3 topage.py pdf/                 # make a page for each PDF that changed; a PDF with no text goes to the model
    python3 topage.py --text <file.pdf>    # the text taken out of one PDF, no model involved
    python3 topage.py --count pdf/         # how many characters came out of each PDF
    python3 topage.py --write <file.pdf>   # the model writes one PDF out as text
"""
import base64, hashlib, sys, time
from datetime import date
from pathlib import Path
from pypdf import PdfReader
import lookup                                         # the same model and the same call as the look-up

WRITE = ("Write this whole document out as Markdown, word for word, in reading order. Every table becomes a "
         "Markdown table with the same rows and columns. Do not summarise, do not leave anything out, and do not "
         "add anything that is not in the document.")
PAGES = Path("pages")


def text_out(pdf):
    """the text the PDF carries inside it; a scan carries none"""
    return "\n\n".join(page.extract_text() for page in PdfReader(pdf).pages)


def write_out(pdf):
    """the model gets the PDF itself and writes it out as text, once"""
    the_pdf = base64.b64encode(Path(pdf).read_bytes()).decode()
    reply = lookup.call({"contents": [{"role": "user", "parts": [
        {"inline_data": {"mime_type": "application/pdf", "data": the_pdf}},      # the PDF itself
        {"text": WRITE}]}]})                                                   # and what to do with it
    return "".join(part.get("text", "") for part in reply["parts"] if not part.get("thought"))


def tag(pdf):
    return hashlib.md5(Path(pdf).read_bytes()).hexdigest()[:8]     # change one byte and the tag changes


def make_pages(folder):
    PAGES.mkdir(exist_ok=True)
    for pdf in sorted(Path(folder).glob("*.pdf")):
        page = PAGES / (pdf.stem + ".md")
        if page.exists() and f"tag {tag(pdf)} " in page.read_text().split("\n")[0]:
            print("kept       ", pdf.stem)
            continue
        text = text_out(pdf)
        if len(text.strip()) == 0:                    # no characters: no text inside, like a scan
            print("made  scan ", pdf.stem, " -> the model")
            text = write_out(pdf)
        else:
            print("made  text ", pdf.stem)
        page.write_text(f"Source: {pdf.name} · tag {tag(pdf)} · made {date.today()}\n\n{text}")


if __name__ == "__main__":
    t0, flag, where = time.time(), sys.argv[1], sys.argv[-1]
    if flag == "--text":
        print(text_out(where))
    elif flag == "--count":
        for pdf in sorted(Path(where).glob("*.pdf")):
            print(f"{pdf.stem:42} {len(text_out(pdf).strip()):>6,}")
    elif flag == "--write":
        print(write_out(where))
    else:
        make_pages(where)
    if lookup.used:
        print(lookup.cost_line(time.time() - t0))
