"""The postmortem for the payments timeouts, as the team would write it: two pages, a summary and a timeline.

    python3 postmortems/make_pdf.py    # writes payments-timeout.pdf and payments-timeout.truth.json
Times for the deploy, the alert, the peak, the rollback and the recovery match arch/latency.csv.
"""
import json, os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = os.path.dirname(os.path.abspath(__file__))

META = [("Incident date", "2026-10-02, night (JST)"), ("Severity", "SEV-2"), ("Incident commander", "Aiko"),
        ("Author", "Mei"), ("Status", "Final, reviewed 2026-10-05")]

SUMMARY = ("At 02:14 JST we deployed payments v2.31. The release cut the database connection pool for payments "
           "from 50 to 20. Even at night traffic, checkout requests began to wait for a free connection, and the "
           "payments p95 latency went above 2 seconds at 02:28. Client retries added load and made the wait longer. "
           "We rolled back to v2.30 starting at 02:58, and payments were restored at 03:07.")

IMPACT = ["Customer impact window: 02:18 to 03:07 JST (49 minutes).",
          "Failed payments: 1,184. All were replayed from the retry queue by 03:12. No customer was charged twice.",
          "Delayed payments (completed, but slower than 2 seconds): 3,907.",
          "Support tickets: 23.",
          "The api p95 latency rose to about 530 ms, because checkout calls in api wait on payments."]

ROOT_CAUSE = ("The pool size lives in a config file. The change was reviewed as \"no functional change\" and was not "
              "load tested. With 20 connections, each slow database call held a connection longer, the queue grew, "
              "and retries from the app added more requests to the same queue.")

ACTIONS = ["Alert on payments connection wait time, not only on p95 latency (owner: Ravi, due 2026-10-16).",
           "Any change to pool sizes needs a load test before deploy (owner: Mei, due 2026-10-16).",
           "Client retries for checkout use backoff with jitter (owner: Aiko, due 2026-10-23)."]

TIMELINE = [  # time, what happened, who
    ("02:14", "Payments v2.31 deployed. The release cuts the database connection pool from 50 to 20.", "Mei"),
    ("02:21", "First support ticket: the checkout spinner does not finish.", "Hana (Support)"),
    ("02:30", "Alert fires: payments p95 above 2 s for 2 minutes. Page sent to on-call.", "PagerDuty"),
    ("02:34", "Page acknowledged.", "Ravi"),
    ("02:39", "Payments logs show requests waiting for a database connection.", "Ravi"),
    ("02:43", "Incident declared (SEV-2). Aiko takes incident commander.", "Aiko"),
    ("02:47", "Mei joins and points at the pool size change in v2.31.", "Mei"),
    ("02:50", "Payments p95 peaks at 3.7 s. Client retries push the request rate up by about 80%.", "Ravi"),
    ("02:56", "Decision to roll back payments to v2.30.", "Aiko"),
    ("02:58", "Rollback to v2.30 started.", "Mei"),
    ("03:04", "Rollback complete on all payments pods.", "Mei"),
    ("03:07", "Payments p95 back under 500 ms. Payments restored.", "Ravi"),
    ("03:12", "1,184 failed payments replayed from the retry queue.", "Mei"),
    ("03:20", "Receipt emails for the replayed payments sent.", "Tom"),
]

TRUTH = {
    "P1": {"answer": "03:07"},
    "P2": {"answer": "Mei"},
    "P3": {"answer": 28, "why": "alert 02:30 -> rollback started 02:58"},
    "P4": {"answer": {"time": "02:47", "who": "Mei"}, "why": "row after 02:43 Incident declared"},
    "P5": {"answer": {"who": "Ravi", "time": "02:34"}},
    "P6": {"answer": {"who": "Tom", "what": "receipt emails for the replayed payments sent"}},
    "P7": {"answer": 1184},
    "P8": {"answer": "v2.30"},
    "P9": {"answer": sum(1 for r in TIMELINE if r[2] == "Mei"), "why": "rows " + ", ".join(r[0] for r in TIMELINE if r[2] == "Mei")},
    "P10": {"answer": "Aiko"},
}


def build(path):
    ss = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=ss["Normal"], fontName="Helvetica", fontSize=10, leading=14)
    cell = ParagraphStyle("cell", parent=body, fontSize=9.5, leading=12.5)
    h1 = ParagraphStyle("h1", parent=body, fontName="Helvetica-Bold", fontSize=16, leading=20, spaceAfter=8)
    h2 = ParagraphStyle("h2", parent=body, fontName="Helvetica-Bold", fontSize=12, leading=16, spaceBefore=12, spaceAfter=4)
    story = [Paragraph("Postmortem: payments timeouts after the v2.31 deploy", h1)]
    meta = Table([[Paragraph(f"<b>{k}</b>", cell), Paragraph(v, cell)] for k, v in META], colWidths=[45 * mm, 110 * mm])
    meta.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                              ("TOPPADDING", (0, 0), (-1, -1), 2), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [meta, Paragraph("Summary", h2), Paragraph(SUMMARY, body), Paragraph("Impact", h2)]
    story += [Paragraph(f"&bull; {line}", body) for line in IMPACT]
    story += [Paragraph("Root cause", h2), Paragraph(ROOT_CAUSE, body), Paragraph("Action items", h2)]
    story += [Paragraph(f"{i}. {line}", body) for i, line in enumerate(ACTIONS, 1)]
    story += [PageBreak(), Paragraph("Timeline (JST)", h2), Spacer(1, 2 * mm)]
    rows = [[Paragraph("<b>Time</b>", cell), Paragraph("<b>What happened</b>", cell), Paragraph("<b>Who</b>", cell)]]
    rows += [[Paragraph(t, cell), Paragraph(w, cell), Paragraph(p, cell)] for t, w, p in TIMELINE]
    table = Table(rows, colWidths=[18 * mm, 120 * mm, 32 * mm], repeatRows=1)
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
                               ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#b0b0b0")),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(table)

    def footer(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(20 * mm, 12 * mm, "Sorrel engineering · internal")
        canvas.drawRightString(190 * mm, 12 * mm, f"Page {doc.page} of 2")

    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm,
                            bottomMargin=20 * mm, title="Postmortem: payments timeouts", author="Mei")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    build(os.path.join(HERE, "payments-timeout.pdf"))
    json.dump({"timeline": [{"time": t, "what": w, "who": p} for t, w, p in TIMELINE], "questions": TRUTH},
              open(os.path.join(HERE, "payments-timeout.truth.json"), "w"), indent=1)
    print(f"{len(TIMELINE)} timeline rows -> payments-timeout.pdf, payments-timeout.truth.json")
