"""Write one synthetic hour of Sorrel production logs around the payments-latency incident.

    python3 sorrel/make_logs.py          # writes logs/sorrel-incident.log

Sorrel is made up: an appointment-scheduling SaaS with four services (web, api, payments,
notifier). The hour is made up too, and so is every name and address in it. The same seed
writes the same file, byte for byte.

What happens in the hour (the payments-latency ticket in tickets/incidents.json):
  13:31:00  payments deploys 2026.09.23-2
  13:38:32  its rate-cache refresher thread dies on its first scheduled refresh
  13:39:02  the cached currency rates expire; every checkout now fetches them live
  13:45:00  the alert fires: p95 4.8 s for 6 min, 14 min after the deploy
"""
import random, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 20260923
LINES = 40_000
START = datetime(2026, 9, 23, 12, 54, 0, tzinfo=timezone.utc)
DEPLOY = START + timedelta(minutes=37)                   # 13:31:00
CRASH = DEPLOY + timedelta(seconds=452, milliseconds=95)  # 13:38:32, one interval after start
STALE = CRASH + timedelta(seconds=30)                    # 13:39:02
ALERT = DEPLOY + timedelta(minutes=14)                   # 13:45:00
END = START + timedelta(hours=1)
OUT = Path(__file__).resolve().parent.parent / "logs" / "sorrel-incident.log"

rng = random.Random(SEED)
events = []                                              # (time, seq, text)


def pod(service, n):
    return [f"{service}-{rng.choice(['5f7c9d', '7b9c6f', '6d4b8c', '84fd21'])}-"
            f"{''.join(rng.choice('bcdfghjklmnpqrstvwxz2456789') for _ in range(5))}" for _ in range(n)]


PODS = {"web": pod("web", 3), "api": pod("api", 4), "notifier": pod("notifier", 2)}
PAY_OLD, PAY_NEW = pod("payments", 2), pod("payments", 2)
FIRST = ["Aiko", "Ben", "Chloe", "Daniel", "Emma", "Farah", "Hiro", "Isha", "Jonas", "Kenji",
         "Lena", "Mateo", "Nadia", "Omar", "Priya", "Rahul", "Sofia", "Taro", "Uma", "Yuki"]
LAST = ["Sato", "Tanaka", "Sharma", "Patel", "Miller", "Garcia", "Kim", "Suzuki", "Iyer", "Novak"]
CLINICS = [f"cl_{rng.randint(1000, 9999)}" for _ in range(60)]
UA = ['"Mozilla/5.0 (iPhone; CPU iPhone OS 19_1 like Mac OS X) AppleWebKit/605.1.15"',
      '"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141.0.0.0 Safari/537.36"',
      '"Mozilla/5.0 (Linux; Android 16; Pixel 9) Chrome/141.0.0.0 Mobile Safari/537.36"',
      '"Sorrel-iOS/5.12.0 (iPhone16,2)"', '"Sorrel-Android/5.12.1"']


def emit(t, level, service, p, msg):
    ts = t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"
    events.append((t, len(events), f"{ts} {level:<5} {service:<8} pod={p} {msg}"))


def ms(lo, hi):
    return int(rng.lognormvariate(0, 0.45) * (lo + hi) / 2) if hi > lo else lo


def email():
    return f"{rng.choice(FIRST).lower()}.{rng.choice(LAST).lower()}{rng.randint(1, 99)}@example.com"


def payments_pods(t):
    return PAY_NEW if t >= DEPLOY + timedelta(seconds=40) else PAY_OLD


