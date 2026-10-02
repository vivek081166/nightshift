"""EP07 M3: an open model's real next-piece candidates, unconstrained and with the schema as a mask.

    HF_HUB_OFFLINE=1 ~/Projects/vivek-ai/.venv/bin/python measure/ep07_candidates.py
Model: mlx-community/Qwen3-8B-4bit (cached), chat template, thinking off. NOT Gemini: Gemini refused logprobs.
Spots: (1) the first piece of the reply, (2) the piece after `"severity": "`.
Mask: a token is allowed only if the text so far + the token can still be continued into a JSON object that matches
triage.py's SCHEMA (the four keys, each once, any order; enum values exact; reason any string; JSON whitespace allowed).
"""
import datetime, json, os, re, sys

import mlx.core as mx
from mlx_lm import load

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from rules import SYSTEM, ACTIONS  # noqa: E402
from triage import SCHEMA  # noqa: E402
FIELDS = "severity (P1, P2 or P3), service, first_move (one of: " + ", ".join(ACTIONS) + "), reason"  # the 09-29 tight prompt

MODEL_ID = "mlx-community/Qwen3-8B-4bit"
CASES = json.load(open("tickets/incidents.json"))
CASE = CASES[0]   # payments-latency, the cold-open alert
PROMPTS = {"tight": f"Alert:\n{CASE['alert']}\nReply with a JSON object with these fields: {FIELDS}.",
           "loose": f"Alert:\n{CASE['alert']}\nReply in JSON with the severity, the service, the first move, and why."}
PROPS = SCHEMA["properties"]
WS = " \t\n\r"


class Shape:
    """Character-level prefix check for triage.py's SCHEMA."""
    def __init__(self):
        self.st, self.buf, self.key, self.used, self.esc = "start", "", None, frozenset(), False

    def copy(self):
        s = Shape.__new__(Shape)
        s.st, s.buf, s.key, s.used, s.esc = self.st, self.buf, self.key, self.used, self.esc
        return s

    def left(self):
        return [k for k in PROPS if k not in self.used]

    def feed(self, ch):
        st = self.st
        if st in ("start", "obj", "colon", "val0", "after", "comma", "done") and ch in WS:
            return True
        if st == "start":
            if ch == "{":
                self.st = "obj"; return True
            return False
        if st in ("obj", "comma"):
            if ch == '"':
                self.st, self.buf = "key", ""; return True
            return False
        if st == "key":
            if ch == '"':
                if self.buf in self.left():
                    self.key, self.st = self.buf, "colon"; return True
                return False
            self.buf += ch
            return any(k.startswith(self.buf) for k in self.left())
        if st == "colon":
            if ch == ":":
                self.st = "val0"; return True
            return False
        if st == "val0":
            if ch == '"':
                self.st, self.buf, self.esc = "val", "", False; return True
            return False
        if st == "val":
            enum = PROPS[self.key].get("enum")
            if enum is None:   # free string: JSON string rules
                if self.esc:
                    self.esc = False
                    return ch in '"\\/bfnrtu'
                if ch == "\\":
                    self.esc = True; return True
                if ch == '"':
                    self.used, self.st = self.used | {self.key}, "after"; return True
                return ord(ch) >= 0x20
            if ch == '"':
                if self.buf in enum:
                    self.used, self.st = self.used | {self.key}, "after"; return True
                return False
            self.buf += ch
            return any(v.startswith(self.buf) for v in enum)
        if st == "after":
            if ch == "," and self.left():
                self.st = "comma"; return True
            if ch == "}" and not self.left():
                self.st = "done"; return True
            return False
        return False   # done: only whitespace

    def take(self, text):
        for ch in text:
            if not self.feed(ch):
                return False
        return True


def allowed(state, piece):
    return bool(piece) and state.copy().take(piece)


m, tok = load(MODEL_ID)
V = m(mx.array([[0]]))[0, -1].shape[0]   # the model's output size
VOCAB = [tok.decode([i]) for i in range(V)]
SPECIAL = set(getattr(tok, "all_special_ids", []) or [])


def probs(ids):
    lg = m(mx.array(ids)[None])[0, -1].astype(mx.float32)
    return mx.softmax(lg, axis=-1)


