"""Probe server for benchmark reproduction.

Arcezia grounds a case's facts by calling YOUR probe webhook. This server plays
that role: it answers each fact from the case's `grounded` values, keyed by the
action description. Run it, expose it over HTTPS (a tunnel is fine), and pass the
URL to reproduce.py. HMAC-signed, same scheme as production.
"""
from __future__ import annotations
import hashlib, hmac, json, glob, os
from fastapi import FastAPI, Request, Response

SECRET = os.environ.get("BENCH_PROBE_SECRET", "arcezia-bench-secret-2026")
_KEY = hashlib.sha256(SECRET.encode()).hexdigest().encode()
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root

CASES: dict[str, dict] = {}
for f in glob.glob(os.path.join(HERE, "cases", "*", "cases.json")):
    for c in json.load(open(f)).get("cases", []):
        CASES[c.get("action_description", "")] = dict(c.get("grounded", {}) or {})

app = FastAPI()

@app.post("/webhook/{domain}/{constraint}")
async def probe(domain: str, constraint: str, request: Request):
    raw = await request.body()
    expected = "sha256=" + hmac.new(_KEY, raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, request.headers.get("X-Arcezia-Signature", "")):
        return Response(status_code=403, content='{"error":"bad signature"}',
                        media_type="application/json")
    grounded = CASES.get(json.loads(raw).get("action_description", ""), {})
    if constraint in grounded and isinstance(grounded[constraint], bool):
        return {"grounded": True, "value": grounded[constraint], "detail": "bench"}
    return {"grounded": False}

@app.get("/health")
def health():
    return {"ok": True, "cases": len(CASES)}
