# NKP bundle v3 - 2026-10-04

## Files
- nkp_run_all.ipynb   : whole run order in one Colab notebook (cells 1-23)
- nkp_math.py         : claim-checking engine + 28 built-in checks
- nkp_math_redteam.py : red-team sets A, B, C (27 claims each)
- nkp_math_bench.py   : benchmark; --seeds and --out required; --final guard for seeds 100+
- nkp_check.py        : the gate. Run after every AI edit. Must end: RESULT: ALL PASS (also runs ledger + real-test tests)
- sieve_lab.py        : sieve audit, fixed variant, comparison, hybrid helper (numpy only)
- nkp_ledger.py       : SQLite claims ledger (verdict, evidence, source, dependencies, duplicates, risk)
- nkp_realtest.py     : NEW. pre-registered real-claims test: check -> freeze -> run once -> audit
- real_claims_template.txt : claim file format with 9 EX example lines
- label_audit.py      : NEW. independent label cross-check (never imports the engine)
- claims_DRAFT.txt    : NEW. 126 claim lines from four AI answers (batch 1 natural, batch 2 adversarial), labelled, NOT frozen
- label_audit_report.txt  : NEW. independent audit of those labels (0 mismatches on 126)

## Real-claims test (the next milestone)
Criteria (fixed in nkp_realtest.py, part of the fingerprint):
  SIZE >= 50 claims, >= 15 labelled false/conditional, else INCONCLUSIVE
  R1 zero false accepts | R2 >= 90% agreement on decided claims | R3 <= 5% false rejects on true claims
  R4 NOT_CHECKABLE and UNDETERMINED never count as accepts; reported as coverage, not scored
  Run once. A rerun is flagged RERUN. Fixes are judged on a NEW set.
Order: collect claims -> label independently (before running) -> user reviews labels -> check -> freeze -> run -> audit.
Labels come from independent calculation or a reference, never from this engine.

## Where things stand (2026-10-04)
- NKP-Math: dev 0 false accepts; final test (20 fresh seeds, 2600 claims) 0 false accepts, +0.353 over best baseline;
  real claims 17/17; red-team 27/27 x3.  Dev/zoo numbers are partly by construction.
- Sieve: original keeps 1/5 (period-5, aliases). Fixed variant floor(3*frac(n/phi)) gives true 1/3.
  Best use: coverage floor + content scorer (synthetic test only).
- Ledger: 26 checks pass. Real-test harness: 20 checks pass. Gate: ALL PASS.
- Known limits: variable renames not detected as duplicates; trivial claims collapse together; a ledger entry is
  verified math, not a fact about the world; no real-data trial yet (that is what the real-claims test is for);
  cosmetic: row 9 of the real claims prints "0 decimals (true value 1.97e+4)" for 3**9 (verdict is right).

## Claim set status (2026-10-05)
126 lines: batch 1 (ai-A, ai-B natural) = 76, batch 2 (ai-C, ai-D adversarial) = 50.  54 are false/conditional (need >= 15).
26 of 130 stated claims (20%) are outside the engine's claim kinds (derivatives, integrals, arcsin, named constants); listed in the file.
Convention decided by user: "to N decimals" means ROUNDED.  Dimension labels mean dimensional consistency.
Next: user reviews labels -> copy claims_DRAFT.txt to claims.txt -> check -> freeze -> run ONCE -> audit.
Results are reported by batch (b1 natural, b2 adversarial); do not blend them into one headline without that note.

## Next
1. Review labels, freeze, run once. (Original: collect 50-100 claims from AI answers / documents (see prompt in chat), paste to Claude for extraction + labels.
2. Review labels, freeze, run once.
3. Strict LaTeX-to-SymPy converter (unparseable = not checkable). arXiv fetching last.
4. 1/3 conserving splitter once the idea is written precisely.
