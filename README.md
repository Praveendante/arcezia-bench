# Arcezia Benchmark

**Reproducible efficacy data for agent-safety verification.** Clone this, run one
command against the hosted engine, and get our published numbers on your machine.

The engine is sealed and hosted. The **tests are open**: every case, every
expected verdict, and the harness that produces them are in this repo. You do not
have to trust a slide — you can re-run the measurement.

---

## What is measured

**235 cases: 221 across 6 regulated domains, plus a 14-case free-tier set anyone
can run.** Each case is a concrete agent action with its grounded evidence, and
each carries the verdict the engine actually returned — `ALLOW`, `BLOCK`, or
`REVIEW`.

| Domain | Cases | What it gates |
|---|---|---|
| `eu_ai_act` | 47 | EU AI Act deployer obligations (Art. 26): transparency, human oversight, conformity, bias audit, data governance |
| `payment_ops` | 35 | AML, sanctions, fraud, duplicate transactions, recipient verification |
| `financial_compliance` | 35 | AML/KYC/sanctions, structuring, audit trail |
| `government_ops` | 35 | Clearance, need-to-know, two-person integrity, ATO accreditation, export control |
| `pii_ops` | 35 | GDPR legal basis, consent, cross-border safeguards, retention |
| `healthcare_ops` | 34 | HIPAA: PHI authorization, BAA, patient consent, encryption, audit logging |
| **`northwind_close`** | **14** | **A month-end close with three planted errors — runs on the free tier, so anyone can reproduce it** |

**Every failure case cites a real, documented incident** — not an invented
scenario. Sources include the Dutch SyRI ruling, Robodebt Royal Commission,
SCHUFA (CJEU C‑634/21), Wirecard, Bangladesh Bank, Capital One, the Dutch
*toeslagenaffaire*, FTC actions (GoodRx, BetterHelp, Kochava), HHS OCR
settlements, and Glovo/Foodinho. See [`cases/incidents_researched.json`](cases/incidents_researched.json).

## Published results

| Measurement | Result |
|---|---|
| Regulated corpus | **221** cases across 6 domains |
| Live reproduction vs. published verdicts | **221/221** (216/221 raw; see *Known artifact* below) |
| **Unsafe divergences** | **0** |
| Free-tier set (`northwind_close`) | **14/14**, verified against the same engine |

The 221/221 live figure covers the six regulated domains. `northwind_close` is
verified separately and is the set you can reproduce without a paid tier.

**Unsafe divergence** = a failure-class case, or a case published as `BLOCK`, that
the live engine returned as `ALLOW`. There were none. This is the property that
matters: the gate never became more permissive in production than published.

Raw per-case data: [`results/online_verification_221.json`](results/online_verification_221.json).

### Known artifact (disclosed, not hidden)

5 of 221 cases differed on the raw live run: all five are *legitimate* cases that
deliberately leave `action_within_task_scope` **ungrounded** to test the
"unknown scope → REVIEW" path. The reproduction harness was applying a
domain-scoping capability envelope, which grounds scope to `true` — so those
returned `ALLOW` instead of `REVIEW`. That is a harness bug, not an engine or
case error; it is fixed in `harness/reproduce.py` (scope is now grounded only
when the case grounds it). Corrected, live reproduction is 221/221.

We publish this rather than the rounder number because a benchmark you cannot
audit is not evidence.

## Reproduce it

```bash
pip install arcezia fastapi uvicorn
export ARCEZIA_API_KEY=ar_live_...        # https://arcezia.com — free tier available

# 1. Serve the case evidence as probe webhooks (Arcezia calls back into this)
python3 -m uvicorn harness.probe_server:app --port 8893

# 2. Expose it over HTTPS (any tunnel works)
ngrok http 8893

# 3. Reproduce — start with the free-tier set, which needs nothing but a free key
python3 harness/reproduce.py https://<your-tunnel-url> northwind_close
```

Expected: `northwind_close: 14/14 match | {'ALLOW': 11, 'BLOCK': 3} | unsafe 0`.

That set is a month-end close where three entries are wrong — an invoice that is
not in the ledger, a balancing plug with no supporting document, and a wire
transfer outside the authorised task. Eleven ordinary entries pass. It runs on
`agent_action`, so **a free key reproduces it in full**.

**The six regulated domains sit above the free tier** (`payment_ops` and
`pii_ops` are Team; `eu_ai_act`, `healthcare_ops`, `financial_compliance` and
`government_ops` are Enterprise — see arcezia.com/pricing). With a key at that
tier, run everything:

```bash
python3 harness/reproduce.py https://<tunnel>                       # all sets
python3 harness/reproduce.py https://<tunnel> payment_ops,pii_ops   # a subset
```

Evaluating and want the regulated sets without buying a tier first? Mail
**research@arcezia.com** and we will issue a time-boxed evaluation key.

## Methodology — why these cases and not others

A case set is only meaningful if it exercises the whole rulebook. We define
completeness formally and check it mechanically, rather than asserting coverage.

For a domain **D**, the set is complete when all five hold:

| | Criterion | Meaning |
|---|---|---|
| **Q1** | Verdict totality | `ALLOW`, `BLOCK`, and `REVIEW` all occur — the gate discriminates, it is not stuck |
| **Q2** | Gate liveness | Every gating constraint is *decisive* in some case: grounding it and flipping it flips the verdict |
| **Q3** | Rule activation | Every domain rule fires in some case |
| **Q4** | Polarity | Every refutable fact appears at both poles — satisfied, and refuted-to-BLOCK |
| **Q5** | Reality | Every failure case cites a real, resolving documented incident |

**Q2 is the load-bearing check, and it is a counterfactual, not a string match.**
Most blocks here are rule-driven, and a rule's consequent can force `BLOCK`
without ever appearing in the certificate's `violated` list. So "decisive" is
established by re-running the engine with the constraint flipped and observing
the verdict change. An earlier membership-based check under-reported coverage as
1/33 where the counterfactual reports 33/33 — the cases were complete; the
checker was wrong.

All six domains satisfy Q1–Q5.

The corpus size follows from this rather than from a target:
`|S| ≥ max(|gating constraints|, 2·|refutable facts|, |rules|, |incidents|, 3)`.

## Honest limits

- **Citation resolvability is verified; citation content is sampled.** All 139
  distinct incident URLs resolve (0 dead — two dead links were found and replaced
  during verification). A subset was read end-to-end to confirm the incident
  supports the failure mode it is mapped to. Several official sources (SEC, FTC,
  AUSTRAC, Robodebt) block automated fetching but are live.
- **These are the regulated domains, not all 18.** The remaining domains have
  scenario coverage but not the full Q1–Q5 case treatment.
- **Coverage-complete is not exhaustive.** Each set is the complete-plus-margin
  minimum over its rulebook, not the full space of failure modes in that industry.
- **Reproduction requires the hosted engine.** The verification method is sealed
  and patent-pending. This repo contains the
  inputs, the expected outputs, and the harness — never the engine.

## Layout

```
cases/<domain>/cases.json        the case set: action, grounded evidence, expected verdict, incident
cases/incidents_researched.json  the documented real incidents behind the failure cases
results/<domain>_offline.json    published per-case verdicts
results/online_verification_221.json   the live reproduction record
harness/probe_server.py          serves case evidence as probe webhooks
harness/reproduce.py             runs the corpus against the hosted engine and diffs
```

---

Questions, or want a domain added: **research@arcezia.com** · [arcezia.com](https://arcezia.com)
