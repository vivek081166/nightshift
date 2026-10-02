"""My on-call code: what it does with the model's triage."""
import json, sys

triage = json.load(open(sys.argv[1]))
print("wake someone now:", triage["severity"] == "P1")
print("first move:", triage["first_move"])