def top(pr, k=10, mask=None):
    p = pr
    if mask is not None:
        p = mx.where(mx.array(mask), pr, 0.0)
        p = p / p.sum()
    order = mx.argsort(-p)[:k].tolist()
    return [{"id": t, "piece": VOCAB[t], "visible": VOCAB[t].replace("\n", "\\n"), "p": round(p[t].item(), 6)}
            for t in order]


def mask_for(state):
    return [i not in SPECIAL and allowed(state, VOCAB[i]) for i in range(len(VOCAB))]


SPOT2 = re.compile(r'"severity"\s*:\s*"$')
SPOT2B = re.compile(r'"severity"\s*:\s*$')


def walk(prompt_ids, masked, steps=60):
    """Greedy decode (masked: argmax among allowed), recording the distributions at both spots."""
    ids, text, state, spots = list(prompt_ids), "", Shape(), {}
    for step in range(steps):
        pr = probs(ids)
        if step == 0 or SPOT2.search(text) or (SPOT2B.search(text) and "spot2_colon" not in spots):
            name = "spot1_first_piece" if step == 0 else ("spot2_severity_value" if SPOT2.search(text)
                                                          else "spot2_colon")
            unc = top(pr)
            entry = {"prefix_text": text, "unconstrained_top10": unc}
            if masked:
                mk = mask_for(state)
                kept = mx.where(mx.array(mk), pr, 0.0).sum().item()
                entry["mask_allowed_tokens"] = int(sum(mk))
                entry["mass_kept_by_mask"] = round(kept, 6)
                for c in unc:
                    c["allowed_by_shape"] = mk[c["id"]]
                entry["masked_renormalised_top10"] = top(pr, mask=mk)
            else:
                st = Shape()
                for c in unc:   # what the shape would say about each, given the same prefix
                    s2 = st.copy()
                    c["allowed_by_shape_if_same_prefix"] = s2.take(text) and allowed(s2, c["piece"])
            spots[name] = entry
            if name == "spot2_severity_value":
                break
        order = mx.argsort(-pr)[:2000].tolist()
        nxt = order[0]
        if masked:
            nxt = next((t for t in order if t not in SPECIAL and allowed(state, VOCAB[t])), None)
            if nxt is None:
                spots["error"] = "no allowed token in the top 2000"
                break
            state.take(VOCAB[nxt])
        if nxt in SPECIAL:
            break
        ids.append(nxt)
        text += VOCAB[nxt]
    return {"generated_text": text, "spots": spots}


out = {"utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
       "model_id": MODEL_ID, "note": "open model on the M3 via mlx_lm (4-bit), NOT Gemini; softmax at temperature 1",
       "thinking": "off (enable_thinking=False)", "case": CASE["id"], "system": SYSTEM,
       "mask_rule": __doc__.split("Mask: ")[1].strip(), "runs": {}}
for pname, user in PROMPTS.items():
    chat = tok.apply_chat_template([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                                   add_generation_prompt=True, enable_thinking=False, tokenize=False)
    ids = tok.encode(chat)
    for masked in (False, True):
        key = f"{pname}/{'schema-mask' if masked else 'unconstrained'}"
        r = walk(ids, masked)
        r["chat_template_text"] = chat
        out["runs"][key] = r
        print("##", key, repr(r["generated_text"][:120]))
        for sname, e in r["spots"].items():
            if not isinstance(e, dict):
                print("  ", sname, e); continue
            print("  ", sname, "prefix", repr(e["prefix_text"]))
            print("     unc:", " | ".join(f"{c['visible']!r} {c['p']:.4f}" for c in e["unconstrained_top10"]))
            if masked:
                print("     kept", e["mass_kept_by_mask"], "allowed tokens", e["mask_allowed_tokens"])
                print("     msk:", " | ".join(f"{c['visible']!r} {c['p']:.4f}" for c in e["masked_renormalised_top10"]))
path = f"runs/ep07/{datetime.date.today()}-candidates-qwen3-8b-4bit.json"
if os.path.exists(path):
    sys.exit(f"{path} exists: record once")
json.dump(out, open(path, "w"), indent=1, ensure_ascii=False)
print("saved", path)
