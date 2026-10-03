"""
Benchmark for NKP-Math.  Two parts, with different meanings:

PART 1  Synthetic claim zoo (labels known BY CONSTRUCTION; each seed = 130 claims)
   identities (true templates; false by coefficient/trig swaps, tiny 1e-2..1e-25 perturbations,
   and decimal "shortfall" arithmetic), decimal value claims (digit-level errors),
   existence bounds (narrow Gaussian peaks), and unit-consistency equations.
   Baselines: Trust (accept all) | Lookup (text match against a textbook list) |
              Float1 (one random point, float64, tol 1e-9) | Float5 (five points).
   This part measures CAPABILITY COVERAGE: which failure modes does each approach catch?  It is not a
   contest on a shared hard task, and the generator and engine were written by the same person.

PART 2  Real claims taken from the user's own documents (ground truth from independent calculations
   done earlier in the project).  This is the meaningful part.

PRE-REGISTERED CRITERIA (written before any run):
  M1  NKP-Math false-accept rate <= 1% overall
  M2  overall accuracy beats the best baseline by > 2 SE (paired over seeds)
  M3  in no family is NKP-Math worse than the best baseline by > 2 SE
  M4  every real case receives the expected verdict
Dev seeds 0-9; final test = fresh seeds 100-119, run once.

    python nkp_math_bench.py --real
    python nkp_math_bench.py --seeds 0:10 --out dev.json ;  python nkp_math_bench.py --report dev.json
"""
from __future__ import annotations

import json
import math
import random
import re
import statistics
import sys
from decimal import ROUND_HALF_UP, Decimal, getcontext

import mpmath as mp
import numpy as np
import sympy as sp

from nkp_math import NKPMath, parse

getcontext().prec = 90
FAMILIES = ["identity", "shortfall", "value", "bound", "dimensions"]
METHODS = ["Trust", "Lookup", "Float1", "Float5", "NKP-Math"]


def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


# ------------------------------------------------------------------ generators
def _true_identity(rng):
    k = rng.randrange(9); a = rng.randint(2, 6)
    return [
        (f"sin({a}*x)**2+cos({a}*x)**2", "1"),
        (f"(x+{a})**3", f"x**3+{3*a}*x**2+{3*a*a}*x+{a**3}"),
        (f"x**2-{a*a}", f"(x-{a})*(x+{a})"),
        (f"cos({2*a}*x)", f"1-2*sin({a}*x)**2"),
        ("sin(x+y)", "sin(x)*cos(y)+cos(x)*sin(y)"),
        (f"exp({a}*x+y)", f"exp(x)**{a}*exp(y)"),
        (f"log(x**{a}*y)", f"{a}*log(x)+log(y)"),
        (f"x**{a}-1", "(x-1)*(" + "+".join(f"x**{j}" for j in range(a)) + ")"),
        (f"phi**{a+2}", f"{fib(a+2)}*phi+{fib(a+1)}"),
    ][k]


def _oracle_identity(L, R):
    """Ground truth for mutated identities, computed independently of the engine (80 digits, 24 points)."""
    r = random.Random(7)
    d = parse(L) - parse(R)
    syms = sorted(d.free_symbols, key=str)
    f = sp.lambdify(syms, d, modules="mpmath")
    mp.mp.dps = 80
    try:
        for _ in range(24):
            pt = [mp.mpf(0.1) + mp.mpf(2.9) * mp.mpf(r.getrandbits(250)) / mp.mpf(2) ** 250 for _ in syms]
            if abs(f(*pt)) > mp.mpf(10) ** -60:
                return False
    finally:
        mp.mp.dps = 50
    return True


def gen_identity(rng):
    L, R = _true_identity(rng)
    dom = {"x": (0.1, 3.0), "y": (0.1, 3.0)} if "log" in L else None       # log identities are claims about positive inputs
    if rng.random() < 0.5:
        return dict(family="identity", L=L, R=R, label=True, domain=dom)
    mode = rng.choice(["perturb", "perturb", "coef", "swap"])
    if mode == "perturb":
        R2 = f"({R})+10**(-{rng.choice([2, 4, 6, 9, 12, 16, 20, 25])})*x**2"
    elif mode == "coef":
        nums = [m for m in re.finditer(r"(?<![\w.*^])\d+(?![\w.])", R)] or [m for m in re.finditer(r"\d+", R)]
        if nums:
            m = rng.choice(nums); R2 = R[:m.start()] + str(int(m.group()) + 1) + R[m.end():]
        else:
            R2 = f"({R})+x"                                           # no numerals to alter: add a term instead
    else:
        R2 = R.replace("sin", "cos", 1) if "sin" in R else R.replace("exp", "exp(1)*exp", 1) if "exp" in R else f"({R})*2"
    return dict(family="identity", L=L, R=R2, label=_oracle_identity(L, R2), domain=dom)


