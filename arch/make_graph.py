"""One night of Sorrel, one point a minute, 01:00-05:00: p95 latency for api and payments.

    python3 arch/make_graph.py       # writes arch/latency.csv, arch/latency.png (the panel),
                                     # arch/latency-rate.png (same panel, request rate on a second axis)
The CSV is the ground truth. The pictures are drawn from it and nothing else.
"""
import csv, os, random

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MultipleLocator

HERE = os.path.dirname(os.path.abspath(__file__))
START_H = 1
DEPLOY, ROLLBACK = 74, 118          # minutes after 01:00: 02:14 and 02:58
EVENTS = {DEPLOY: "deploy payments v2.31", ROLLBACK: "rollback payments v2.30"}

BG, PANEL, TEXT, GRID = "#111217", "#181b1f", "#ccccdc", "#2c3235"
GREEN, YELLOW, BLUE, ANNO = "#73BF69", "#FADE2A", "#5794F2", "#8AB8FF"


def hhmm(m):
    return f"{START_H + m // 60:02d}:{m % 60:02d}"


def night(seed=8):
    rnd = random.Random(seed)
    rows = []
    for m in range(0, 241):
        # payments: flat ~300 ms, then the v2.31 connection pool starves from 02:17
        pay = 300 + 18 * rnd.gauss(0, 1) + 12 * ((m % 17) / 17 - 0.5)
        if 77 <= m <= 112:                      # the climb, 02:17 -> 02:52
            x = (m - 77) / 35
            pay = 300 + 3500 * (x ** 0.65) + 90 * rnd.gauss(0, 1)
        elif 112 < m <= 118:                    # stuck near the top until the rollback
            pay = 3350 + 60 * rnd.gauss(0, 1)
        elif 118 < m <= 131:                    # the rollback rolls out, 02:58 -> 03:11
            x = (m - 118) / 11
            pay = max(300, 3350 * max(0, 1 - x) ** 1.8 + 300 * min(1, x)) + 40 * rnd.gauss(0, 1)
        pay = round(max(pay, 180))
        # api waits on payments for checkout calls
        api = 175 + 9 * rnd.gauss(0, 1) - 0.08 * m + 0.11 * max(0, pay - 320)
        api = round(api)
        # payments request rate falls through the night; client retries push it up during the incident
        rps = 152 - 0.17 * m + 3.5 * rnd.gauss(0, 1)
        rps *= 1 + max(0, pay - 320) / 3400
        rows.append({"time": hhmm(m), "api_p95_ms": api, "payments_p95_ms": pay,
                     "payments_rps": round(rps, 1), "event": EVENTS.get(m, "")})
    return rows


def ms_label(v, _):
    if v < 1000:
        return f"{v:.0f} ms"
    s = v / 1000
    return f"{s:.0f} s" if s == int(s) else f"{s:.2f} s"


def panel(rows, path, with_rate=False, width_px=1600):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})
    fig = plt.figure(figsize=(16, 9), dpi=100, facecolor=BG)
    ax = fig.add_axes([0.045, 0.10, 0.90 if with_rate else 0.94, 0.80], facecolor=PANEL)
    fig.patches.append(plt.Rectangle((0.008, 0.015), 0.984, 0.965, transform=fig.transFigure,
                                     facecolor=PANEL, edgecolor="#2f3136", lw=1, zorder=-1))
    xs = list(range(len(rows)))
    api = [r["api_p95_ms"] for r in rows]
    pay = [r["payments_p95_ms"] for r in rows]
    l1, = ax.plot(xs, api, color=GREEN, lw=1.2, label="api")
    l2, = ax.plot(xs, pay, color=YELLOW, lw=1.2, label="payments")
    ax.fill_between(xs, api, color=GREEN, alpha=0.08, lw=0)
    ax.fill_between(xs, pay, color=YELLOW, alpha=0.08, lw=0)
    ax.set_xlim(0, len(rows) - 1)
    ax.set_ylim(0, 4000)
    ax.yaxis.set_major_locator(MultipleLocator(500))
    ax.yaxis.set_major_formatter(FuncFormatter(ms_label))
    ax.xaxis.set_major_locator(MultipleLocator(20))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: hhmm(int(v))))
    ax.grid(True, color=GRID, lw=0.8)
    for side in ax.spines.values():
        side.set_visible(False)
    ax.tick_params(colors=TEXT, length=0, labelsize=9, pad=6)
    handles = [l1, l2]
    if with_rate:
        ax2 = ax.twinx()
        rate = [r["payments_rps"] for r in rows]
        l3, = ax2.plot(xs, rate, color=BLUE, lw=1.1, label="payments req/s (right axis)")
        ax2.set_ylim(0, 400)
        ax2.yaxis.set_major_locator(MultipleLocator(50))
        ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f} req/s"))
        for side in ax2.spines.values():
            side.set_visible(False)
        ax2.tick_params(colors=TEXT, length=0, labelsize=9, pad=6)
        handles.append(l3)
    for m, label in EVENTS.items():
        ax.axvline(m, color=ANNO, lw=1, ls=(0, (4, 3)), zorder=3)
        ax.text(m + 0.8, 3930, label, color=ANNO, fontsize=8, va="top", ha="left",
                bbox={"facecolor": PANEL, "edgecolor": ANNO, "lw": 0.6, "boxstyle": "round,pad=0.25"})
    title = "p95 latency and request rate" if with_rate else "p95 latency by service"
    fig.text(0.02, 0.945, title, color=TEXT, fontsize=11, fontweight="bold", ha="left", va="center")
    fig.text(0.98, 0.945, "Last 4 hours · 01:00 to 05:00", color="#8e8e8e", fontsize=8.5, ha="right", va="center")
    leg = fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.04, 0.025), ncol=len(handles),
                     frameon=False, fontsize=9, handlelength=1.6, columnspacing=2.2)
    for t in leg.get_texts():
        t.set_color(TEXT)
    fig.savefig(path, dpi=100 * width_px / 1600, facecolor=BG)
    plt.close(fig)


if __name__ == "__main__":
    rows = night()
    with open(os.path.join(HERE, "latency.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    panel(rows, os.path.join(HERE, "latency.png"))
    panel(rows, os.path.join(HERE, "latency-rate.png"), with_rate=True)
    print(f"{len(rows)} rows -> latency.csv, latency.png, latency-rate.png")
