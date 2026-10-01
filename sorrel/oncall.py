"""The pretend Sorrel the on-call functions act on. Nothing real is rolled back or paged:
each function returns the text a real one would, built from the alert, so every run is repeatable.
"""
import hashlib, re

SERVICES = ["web", "api", "payments", "notifier"]
PROVIDERS = ["stripe", "twilio", "sendgrid", "cloudflare", "aws"]
OWNERS = {"web": "Aiko", "api": "Ravi", "payments": "Mei", "notifier": "Tom"}


def alert_service(case):
    """The service the alert is about. 'payments-api: ...' is the payments service."""
    return case["alert"].split(":")[0].split("-")[0]


def _age_min(alert):
    m = re.search(r"last deploy (\d+) (min|h|days?) ago", alert)
    if not m:
        return 3 * 24 * 60
    n, unit = int(m.group(1)), m.group(2)
    return n if unit == "min" else n * 60 if unit == "h" else n * 24 * 60


def _deploy_id(case, service, i):
    h = hashlib.sha256(f"{case['id']}/{service}/{i}".encode()).hexdigest()
    return f"d-{int(h[:6], 16) % 9000 + 1000}"


def deploys(case, service):
    """Newest first. The alerting service's last deploy is the age the alert states."""
    first = _age_min(case["alert"]) if service == alert_service(case) else 4 * 24 * 60
    ages = [first, first + 2 * 24 * 60, first + 9 * 24 * 60]
    return [{"id": _deploy_id(case, service, i), "age_min": a} for i, a in enumerate(ages)]


def _ago(minutes):
    if minutes < 60:
        return f"{minutes} min ago"
    if minutes < 24 * 60:
        return f"{minutes // 60} h ago"
    return f"{minutes // (24 * 60)} days ago"


def run(name, args, case):
    """What the function would have done, as text for the model to read next."""
    service = args.get("service")
    if name == "list_deploys":
        return {"deploys": [f"{d['id']} ({_ago(d['age_min'])})" for d in deploys(case, service)]}
    if name == "read_logs":
        symptom = case["alert"].split(":", 1)[1].split(",")[0].strip()
        last = deploys(case, service)[0]
        return {"lines": [f"{service} started {last['id']} {_ago(last['age_min'])}",
                          f"{service} WARN {symptom}",
                          f"{service} WARN {symptom} (repeated)"]}
    if name == "roll_back":
        return {"result": f"{service} rolled back past {args.get('deploy_id')}"}
    if name == "check_provider":
        text = case["alert"].lower()
        down = any(w in text for w in ("status page reports", "reports a", "returning 503",
                                       "quota exceeded", "purge still in progress"))
        return {"status": "incident reported" if down else "all systems normal"}
    if name == "page_owner":
        return {"result": f"paged {OWNERS.get(service, 'nobody')}, the owner of {service}"}
    if name == "no_action":
        return {"result": "noted"}
    return {"error": f"no function called {name}"}