def gen_shortfall(rng):
    n = rng.randint(3, 25)
    if rng.random() < 0.5:
        return dict(family="shortfall", L=f"3*0.{'3'*n}", R="1", label=False)                     # 3 x 0.33..3 = 1 ?
    return dict(family="shortfall", L=f"3*(10**{n}-1)/(3*10**{n})+10**(-{n})", R="1", label=True)


_VALS = ["pi", "phi", "sqrt(2)", "sqrt(3)", "log(2)", "exp(pi)", "2*pi/phi**2", "pi**2/6", "sqrt(5)", "exp(1)"]


def gen_value(rng):
    e = rng.choice(_VALS); k = rng.randint(3, 28)
    v = Decimal(str(sp.N(parse(e), 80)))
    q = v.quantize(Decimal(1).scaleb(-k), rounding=ROUND_HALF_UP)
    if rng.random() < 0.5:
        return dict(family="value", expr=e, claimed=format(q, "f"), label=True)
    bad = q + rng.choice([-1, 1]) * Decimal(1).scaleb(-k)
    return dict(family="value", expr=e, claimed=format(bad, "f"), label=False)


def gen_bound(rng):
    a = round(rng.uniform(0.5, 5), 3); x0 = round(rng.uniform(1, 9), 4)
    w = rng.choice([0.002, 0.01, 0.05]); kk = rng.choice([1, 3]); eps = rng.choice([0.001, 0.01, 0.05])
    true = rng.random() < 0.5
    c = a * (1 - eps) if true else a * (1 + eps)
    return dict(family="bound", expr=f"{a}*exp(-((x-{x0})/{w})**2)*cos({kk}*(x-{x0}))", c=format(Decimal(c).quantize(Decimal("1e-9")), "f"), label=true)


_QD = {"m": "M", "a": "L T^-2", "v": "L T^-1", "d": "L", "t": "T", "F": "M L T^-2", "En": "M L^2 T^-2", "p": "M L T^-1", "P": "M L^2 T^-3"}
_TRUE_EQ = ["F = m*a", "En = m*v**2/2", "p = m*v", "v = d/t", "P = F*v", "En = F*d", "a = v/t", "En = P*t", "d = v*t", "F = p/t"]
_BAD_EQ = ["En = m*v", "F = m*v", "p = m*v**2", "v = d*t", "P = F*d", "En = m*v**2 + m*v", "a = v*t", "En = F*t", "d = v/t", "F = m*sin(d)", "En = m*exp(t)", "P = F*v + m*a"]


def gen_dims(rng):
    true = rng.random() < 0.5
    eq = rng.choice(_TRUE_EQ if true else _BAD_EQ)
    if rng.random() < 0.5:                                        # harmless decoration: a dimensionless factor
        lhs, rhs = eq.split("="); eq = f"{lhs.strip()} = {rng.choice(['2', '3', 'pi', '1/2'])}*({rhs.strip()})"
        if not true and "sin" in eq or not true and "exp" in eq: pass
    return dict(family="dimensions", eq=eq, label=true)


def make_seed(seed):
    rng = random.Random(seed)
    out = [gen_identity(rng) for _ in range(40)] + [gen_shortfall(rng) for _ in range(10)] + [gen_value(rng) for _ in range(30)]
    out += [gen_bound(rng) for _ in range(20)] + [gen_dims(rng) for _ in range(30)]
    return out


# ------------------------------------------------------------------ baselines and engine
def fparse(s):
    return sp.parse_expr(s.replace("^", "**"), local_dict={"phi": sp.GoldenRatio, "pi": sp.pi, "euler": sp.E})


_LOOKUP = {("sin(2*x)**2+cos(2*x)**2", "1"), ("sin(x+y)", "sin(x)*cos(y)+cos(x)*sin(y)"), ("x**2-4", "(x-2)*(x+2)"),
           ("exp(2*x+y)", "exp(x)**2*exp(y)"), ("phi**4", "3*phi+2"), ("(x+2)**3", "x**3+6*x**2+12*x+8")}
_LOOKUP_VALUES = {("pi", "3.14159265358979"), ("phi", "1.6180339887"), ("sqrt(2)", "1.41421356237"), ("exp(1)", "2.71828182845")}
_LOOKUP_EQ = {"F = m*a", "En = m*v**2/2", "p = m*v", "v = d/t"}


