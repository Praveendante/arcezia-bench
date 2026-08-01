"""Reproduce the Arcezia benchmark against the hosted engine (api.arcezia.com).

For each case: register only its own probes, verify through the installed SDK,
compare the real verdict to the published expectation, deregister. Per-case probe
isolation keeps webhook load low so a public tunnel is not throttled.

  export ARCEZIA_API_KEY=ar_live_...        # a key with access to the domains you run
  python3 reproduce.py https://<your-public-probe-url>   [domain1,domain2,...]

A free-tier key reproduces the free domains; the regulated domains
(payment/healthcare/financial/government/pii/eu_ai_act) need their tier. The
published results in ../results were produced this way against production v27.
"""
import json, glob, os, sys, urllib.request, time
from collections import Counter
from arcezia import Arcezia

API = os.environ.get("ARCEZIA_API_URL", "https://api.arcezia.com")
KEY = os.environ["ARCEZIA_API_KEY"]
SECRET = os.environ.get("BENCH_PROBE_SECRET", "arcezia-bench-secret-2026")
TUNNEL = sys.argv[1]
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOMAINS = sys.argv[2].split(",") if len(sys.argv) > 2 else \
    [os.path.basename(os.path.dirname(f)) for f in glob.glob(os.path.join(HERE, "cases", "*", "cases.json"))]
AXIS = {"mass_scope":"mass_scope","outbound":"outbound","mutation":"persistent_mutation",
        "irreversible":"irreversible","sensitive_access":"sensitive_data","trust_crossing":"trust_boundary_crossing"}

def api(m, p, b=None):
    d = json.dumps(b).encode() if b else None
    r = urllib.request.Request(f"{API}{p}", data=d, method=m,
        headers={"Content-Type":"application/json","Authorization":f"Bearer {KEY}","User-Agent":"arcezia-bench/1.0"})
    try:
        with urllib.request.urlopen(r, timeout=30) as x: return x.status
    except urllib.error.HTTPError as e: return e.code

grand_match = grand_tot = grand_unsafe = 0
for dom in DOMAINS:
    cases = json.load(open(os.path.join(HERE, "cases", dom, "cases.json")))["cases"]
    expected = {r["id"]: r["actual_verdict"] for r in
                json.load(open(os.path.join(HERE, "results", f"{dom}_offline.json")))["results"]}
    rows = []
    for c in cases:
        g = c.get("grounded") or {}
        for k in [k for k, v in g.items() if isinstance(v, bool)]:
            api("POST", "/v1/probes", {"domain":dom,"constraint_name":k,
                "webhook_url":f"{TUNNEL}/webhook/{dom}/{k}","secret":SECRET})
        time.sleep(1)
        sa = {}
        for k, ax in AXIS.items():
            if g.get(f"authority_denies_{k}") is True: sa[ax] = False
            elif g.get(f"authority_allows_{k}") is True: sa[ax] = True
        scope = g.get("action_within_task_scope")
        if scope is True:  env = {"allowed_domains":[dom],"allowed_action_types":[c["action_type"]],"structural_authority":sa}
        elif scope is False: env = {"allowed_domains":[dom],"allowed_action_types":[],"structural_authority":sa}
        else: env = {"structural_authority": sa} if sa else None
        try:
            az = Arcezia(api_key=KEY, task=f"bench {c['id']}")
            az.start_session(capability_envelope=env)
            v = az.verify(action_type=c["action_type"], action_description=c.get("action_description",""),
                          domain=dom, agent_evidence=(c.get("llm_claims") or None)).verdict
        except Exception as e:
            v = f"ERR:{type(e).__name__}"
        for k in [k for k, val in g.items() if isinstance(val, bool)]:
            api("DELETE", f"/v1/probes/{dom}/{k}", None)
        exp = expected.get(c["id"], "?")
        rows.append((c["id"], c.get("class"), exp, v, exp == v))
    m = sum(r[4] for r in rows)
    unsafe = sum(1 for r in rows if r[3] == "ALLOW" and (r[1] == "failure" or r[2] == "BLOCK"))
    grand_match += m; grand_tot += len(rows); grand_unsafe += unsafe
    print(f"{dom}: {m}/{len(rows)} match | {dict(Counter(r[3] for r in rows))} | unsafe {unsafe}", flush=True)

print(f"\nTOTAL: {grand_match}/{grand_tot} match | unsafe divergences: {grand_unsafe}")
