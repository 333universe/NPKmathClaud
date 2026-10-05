"""
nkp_check.py - one-file referee gate for NKP-Math.  Run it after EVERY AI edit.

    python nkp_check.py

It never trusts silence.  Each check must print PASS or the whole run ends in FAIL (exit code 1).
Put it in the same folder as nkp_math.py and nkp_math_redteam.py.  Needs sympy and mpmath.

Checks
  1  nkp_math.py still contains its test suite (counted from the code, not from the message it prints)
  2  the test suite runs, prints something, and passes
  3  red-team sets A, B, C all score full marks
  4  zero false accepts (a claim labelled reject/conditional that the engine accepted)
  5  the label-correction note and the A/B annotations are still in the red-team file
  6  if nkp_math_bench.py is present: no literal 'fam' label bug, and no silent seed default
  6c if nkp_ledger.py is present: its tests run and pass
  7  fingerprints of the files, so you can see when something changed
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

MIN_ASSERTS = 28          # the referee had 28 checks; fewer means something was deleted
failures = []


def report(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({note})" if note else ""))
    if not ok:
        failures.append(name)


def read(fn: str) -> str:
    with open(os.path.join(HERE, fn), encoding="utf-8") as f:
        return f.read()


def main() -> int:
    try:
        math_src = read("nkp_math.py")
        red_src = read("nkp_math_redteam.py")
    except FileNotFoundError as e:
        print(f"FAIL  missing file: {e.filename}")
        return 1

    # 1. the tests still exist (the printed "28" is just a literal, so count real assert statements)
    tree = ast.parse(math_src)
    fn = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run_tests"), None)
    n_assert = sum(isinstance(n, ast.Assert) for n in ast.walk(fn)) if fn else 0
    report("test suite present in nkp_math.py", n_assert >= MIN_ASSERTS, f"{n_assert} asserts, need >= {MIN_ASSERTS}")
    report("command-line block present (--test)", '"--test"' in math_src or "'--test'" in math_src)

    # 2. run the tests; empty output counts as failure
    import nkp_math
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            nkp_math.run_tests()
        out = buf.getvalue().strip()
        report("tests ran and passed", bool(out), out if out else "EMPTY OUTPUT = failure")
    except Exception as e:  # AssertionError or anything else
        report("tests ran and passed", False, f"{type(e).__name__}: {e}"[:120])

    # 3 + 4. red-team sets
    import nkp_math_redteam as rt
    eng = nkp_math.NKPMath(seed=1)
    false_accepts = []
    for name, items in (("A", rt.RED_A), ("B", rt.RED_B), ("C", rt.RED_C)):
        ok = 0
        for label, kind, kw, expected in items:
            v = getattr(eng, kind)(**kw)
            got = rt.classify(v)
            ok += got == expected
            if got == "accept" and expected != "accept":
                false_accepts.append(label)
        report(f"red-team set {name}", ok == len(items), f"{ok}/{len(items)}")
    report("zero false accepts", not false_accepts, "; ".join(false_accepts))

    # 5. the honesty record
    report("label-correction note kept", "LABEL CORRECTION" in red_src)
    report("A-fix / B-held-out annotations kept", "used for fixing" in red_src and "held out" in red_src)

    # 6. benchmark guards (only if the file is there)
    bench_src = read("nkp_math_bench.py") if os.path.exists(os.path.join(HERE, "nkp_math_bench.py")) else ""
    if bench_src:
        report("benchmark: family label bug absent", "{'fam'" not in bench_src and '{"fam"' not in bench_src)
        report("benchmark: --seeds required, --final guard present",
               'sys.exit' in bench_src and '"--final"' in bench_src and "or '0:10'" not in bench_src and 'else "0:10"' not in bench_src)

    # 6c. the claims ledger (only if the file is there); empty output counts as failure
    led_path = os.path.join(HERE, "nkp_ledger.py")
    led_src = read("nkp_ledger.py") if os.path.exists(led_path) else ""
    if led_src:
        import nkp_ledger
        lbuf = io.StringIO()
        try:
            with contextlib.redirect_stdout(lbuf):
                nkp_ledger.run_tests()
            lout = lbuf.getvalue().strip()
            report("ledger tests ran and passed", bool(lout), lout if lout else "EMPTY OUTPUT = failure")
        except Exception as e:
            report("ledger tests ran and passed", False, f"{type(e).__name__}: {e}"[:120])

    # 6d. the real-claims test harness (only if the file is there)
    rt_path = os.path.join(HERE, "nkp_realtest.py")
    rt_src = read("nkp_realtest.py") if os.path.exists(rt_path) else ""
    if rt_src:
        import nkp_realtest
        rbuf = io.StringIO()
        try:
            with contextlib.redirect_stdout(rbuf):
                nkp_realtest.run_tests()
            rout = rbuf.getvalue().strip().splitlines()
            report("real-claims harness tests ran and passed", bool(rout) and rout[-1].startswith("all "), rout[-1] if rout else "EMPTY OUTPUT = failure")
        except Exception as e:
            report("real-claims harness tests ran and passed", False, f"{type(e).__name__}: {e}"[:120])

    # 7. fingerprints
    srcs = [("nkp_math.py", math_src), ("nkp_math_redteam.py", red_src)] + ([("nkp_math_bench.py", bench_src)] if bench_src else []) + ([("nkp_ledger.py", led_src)] if led_src else []) + ([("nkp_realtest.py", rt_src)] if rt_src else [])
    for fname, src in srcs:
        print(f"      {fname:<22} sha256 {hashlib.sha256(src.encode()).hexdigest()[:12]}")

    print("\nRESULT:", "ALL PASS" if not failures else f"FAIL ({len(failures)}): " + ", ".join(failures))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