def checkout(t, req, user_ua):
    """One checkout: web -> api -> payments -> provider. Slow once the rate cache is stale."""
    p = rng.choice(payments_pods(t))
    stale = t >= STALE
    fx = int(rng.lognormvariate(0, 0.16) * 3300) if stale else ms(2, 6)
    if stale and rng.random() < 0.02:
        fx = rng.randint(8000, 9500)                    # the tail that times out
    provider = ms(280, 700)
    amount = rng.choice([3300, 4400, 5500, 6600, 8800, 11000, 16500])
    cur = rng.choice(["JPY"] * 6 + ["USD", "EUR", "INR", "SGD"])
    api_p = rng.choice(PODS["api"])
    if fx >= 8000:
        emit(t + timedelta(milliseconds=8000), "ERROR", "api", api_p,
             f"req={req} method=POST path=/v1/checkout status=504 dur_ms=8003 "
             f'upstream=payments err="upstream timeout after 8000ms"')
        emit(t + timedelta(milliseconds=8010), "WARN", "web", rng.choice(PODS["web"]),
             f"req={req} method=POST path=/checkout status=502 dur_ms=8021 ua={user_ua}")
        emit(t + timedelta(milliseconds=fx + provider), "WARN", "payments", p,
             f"req={req} method=POST path=/v1/charges status=201 dur_ms={fx + provider} "
             f"note=client_gone amount={amount} currency={cur} fx_source=live")
        return
    declined = rng.random() < 0.03
    status = 402 if declined else 201
    dur = fx + provider + ms(8, 20)
    extra = ' code=PAY-4031 reason="card_declined"' if declined else ""
    emit(t + timedelta(milliseconds=dur), "INFO", "payments", p,
         f"req={req} method=POST path=/v1/charges status={status} dur_ms={dur} amount={amount} "
         f"currency={cur} fx_source={'live' if stale else 'cache'} provider=cardco "
         f"provider_ms={provider}{extra}")
    emit(t + timedelta(milliseconds=dur + 4), "INFO", "api", api_p,
         f"req={req} method=POST path=/v1/checkout status={status} dur_ms={dur + 4} upstream=payments")
    emit(t + timedelta(milliseconds=dur + 12), "INFO", "web", rng.choice(PODS["web"]),
         f"req={req} method=POST path=/checkout status={200 if not declined else 402} "
         f"dur_ms={dur + 12} ua={user_ua}")
    if not declined:
        emit(t + timedelta(milliseconds=dur + ms(300, 900)), "INFO", "notifier", rng.choice(PODS["notifier"]),
             f"req={req} sent kind=email template=payment_receipt to={email()} provider=mailgrid "
             f"dur_ms={ms(120, 260)}")


def user_request(t):
    req = str(uuid.UUID(int=rng.getrandbits(128), version=4))
    ua = rng.choice(UA)
    clinic = rng.choice(CLINICS)
    r = rng.random()
    web_p, api_p = rng.choice(PODS["web"]), rng.choice(PODS["api"])
    if r < 0.05:
        return checkout(t, req, ua)
    if r < 0.40:
        day = (START + timedelta(days=rng.randint(0, 20))).strftime("%Y-%m-%d")
        d = ms(25, 90)
        slow = rng.random() < 0.004
        if slow:
            d = rng.randint(1100, 2400)
            emit(t + timedelta(milliseconds=d - 3), "WARN", "api", api_p,
                 f'req={req} slow_query table=slots dur_ms={d - 3} sql="SELECT ... FROM slots WHERE clinic_id=$1 AND day=$2"')
        emit(t + timedelta(milliseconds=d), "INFO", "api", api_p,
             f"req={req} method=GET path=/v1/clinics/{clinic}/slots?date={day} status=200 dur_ms={d}")
        emit(t + timedelta(milliseconds=d + ms(30, 60)), "INFO", "web", web_p,
             f"req={req} method=GET path=/book/{clinic} status=200 dur_ms={d + 40} ua={ua}")
    elif r < 0.62:
        appt = f"ap_{rng.getrandbits(40):010x}"
        d = ms(40, 120)
        emit(t + timedelta(milliseconds=d), "INFO", "api", api_p,
             f"req={req} method=POST path=/v1/appointments status=201 dur_ms={d} clinic={clinic} appointment={appt}")
        emit(t + timedelta(milliseconds=d + 20), "INFO", "web", web_p,
             f"req={req} method=POST path=/book/{clinic}/confirm status=303 dur_ms={d + 20} ua={ua}")
        emit(t + timedelta(milliseconds=d + ms(200, 800)), "INFO", "notifier", rng.choice(PODS["notifier"]),
             f"req={req} sent kind=email template=booking_confirmed to={email()} provider=mailgrid dur_ms={ms(120, 260)}")
    elif r < 0.72:
        d = ms(20, 60)
        code = 200 if rng.random() > 0.02 else 404
        emit(t + timedelta(milliseconds=d), "INFO", "api", api_p,
             f"req={req} method=GET path=/v1/appointments/ap_{rng.getrandbits(40):010x} status={code} dur_ms={d}")
        emit(t + timedelta(milliseconds=d + 15), "INFO", "web", web_p,
             f"req={req} method=GET path=/account/appointments status={code} dur_ms={d + 15} ua={ua}")
        if code == 200 and rng.random() < 0.3:              # the receipt link on the page
            emit(t + timedelta(milliseconds=d + ms(10, 30)), "INFO", "payments", rng.choice(payments_pods(t)),
                 f"req={req} method=GET path=/v1/charges/ch_{rng.getrandbits(48):012x} status=200 dur_ms={ms(6, 18)}")
    elif r < 0.76 and rng.random() < 0.5:
        emit(t + timedelta(milliseconds=3), "WARN", "api", api_p,
             f"req={req} method=GET path=/v1/clinics/{clinic}/slots status=429 dur_ms=2 "
             f"reason=rate_limited client=partner_{rng.randint(10, 40)} limit=120/min")
    else:
        d = ms(8, 40)
        emit(t + timedelta(milliseconds=d), "INFO", "web", web_p,
             f"req={req} method=GET path={rng.choice(['/', '/login', '/pricing', '/account'])} status=200 dur_ms={d} ua={ua}")


