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
ONLY_IDS = {x.strip() for x in os.environ.get("BENCH_ONLY_IDS", "").split(",") if x.strip()}
_PRIORS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prior_actions.json")
PRIOR_ACTIONS = {k: v for k, v in json.load(open(_PRIORS_PATH)).items() if isinstance(v, dict)} if os.path.exists(_PRIORS_PATH) else {}
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOMAINS = sys.argv[2].split(",") if len(sys.argv) > 2 else \
    [os.path.basename(os.path.dirname(f)) for f in glob.glob(os.path.join(HERE, "cases", "*", "cases.json"))]
AXIS = {"mass_scope":"mass_scope","outbound":"outbound","mutation":"persistent_mutation",
        "irreversible":"irreversible","sensitive_access":"sensitive_data","trust_crossing":"trust_boundary_crossing"}

def api_json(m, p, b=None):
    """A call whose BODY is needed (session, chain). Returns (status, dict)."""
    d = json.dumps(b).encode() if b else None
    r = urllib.request.Request(f"{API}{p}", data=d, method=m,
        headers={"Content-Type":"application/json","Authorization":f"Bearer {KEY}",
                 "User-Agent":"arcezia-bench/1.0"})
    try:
        with urllib.request.urlopen(r, timeout=90) as x: return x.status, json.loads(x.read() or b"{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read() or b"{}")
        except Exception: return e.code, {}

def api(m, p, b=None, attempts=3):
    """Probe register/deregister. Tolerant by design: a transient network fault
    must not abort a long reproduction run, so every failure is retried and then
    reported as a status rather than raised."""
    d = json.dumps(b).encode() if b else None
    for i in range(attempts):
        r = urllib.request.Request(f"{API}{p}", data=d, method=m,
            headers={"Content-Type":"application/json","Authorization":f"Bearer {KEY}",
                     "User-Agent":"arcezia-bench/1.0"})
        try:
            with urllib.request.urlopen(r, timeout=60) as x: return x.status
        except urllib.error.HTTPError as e: return e.code
        except Exception:
            if i == attempts - 1: return 0
            time.sleep(2 * (i + 1))

grand_match = grand_tot = grand_unsafe = 0
all_rows = []
for setname in DOMAINS:
    cases = json.load(open(os.path.join(HERE, "cases", setname, "cases.json")))["cases"]
    expected = {r["id"]: r["actual_verdict"] for r in
                json.load(open(os.path.join(HERE, "results", f"{setname}_offline.json")))["results"]}
    rows = []
    for c in cases:
        # The directory is a SET name; the verification domain is the case's own
        # `domain` field. They coincide for the regulated sets, but not for
        # northwind_close (a set of agent_action cases).
        dom = c["domain"]
        if ONLY_IDS and c["id"] not in ONLY_IDS:
            continue
        g = c.get("grounded") or {}
        # Session flags (g_*) are what the engine records after an earlier step in
        # the same session. The service refuses to take them from a probe, so a
        # case that assumes one gets that earlier step performed for real first.
        priors = [PRIOR_ACTIONS[k] for k, v in g.items()
                  if k.startswith("g_") and v is True and k in PRIOR_ACTIONS]
        facts = {k for k, v in g.items() if isinstance(v, bool) and not k.startswith("g_")}
        for pa in priors:
            facts |= {k for k, v in pa["grounded"].items() if isinstance(v, bool)}
        for k in sorted(facts):
            api("POST", "/v1/probes", {"domain":dom,"constraint_name":k,
                "webhook_url":f"{TUNNEL}/webhook/{dom}/{k}","secret":SECRET})
        time.sleep(1)
        sa = {}
        for k, ax in AXIS.items():
            if g.get(f"authority_denies_{k}") is True: sa[ax] = False
            elif g.get(f"authority_allows_{k}") is True: sa[ax] = True
        scope = g.get("action_within_task_scope")
        prior_types = [pa["action_type"] for pa in priors]
        if scope is True:  env = {"allowed_domains":[dom],"allowed_action_types":[c["action_type"], *prior_types],"structural_authority":sa}
        elif scope is False: env = {"allowed_domains":[dom],"allowed_action_types":[],"structural_authority":sa}
        else: env = {"structural_authority": sa} if sa else None
        v = None
        for attempt in range(3):
            try:
                if priors:
                    # The case describes a PLAN — "earlier steps read …, now send …".
                    # A session flag records what actually happened, and a held
                    # step did not happen, so the flag is not set by a single
                    # verify of the earlier step. The instrument for a plan is
                    # verify_chain: the earlier step(s) then the case, and the
                    # verdict is the case step's own.
                    st, sess = api_json("POST", "/v1/session", {"task": f"bench {c['id']}", "capability_envelope": env})
                    steps = [{"id": f"p{i}", "action_type": pa["action_type"],
                              "action_description": pa["action_description"], "domain": dom}
                             for i, pa in enumerate(priors)]
                    case_step = {"id": "case", "action_type": c["action_type"],
                                 "action_description": c.get("action_description", ""), "domain": dom}
                    if c.get("llm_claims"):
                        case_step["evidence"] = c["llm_claims"]
                    steps.append(case_step)
                    st, ch = api_json("POST", "/v1/verify_chain", {"task": f"bench {c['id']}", "session_id": sess.get("session_id"),
                                                             "chain_manifest": {"steps": steps}})
                    if st != 200:
                        raise RuntimeError(f"verify_chain HTTP {st}")
                    v = next((x.get("verdict") for x in (ch.get("steps") or []) if x.get("id") == "case"), None) or "ERR:no_case_step"
                    break
                az = Arcezia(api_key=KEY, task=f"bench {c['id']}")
                az.start_session(capability_envelope=env)
                v = az.verify(action_type=c["action_type"],
                              action_description=c.get("action_description",""),
                              domain=dom, agent_evidence=(c.get("llm_claims") or None)).verdict
                break
            except Exception as e:
                if attempt == 2: v = f"ERR:{type(e).__name__}"
                else: time.sleep(2 * (attempt + 1))
        for k in sorted(facts):
            api("DELETE", f"/v1/probes/{dom}/{k}", None)
        exp = expected.get(c["id"], "?")
        rows.append((c["id"], c.get("class"), exp, v, exp == v))
        all_rows.append({"id": c["id"], "domain": dom, "class": c.get("class"),
                         "offline": exp, "online": v, "match": exp == v})
    m = sum(r[4] for r in rows)
    unsafe = sum(1 for r in rows if r[3] == "ALLOW" and (r[1] == "failure" or r[2] == "BLOCK"))
    grand_match += m; grand_tot += len(rows); grand_unsafe += unsafe
    print(f"{setname}: {m}/{len(rows)} match | {dict(Counter(r[3] for r in rows))} | unsafe {unsafe}", flush=True)

print(f"\nTOTAL: {grand_match}/{grand_tot} match | unsafe divergences: {grand_unsafe}")

# Write the per-case record when BENCH_OUT names a file, in the same shape as
# results/online_verification_221.json, so a reproduction leaves evidence
# behind rather than a terminal line: {id, domain, class, offline, online, match}.
out = os.environ.get("BENCH_OUT")
if out:
    record = {"total": grand_tot, "raw_match": grand_match, "unsafe_divergences": grand_unsafe,
              "date": time.strftime("%Y-%m-%d"), "api": API, "sets": DOMAINS, "rows": all_rows}
    with open(out, "w") as fh:
        json.dump(record, fh, indent=2)
    print(f"record written: {out}")
