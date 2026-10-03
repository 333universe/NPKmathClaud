# NKP and Physics Mimic: Project Summary
**As of 2026-10-03.** Every file named here was re-verified on this date from a clean folder (see `VERIFICATION.txt`). All headline numbers below were regenerated from the saved result files (`RESULTS_FROM_SAVED_DATA.txt`), not copied from memory.

---

## 1. Goal and ground rules

- **Goal:** an engine an AI can use for effective, efficient acquisition of new knowledge (NKP, the New Knowledge Pattern). The motivation is the physics "mimic" project, where AI tends to stop at standard GR and QM.
- **Your ground rule:** a design only counts as improved if it measurably beats simple baselines. If it doesn't, we don't pursue it.
- **How we kept ourselves honest:** pass/fail criteria were written down before final tests, final tests used fresh random seeds, and failures were reported.
- **Caveat:** the simulator and the baselines were built by me. Results show the mechanism works in simulation, not that it works on real data.

## 2. Status of each design

| Design | File | Status |
|---|---|---|
| v2: text-surprisal engine with adaptive "entropy horizon" | `nkp_engine.py` | Works (6 tests). Superseded, still used by the triage benchmark. |
| v3: belief store + acquisition planner | `nkp_acquire.py` | Works (11 tests) but **failed the benchmark**: worse than the baseline in all 12 cells. Kept for the record. |
| v4: observation-ledger engine; `NKPv41` = K-aware version | `nkp_v4.py` | Works (7 tests). **Recommended: `NKPv41`.** |
| Benchmarks | `nkp_bench.py` (worlds A, B), `nkp_fewsource.py` (world C), `nkp_triage.py` (worlds U1-U3), `nkp_regress.py` | Verified |
| Physics-material tests | `physics_tests/` | cipher, golden-angle scan, batch tests, SD-card tests |
| **NKP-Math** (claims are math objects; sources are computations) | `nkp_math.py` | **New.** Works (28 checks). See section 6b. |
| NKP-Math benchmark and red-team | `nkp_math_bench.py`, `nkp_math_redteam.py` | **New.** Verified. |

## 3. How it got here

1. **First notebook** (pi digits, a constant of 118): the labels did not match the mechanism. Rebuilt on real prediction error.
2. **v2:** text surprisal plus an adaptive horizon. You asked to drop the visual.
3. **v3:** belief store and planner. The benchmark showed it lost to a simple baseline. Two causes: the planner looped on echo sources (about 93% of queries returned nothing new), and volatile facts were never refreshed.
4. **v4:** observation ledger, novelty-aware planner, learned source reliability, copy detection. Two bugs were found while building it and fixed on development seeds: a biased reliability learner and false copy merges.
5. **Final test:** code frozen (checksums recorded), run once on fresh seeds.
6. **Few-source world:** exposed a modelling error. Confidence was too low whenever a domain has many possible values. Fixed with a Bayes-correct likelihood, giving v4.1.
7. **Triage benchmark:** tested your idea of a second, text-novelty alarm.

## 4. Headline results

- **Worlds A and B (final test, 30 fresh seeds per cell):** v4 beat the baseline on accuracy in **10 of 12 cells** (+0.011 to +0.097). Two cells were ties (A with hidden origins at budget 4; B with visible origins at budget 2). It was better calibrated in **12 of 12** (ECE 0.05 to 0.22 lower). The strict criterion, "every cell passes," **failed**. v3 was worse than the baseline on accuracy in all 12 cells (-0.04 to -0.23).
- **Ablations:** copy detection mostly helps at budget 8 with hidden origins. Reliability learning is mixed in worlds A and B.
- **Few-source world C (fresh seeds):** v4 failed calibration (ECE worse by 0.04 to 0.08). **v4.1 passed all 9 criteria:** accuracy +0.065 to +0.070 over the baseline, ECE 0.04 to 0.08 better, and learning added +0.018 to +0.033.
- **Regression check, v4.1 vs v4** (A and B, budget 4, fresh seeds): no accuracy loss, and better calibration in all four cells.
- **Triage, text-novelty hybrid** (fresh seeds): passed all 4 criteria. Gains were +0.139 where errors use rare words (a world built to favor it), +0.010 with realistic novel events, and 0.000 (no harm) where text carries no signal.