def float_check(c, npts, rng):
    f = c["family"]
    if f in ("identity", "shortfall"):
        d = fparse(c["L"]) - fparse(c["R"])
        syms = sorted(d.free_symbols, key=str)
        fn = sp.lambdify(syms, d, "numpy")
        fl = sp.lambdify(syms, fparse(c["L"]), "numpy")
        for _ in range(npts):
            pt = [rng.uniform(0.1, 3.0) for _ in syms]
            if abs(float(fn(*pt))) > 1e-9 * max(1.0, abs(float(fl(*pt)))):
                return False
        return True
    if f == "value":
        return abs(float(sp.N(fparse(c["expr"]), 15)) - float(c["claimed"])) <= 1e-9
    if f == "bound":
        fn = sp.lambdify(sp.Symbol("x"), fparse(c["expr"]), "numpy")
        xs = np.linspace(0, 10, 400 if npts > 1 else 50)
        return bool(np.max(np.abs(fn(xs))) > float(c["c"]))
    return False                                                  # numeric checks cannot see units


def decide(method, c, eng, rng):
    f = c["family"]
    if method == "Trust":
        return True
    if method == "Lookup":
        if f in ("identity", "shortfall"): return (c["L"], c["R"]) in _LOOKUP
        if f == "value": return (c["expr"], c["claimed"]) in _LOOKUP_VALUES
        if f == "dimensions": return c["eq"] in _LOOKUP_EQ
        return False
    if method == "Float1": return float_check(c, 1, rng)
    if method == "Float5": return float_check(c, 5, rng)
    if f in ("identity", "shortfall"): return eng.identity(c["L"], c["R"], domain=c.get("domain")).accepted
    if f == "value": return eng.value(c["expr"], c["claimed"]).accepted
    if f == "bound": return eng.exceeds(c["expr"], "x", 0, 10, c["c"]).status == "PROVED"
    return eng.dimensions(c["eq"], _QD).accepted


def run_seed(seed):
    claims = make_seed(seed); eng = NKPMath(seed=seed); rng = random.Random(seed + 1)
    tally = {m: {fam: [0, 0, 0, 0] for fam in FAMILIES} for m in METHODS}            # correct, total, false-accepts, false-total
    for c in claims:
        for m in METHODS:
            d = decide(m, c, eng, rng)
            t = tally[m][c["family"]]
            t[0] += int(d == c["label"]); t[1] += 1
            if not c["label"]:
                t[3] += 1; t[2] += int(d)
    return tally


# ------------------------------------------------------------------ part 2: real claims from the user's documents
REAL = [
    # (kind, args, expected, source)
    ("identity", ("2*cos(pi/5)", "phi"), "accept", "screenshot:gemini-identity"),
    ("identity", ("phi", "1+1/phi"), "accept", "screenshot:gemini-identity"),
    ("identity", ("phi**2", "phi+1"), "accept", "doc:copilot-parameters"),
    ("identity", ("3*0.3333", "1"), "reject", "screenshot:triadic-flaw"),
    ("identity", ("0.3333+0.3333+0.3333", "0.9999"), "accept", "user:own-arithmetic"),
    ("identity", ("0.3333+0.3333+0.3333+0.0001", "1"), "accept", "user:own-arithmetic"),
    ("identity", ("1-3*(10**8-1)/(3*10**8)", "10**(-8)"), "accept", "screenshot:triadic-flaw"),
    ("value", ("2*pi/phi**2", "2.3999632297"), "accept", "doc:sieve-script"),
    ("value", ("3**9", "19683"), "accept", "screenshot:gemini-tictactoe"),
    ("exceeds", ("sin(x*pi)*phi**(x/10)/(pi*phi)", "x", 0, 10, "0.3333333333333333"), "reject", "doc:gate-script"),
    ("dimensions", ("Gmn = 8*pi*G/c**4*Tmn", {"Gmn": "L^-2", "G": "L^3 M^-1 T^-2", "c": "L T^-1", "Tmn": "M L^-1 T^-2"}), "accept", "gr-baseline"),
    ("dimensions", ("Gmn = 8*pi*G/c**4*(I*sqrt(X))**(1+b)*Tmn/sqrt(X)", {"Gmn": "L^-2", "G": "L^3 M^-1 T^-2", "c": "L T^-1", "Tmn": "M L^-1 T^-2", "X": "M L^-1 T^-2"}), "conditional", "screenshot:copilot-single-equation"),
    ("dimensions", ("Pw = al*Cc*f*V**2", {"Pw": "M L^2 T^-3", "Cc": "Q^2 T^2 M^-1 L^-2", "f": "T^-1", "V": "M L^2 T^-2 Q^-1"}), "accept", "screenshot:google-ai-cpu"),
    ("dimensions", ("Pj = Ic**2*Rr", {"Pj": "M L^2 T^-3", "Ic": "Q T^-1", "Rr": "M L^2 T^-1 Q^-2"}), "accept", "screenshot:google-ai-cpu"),
    ("dimensions", ("Ic = Isat*exp(V)", {"Ic": "Q T^-1", "Isat": "Q T^-1", "V": "M L^2 T^-2 Q^-1"}), "reject", "screenshot:google-ai-cpu"),
    ("dimensions", ("Gmn = rho", {"Gmn": "L^-2"}), "reject", "doc:unified-equation"),
    ("coincidence", (360 * (1 - 1 / ((1 + 5 ** 0.5) / 2)), 137.035999084, "360*(1-1/phi)"), "reject", "user:hydrogen-similarity"),
]