def payments_lifecycle():
    for p in PAY_OLD:                                    # the old version, refreshing every 450 s
        emit(START + timedelta(seconds=rng.randint(1, 9)), "INFO", "payments", p,
             "version=2026.09.19-1 commit=77c02d5 uptime_s=331204")
    t = START + timedelta(seconds=94)
    while t < DEPLOY:
        emit(t, "INFO", "payments", PAY_OLD[0], f"rate cache refreshed pairs=14 dur_ms={ms(300, 460)} ttl_s=480")
        t += timedelta(seconds=450)
    emit(DEPLOY - timedelta(seconds=2), "INFO", "api", PODS["api"][0],
         "deploy started service=payments version=2026.09.23-2 commit=a41f9e3 by=ci strategy=rolling")
    for i, (old, new) in enumerate(zip(PAY_OLD, PAY_NEW)):
        t0 = DEPLOY + timedelta(seconds=18 * i)
        emit(t0, "INFO", "payments", old, f"received SIGTERM, draining in_flight={rng.randint(2, 9)}")
        emit(t0 + timedelta(seconds=1), "INFO", "payments", new, "starting sorrel-payments version=2026.09.23-2 commit=a41f9e3 python=3.12.6")
        emit(t0 + timedelta(seconds=1, milliseconds=220), "INFO", "payments", new, "db pool ready size=10 host=pg-payments-primary")
        emit(t0 + timedelta(seconds=1, milliseconds=410), "INFO", "payments", new, "rate cache warmed from snapshot pairs=14 age_s=38")
        emit(t0 + timedelta(seconds=2), "INFO", "payments", new, "listening on :8080 workers=4")
        emit(t0 + timedelta(seconds=4), "INFO", "payments", old, "shutdown complete")
    emit(DEPLOY + timedelta(seconds=2, milliseconds=90), "INFO", "payments", PAY_NEW[0],
         "elected rate-cache leader lease_s=30")
    emit(DEPLOY + timedelta(seconds=2, milliseconds=95), "INFO", "payments", PAY_NEW[0],
         "rate cache refresher started interval_s=450")
    emit(DEPLOY + timedelta(seconds=41), "INFO", "api", PODS["api"][0],
         "deploy finished service=payments version=2026.09.23-2 replicas=2/2 healthy")
    tb = [
        "Exception in thread rate-cache-refresher:",
        "Traceback (most recent call last):",
        '  File "/usr/local/lib/python3.12/threading.py", line 1075, in _bootstrap_inner',
        "    self.run()",
        '  File "/usr/local/lib/python3.12/threading.py", line 1012, in run',
        "    self._target(*self._args, **self._kwargs)",
        '  File "/app/payments/rates/cache.py", line 64, in refresh_forever',
        "    self._refresh_once()",
        '  File "/app/payments/rates/cache.py", line 81, in _refresh_once',
        '    ttl = int(settings["RATE_CACHE_TTL"])',
        "              ~~~~~~~~^^^^^^^^^^^^^^^^^^",
        "KeyError: 'RATE_CACHE_TTL'",
    ]
    ts = CRASH.strftime("%Y-%m-%dT%H:%M:%S.") + f"{CRASH.microsecond // 1000:03d}Z"
    head = f"{ts} ERROR payments pod={PAY_NEW[0]} stream=stderr {tb[0]}"
    events.append((CRASH, len(events), "\n".join([head] + tb[1:])))
    emit(ALERT, "INFO", "notifier", PODS["notifier"][1],
         "sent kind=page to=oncall-payments provider=pagerline alert=\"payments-api: p95 latency 4.8 s for 6 min, "
         "error rate 0.9 %\" dur_ms=184")