## 5. Known gaps

- Single-valued facts only; objects are matched as strings ("MIT" and "MIT License" count as different).
- v4 has no save/load, and no horizon triage inside the engine.
- **v4.1 has not been re-run on the full 12-cell grid or on the triage benchmark.**
- Everything is synthetic. No real-data trial yet.
- The hybrid's combination rule and its "verified" definition were changed on development seeds, before the final test.

## 6. Physics mimic: what was reviewed

- **Cipher:** fails. Round trip returned `[0.84, 0.31, 0.16, ...]` for inputs `[42, 108.5, 256.12, ...]`; a wrong key gives identical output; six inputs become two numbers; a "removed" branch is still in the code.
- **"Unified equation":** type errors (a real tensor minus a density operator), undefined n, and S = 0 is not the action principle (δS = 0 is). GR orbits precess; they are not closed.
- **Golden angle:** optimal for spiral packing (ranked #1 of 1,801 angles), but that says nothing about physical law.
- **1/3 "remainder":** a truncation artifact of decimal; it vanishes in base 3.
- **Sieve script:** keeps 2 of 12 tokens and repeats a period-5 pattern 99.98% of the time.
- **Gate script:** never opens (max 0.311 against a threshold of 0.333; bounded by 1/π).
- **TriEn engine:** works as a phase-locked averager. Repeating signal + noise: error 0.302 → 0.191. Non-repeating signal: worse, 0.301 → 0.516.
- **Repaired-gravity candidate (P_μν):** the only item that could modify GR. Needs a sign fix, defined parameters, and conservation.
- **Hydrogen "similarity":** probably the golden angle (137.508°) vs 1/α (137.036), a 0.34% gap, about 10⁷ times larger than α's measurement precision.
- **What would make it functional:** a well-typed model, one domain with known numbers to reproduce, a specific small correction compared with measurement bounds, and a test of whether anything singles out the chosen constants.

## 6b. NKP-Math (new): an engine for math instead of text

Claims are mathematical objects and the "sources" are computations: exact algebra, 120-digit numerics, interval arithmetic, unit analysis, and a coincidence meter (evidence in bits = precision - formula cost - search freedom). A ledger tracks which claim sources survive computation.

- **Real claims from your documents:** 17 of 17 received the expected verdict. Examples: the gate script is *proved* impossible; "3 x 0.3333 = 1" is refuted; Copilot's "single equation" is consistent with GR only if b = 0; the diode-table shorthand `I ~ e^V` is dimensionally ill-formed; golden angle vs 1/alpha scores -43 bits (coincidence).
- **Synthetic zoo (fresh seeds 200-219, run once):** all pre-registered criteria pass. False-accept rate 0.000. Accuracy 1.000 vs 0.635 for the best baseline (float checks) and 0.551 for text lookup. **This is by construction:** each test family targets something the engine checks, so it shows coverage, not general ability.
- **Red-team (50+ hand-written claims meant to fool it):** the first run found 7 false accepts in three families: claims true only for positive numbers (`sqrt(x^2) = x`), differences below 1e-35 (`x = x + 1e-60 x^2`), and wrong last digits in 50+ decimal claims. Fixes: no stated domain now means "all reals" (positive-only claims get verdict CONDITIONAL), exact algebra catches differences of any size between rational expressions, and precision follows the claim. After the fixes: set A 27/27 and set B 27/27 (under the original labels: 25/27 and 26/27, with zero false accepts; three domain-trap claims were relabelled "conditional" and this is disclosed in the file). Set C, written after the fixes, scored 27/27.
- **Known limits:** non-rational differences below 1e-90 are invisible to the numeric check; claims with an unstated domain are read as "all reals"; interval proofs are univariate only; no claim-dependency tracking yet; a proof assistant (Lean) is not used.
- **Grok's Lean 4 / NetworkX proposal was tested and rejected:** the Lean file stores names as strings and verifies nothing (the contradiction checker is a stub returning false); the Python graph rejected a valid proof, deleted existing proof links, and crashed on `get_proof_chain`.
- **Your Colab notebook (`NKPmathClaud`):** much cleaner (13 cells, 173 KB) and it reproduces the results. Fix list: three cells ran before their files existed (delete them); its copy of the benchmark has a labelling bug (`{'fam':<12}` prints "fam" on every row); the family accuracies it showed (identity 0.949) were a real regression from my first domain fix, now corrected; and the ledger's reliabilities reflect which claims I picked, not true source quality.

## 7. Review of your first Colab notebook (`NKPrough`)

**The direction is good:** replacing token-level surprisal with sentence-embedding novelty could handle paraphrases. **But the notebook does not currently run top to bottom, and it has no completed result.** Findings:

1. It uses the **early draft** of `nkp_v4.py` (the biased learner), not the final tested version.
2. The `nkp_engine.py` cell is a **stub** (`class PredictiveModel: pass`).
3. **Bug:** `tm_all.learn(text)` is called without a slot, and `TextModel.learn` only stores embeddings when a slot is given. The "Text-all" channel therefore always returns 1.0 (I confirmed this with a stand-in). Also `if slot:` skips slot 0.
4. **Scale mismatch:** the z-score code has a floor of 0.5, tuned for "bits." Cosine distances vary far less, so the text alarm would almost never fire.
5. The model is loaded twice per run, so it's very slow. The triage run ended in a KeyboardInterrupt with no results.
6. Cells are out of order (modules imported before they are written), giving ModuleNotFoundError.
7. The official test seeds 100-139 were reused for a changed design. Use fresh seeds (for example 500-539).
8. Sentence embeddings place opposites close together ("normal" and "abnormal"), so this signal measures novel content, not truth.

## 8. Next steps (priority order)

0. **NKP-Math next:** claim dependency tracking (if a claim is refuted, flag everything built on it), a multivariable bound checker, and testing claims you can verify yourself.
1. On the laptop, sort material into three piles: computes something and tested, well-formed but untested, narrative or analogy. Search for "hydrogen", "Rydberg", "Balmer", "eV", "137".
2. Run the "conserving splitter" experiment (divide by three repeatedly, with and without carrying the remainder).
3. Repair the P_μν equation and test it against solar-system bounds.
4. Fix the notebook (items above) and test the semantic text model on fresh seeds against the token-based hybrid.
5. Re-run v4.1 on the full grid and the triage benchmark.
6. A real-data trial: claims you can check.

## 9. Files and how to run

Unzip the bundle. In the `nkp/` folder:

```
python nkp_v4.py --test
python nkp_acquire.py --test
python nkp_engine.py --test
python nkp_triage.py --dev --quick
python nkp_bench.py --dev --quick
```

NKP-Math: `python nkp_math.py --test`, `python nkp_math_redteam.py`, `python nkp_math_bench.py --real`.

On a phone, open `NKP_colab_runner.ipynb` in Google Colab, upload the zip, and run the cells. `MANIFEST_SHA256.txt` lets you check that files are intact.

## 10. Corrections to earlier statements

- My first math-engine unit test had a bug (Decimal precision); fixed. The first benchmark generator crashed on identities with no numbers; fixed. My first domain fix made true log identities return CONDITIONAL in the benchmark; the generator now declares their domain.
- The red-team relabelling (A1, A3, B3) is disclosed in `nkp_math_redteam.py`.
- I twice said the final test was "still running." It had died. It was rerun in foreground chunks, and the results here come from complete runs.
- If your phone holds an older `nkp_v4.py` from the first download card, replace it. That early draft had a biased learner and a flawed test.