def run_real():
    eng = NKPMath(seed=0); ok = 0
    print(f"{'#':>2} {'source':<34}{'verdict':<13}{'expected':<12} claim / detail")
    for i, (kind, args, exp, src) in enumerate(REAL, 1):
        v = getattr(eng, kind)(*args, source=src)
        got = "accept" if v.accepted else "reject" if v.status in ("REFUTED", "ILL_FORMED", "COINCIDENCE") else "conditional"
        good = got == exp; ok += good
        name = args[0] if isinstance(args[0], str) else f"{args[0]:.4f} vs {args[1]}"
        print(f"{i:>2} {src:<34}{v.status:<13}{exp:<12} {'OK ' if good else 'BAD'} {str(name)[:46]} | {v.detail[:90]}")
    print(f"\nM4: {ok} of {len(REAL)} real claims received the expected verdict -> {'PASS' if ok == len(REAL) else 'FAIL'}")
    print("\nsource track record (true / false / open -> reliability):")
    for s, t, f, o, r in eng.ledger.table():
        print(f"  {s:<34}{t} / {f} / {o}  -> {r:.2f}")
    return ok == len(REAL)


# ------------------------------------------------------------------ reporting
def se(x):
    return statistics.stdev(x) / math.sqrt(len(x)) if len(x) > 1 else 0.0


def report(files):
    runs = []
    for fn in files: runs += json.load(open(fn))
    n = len(runs)

    def acc(r, m, fams):
        c = sum(r[m][f][0] for f in fams); t = sum(r[m][f][1] for f in fams); return c / t

    def fa(r, m):
        a = sum(r[m][f][2] for f in FAMILIES); b = sum(r[m][f][3] for f in FAMILIES); return a / b
    print(f"{n} seeds, {n*130} claims.   accuracy by family (mean over seeds)")
    print(f"{'family':<12}" + "".join(f"{m:>11}" for m in METHODS))
    for fam in FAMILIES + ["ALL"]:
        fams = FAMILIES if fam == "ALL" else [fam]
        print(f"{fam:<12}" + "".join(f"{statistics.mean(acc(r, m, fams) for r in runs):>11.3f}" for m in METHODS))
    print(f"{'false-accept':<12}" + "".join(f"{statistics.mean(fa(r, m) for r in runs):>11.3f}" for m in METHODS))
    best = lambda fams: max(METHODS[:-1], key=lambda m: statistics.mean(acc(r, m, fams) for r in runs))
    print("\nPRE-REGISTERED CRITERIA")
    m1 = statistics.mean(fa(r, "NKP-Math") for r in runs)
    print(f"  M1 false-accept rate {m1:.3f}  {'PASS' if m1 <= 0.01 else 'FAIL'}")
    b = best(FAMILIES); d = [acc(r, "NKP-Math", FAMILIES) - acc(r, b, FAMILIES) for r in runs]
    print(f"  M2 overall vs best baseline ({b}): {statistics.mean(d):+.3f}±{se(d):.3f}  {'PASS' if statistics.mean(d) - 2 * se(d) > 0 else 'FAIL'}")
    ok3 = True
    for fam in FAMILIES:
        b = best([fam]); d = [acc(r, "NKP-Math", [fam]) - acc(r, b, [fam]) for r in runs]
        good = statistics.mean(d) + 2 * se(d) >= 0; ok3 &= good
        print(f"  M3 {fam:<11} vs best baseline ({b}): {statistics.mean(d):+.3f}±{se(d):.3f}  {'ok' if good else 'WORSE'}")
    print(f"  M3 overall: {'PASS' if ok3 else 'FAIL'}")


if __name__ == "__main__":
    a = sys.argv
    if "--real" in a:
        run_real()
    elif "--report" in a:
        report(a[a.index("--report") + 1:])
    else:
        lo, hi = map(int, a[a.index("--seeds") + 1].split(":"))
        res = [run_seed(s) for s in range(lo, hi)]
        json.dump(res, open(a[a.index("--out") + 1], "w"))
        print(f"seeds {lo}:{hi} done")