def background():
    everyone = [("web", p) for p in PODS["web"]] + [("api", p) for p in PODS["api"]] + \
               [("notifier", p) for p in PODS["notifier"]]
    t = START
    while t < END:
        for service, p in everyone + [("payments", p) for p in payments_pods(t)]:
            emit(t + timedelta(milliseconds=rng.randint(0, 999)), "INFO", service, p,
                 'method=GET path=/healthz status=200 dur_ms=1 ua="kube-probe/1.31"')
        if t.second == 0:
            for p in PODS["api"]:
                emit(t + timedelta(milliseconds=rng.randint(0, 999)), "INFO", "api", p,
                     f"db pool in_use={rng.randint(1, 6)}/20 waiting=0 host=pg-main-primary")
            for p in payments_pods(t):
                emit(t + timedelta(milliseconds=rng.randint(0, 999)), "INFO", "payments", p,
                     f"db pool in_use={rng.randint(1, 4)}/10 waiting=0 host=pg-payments-primary")
        if t.second % 30 == 0:
            emit(t + timedelta(milliseconds=rng.randint(0, 999)), "INFO", "notifier", PODS["notifier"][0],
                 f"queue depth={rng.randint(0, 40)} consumers=8 oldest_ms={rng.randint(20, 900)}")
        if t.second == 15 and t.minute % 5 == 0:
            for p in PODS["notifier"]:
                emit(t, "INFO", "notifier", p, f"reminders batch due_in=24h picked={rng.randint(40, 160)}")
        t += timedelta(seconds=10)


def notifier_chatter():
    t = START
    while t < END:
        t += timedelta(milliseconds=int(rng.expovariate(1 / 1100)))
        p = rng.choice(PODS["notifier"])
        if rng.random() < 0.01:
            emit(t, "WARN", "notifier", p, f"send failed kind=sms provider=textbridge status=503 attempt=1 retry_in_ms=500")
            emit(t + timedelta(milliseconds=520), "INFO", "notifier", p,
                 f"sent kind=sms template=reminder_24h to=+81-90-0000-{rng.randint(1000, 9999)} provider=textbridge attempt=2 dur_ms={ms(90, 200)}")
        else:
            kind = rng.choice(["email", "email", "sms"])
            to = email() if kind == "email" else f"+81-90-0000-{rng.randint(1000, 9999)}"
            emit(t, "INFO", "notifier", p,
                 f"sent kind={kind} template=reminder_24h to={to} provider={'mailgrid' if kind == 'email' else 'textbridge'} dur_ms={ms(90, 260)}")


def provider_webhooks():
    t = START
    while t < END:
        t += timedelta(milliseconds=int(rng.expovariate(1 / 6000)))
        emit(t, "INFO", "payments", rng.choice(payments_pods(t)),
             f"req={uuid.UUID(int=rng.getrandbits(128), version=4)} method=POST path=/v1/webhooks/cardco "
             f"status=200 dur_ms={ms(4, 12)} event={rng.choice(['charge.succeeded'] * 5 + ['charge.refunded', 'payout.paid'])}")


background()
payments_lifecycle()
provider_webhooks()
notifier_chatter()
t = START
while t < END:
    t += timedelta(milliseconds=int(rng.expovariate(1 / 205)))
    user_request(t)

lines = []
for _, _, text in sorted(events):
    lines.extend(text.split("\n"))
OUT.parent.mkdir(exist_ok=True)
OUT.write_text("\n".join(lines[:LINES]) + "\n")
print(f"{OUT.name}: {min(len(lines), LINES):,} of {len(lines):,} lines written, seed {SEED}")
