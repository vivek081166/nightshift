import json, sys
triage = json.loads(open(sys.argv[1]).read())
print("severity:", triage["severity"])
print("service:", triage["service"])
print("wake someone now:", triage["severity"] == "P1")
print("first move:", triage["first_move"])
