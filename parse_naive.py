"""Read the severity out of answers that were already saved, two ways.

The obvious version checks the front of the line. The one in ten_runs.py searches
anywhere. On fifty real answers they do not agree, and nothing warns you.
"""
import json, re

answers = json.load(open("runs/ep02/answers-50.json"))["answers"]

naive = [a for a in answers if a.startswith("P")]        # the one you write first
search = [a for a in answers if re.search(r"P[123]", a)]  # the one in ten_runs.py

print(f"startswith('P')      {len(naive)} / {len(answers)}")
print(f"re.search('P[123]')  {len(search)} / {len(answers)}")

for a in answers:
    if not a.startswith("P"):
        print(f"  dropped: {a}")
