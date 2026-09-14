// The same request as ten_runs.py, once, in Node. Same URL, same JSON body.
const ALERT = `payments-api: p95 latency 4.8 s for 6 min, error rate 0.9 %,
3 customer reports of failed checkout, last deploy 14 min ago.`;
const PROMPT = `You are the on-call assistant. Alert:
${ALERT}
Reply in one line: P1 or P2, then the first action.`;

const MODEL = "gemini-3.8-flash";
const URL = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`;
const [PRICE_IN, PRICE_OUT] = [0.75, 3.75];   // dollars per million tokens

const res = await fetch(URL, {
  method: "POST",
  headers: { "x-goog-api-key": process.env.GEMINI_API_KEY,
             "content-type": "application/json" },
  body: JSON.stringify({ contents: [{ parts: [{ text: PROMPT }] }] }),
});
const r = await res.json();
const text = r.candidates[0].content.parts.map(p => p.text).join("").trim();
const u = r.usageMetadata;
const out = u.candidatesTokenCount + (u.thoughtsTokenCount ?? 0);
const cost = (u.promptTokenCount * PRICE_IN + out * PRICE_OUT) / 1e6;
console.log(`${text} · ${u.promptTokenCount} in / ${out} out · $${cost.toFixed(4)}`);
