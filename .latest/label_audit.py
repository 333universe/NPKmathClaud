"""
label_audit.py - INDEPENDENT cross-check of the labels in a claims file.  It never imports nkp_math.py.

    python label_audit.py claims.txt

Methods (deliberately different from the engine's):
  identity    24 random points, 60-digit mpmath arithmetic; true = equal everywhere sampled
              ('conditional' = equal on positive inputs only)
  value       mpmath value rounded half-up to the claimed number of decimals (also reports whether the claim equals
              the TRUNCATED value, which is a convention question, not a calculation question)
  exceeds     max |f| on [lo, hi] from a fine grid, then mpmath root-finding on f' for the exact maximum
  dimensions  recursive dimension algebra (sums need equal dimensions, powers need dimensionless exponents, functions need
              dimensionless arguments); consistent when both sides have the same dimension
Prints one line per claim and flags every disagreement between the file's label and the independent result.
"""
from __future__ import annotations

import json
import random
import re
import sys
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, getcontext

import mpmath as mp
import numpy as np
import sympy as sp

mp.mp.dps = 60
getcontext().prec = 80
LOC = {"pi": sp.pi, "phi": sp.GoldenRatio}
FUN = {"sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "exp": sp.exp, "log": sp.log, "sqrt": sp.sqrt}


def S(text: str):
    return sp.sympify(text, locals={**LOC, **FUN})


def read_claims(path):
    rows = []
    for raw in open(path, encoding="utf-8"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        body, _, orig = line.partition(" ## ")
        f = [p.strip() for p in body.split("|")]
        rows.append(dict(id=f[0], label=f[1].lower(), kind=f[2].lower(), source=f[3], args=f[4:], original=orig.strip()))
    return rows


def audit_identity(args):
    lhs, rhs = S(args[0]), S(args[1])
    dom = json.loads(args[2]) if len(args) > 2 else None
    syms = sorted((lhs - rhs).free_symbols | lhs.free_symbols | rhs.free_symbols, key=str)
    f = sp.lambdify(syms, lhs - rhs, modules="mpmath")
    rnd = random.Random(11)

    def holds(lo_hi):
        for _ in range(24):
            pt = []
            for s in syms:
                lo, hi = lo_hi.get(str(s), (-3.0, 3.0)) if lo_hi else (-3.0, 3.0)
                pt.append(mp.mpf(lo) + (mp.mpf(hi) - mp.mpf(lo)) * mp.mpf(rnd.getrandbits(200)) / mp.mpf(2) ** 200)
            try:
                if abs(f(*pt)) > mp.mpf(10) ** -40:
                    return False
            except Exception:
                continue
        return True
    if dom:
        return "true" if holds({k: tuple(v) for k, v in dom.items()}) else "false"
    pos = holds({str(s): (0.1, 3.0) for s in syms})
    full = holds(None)
    return "true" if full else "conditional" if pos else "false"


def audit_value(args):
    val = mp.mpf(sp.N(S(args[0]), 60))
    claimed = args[1]
    d = len(claimed.split(".")[1]) if "." in claimed else 0
    D = Decimal(mp.nstr(val, 55))
    q = Decimal(1).scaleb(-d)
    rounded, trunc = D.quantize(q, rounding=ROUND_HALF_UP), D.quantize(q, rounding=ROUND_DOWN)
    c = Decimal(claimed)
    note = f"true value {mp.nstr(val, 14)}; rounded {rounded}; truncated {trunc}"
    return ("true" if c == rounded else "false"), note + ("  [claim equals the TRUNCATED value]" if c == trunc and c != rounded else "")


def audit_exceeds(args):
    expr, var, lo, hi, c = S(args[0]), sp.Symbol(args[1]), float(args[2]), float(args[3]), mp.mpf(args[4])
    f = sp.lambdify(var, expr, "mpmath")
    fn = sp.lambdify(var, expr, "numpy")
    df = sp.lambdify(var, sp.diff(expr, var), "mpmath")
    xs = np.linspace(lo, hi, 20001)
    d = np.array([float(df(mp.mpf(x))) for x in xs[::20]])
    cand = [mp.mpf(lo), mp.mpf(hi)]
    for i in range(len(d) - 1):
        if d[i] == 0 or d[i] * d[i + 1] < 0:
            a, b = xs[i * 20], xs[min((i + 1) * 20, len(xs) - 1)]
            try:
                r = mp.findroot(df, (mp.mpf(a) + mp.mpf(b)) / 2)
                if lo <= r <= hi:
                    cand.append(r)
            except Exception:
                pass
    M = max(abs(f(x)) for x in cand)
    return ("true" if M > c else "false"), f"max|f| = {mp.nstr(M, 16)} vs c = {args[4]}"


def audit_dims(args):
    """Recursive dimension algebra, independent of the engine.  Sums need equal dimensions, powers need dimensionless
    exponents, functions need dimensionless arguments.  Returns true when both sides have the same dimension and no
    internal inconsistency was found."""
    eq, dims = args[0], json.loads(args[1])
    base = {}

    def mono(spec):
        out = sp.Integer(1)
        for tok in spec.split():
            m = re.fullmatch(r"([A-Za-z]+)(?:\^(-?[\d/]+))?", tok)
            bs = base.setdefault(m.group(1), sp.Symbol("BASE_" + m.group(1), positive=True))
            out *= bs ** (sp.Rational(m.group(2)) if m.group(2) else 1)
        return out
    D = {k: mono(v) for k, v in dims.items()}
    problems = []

    def dim(e):
        if e.is_Number or e in (sp.pi, sp.E):
            return sp.Integer(1)
        if e.is_Symbol:
            return D[str(e)]
        if e.is_Add:
            ds = [dim(t) for t in e.args]
            if any(sp.simplify(d / ds[0]) != 1 for d in ds):
                problems.append(f"sum mixes dimensions in {e}")
            return ds[0]
        if e.is_Mul:
            out = sp.Integer(1)
            for t in e.args:
                out *= dim(t)
            return out
        if e.is_Pow:
            bd, ed = dim(e.base), dim(e.exp)
            if sp.simplify(ed) != 1:
                problems.append(f"exponent has a dimension in {e}")
            return bd ** e.exp
        if e.is_Function:
            for a in e.args:
                if sp.simplify(dim(a)) != 1:
                    problems.append(f"argument of {e.func.__name__} has a dimension in {e}")
            return sp.Integer(1)
        problems.append(f"unsupported term {e}")
        return sp.Integer(1)
    L, R = [t.strip() for t in eq.split("=")]
    loc = {k: sp.Symbol(k, positive=True) for k in dims}
    lhs, rhs = S(L).xreplace({sp.Symbol(k): v for k, v in loc.items()}), S(R).xreplace({sp.Symbol(k): v for k, v in loc.items()})
    dl, dr = dim(lhs), dim(rhs)
    ratio = sp.simplify(dl / dr)
    ok = ratio == 1 and not problems
    return ("true" if ok else "false"), (f"dim(lhs)/dim(rhs) = {ratio}" + (f"; {problems[0]}" if problems else ""))


def main(path):
    rows = read_claims(path)
    bad = 0
    print(f"{'id':<7}{'file label':<12}{'independent':<13}{'':<5}basis")
    for r in rows:
        try:
            if r["kind"] == "identity":
                res, note = audit_identity(r["args"]), "24-point 60-digit numeric check"
            elif r["kind"] == "value":
                res, note = audit_value(r["args"])
            elif r["kind"] == "exceeds":
                res, note = audit_exceeds(r["args"])
            elif r["kind"] == "dimensions":
                res, note = audit_dims(r["args"])
            else:
                res, note = "n/a", "no independent method written for this kind"
        except Exception as e:
            res, note = "error", f"{type(e).__name__}: {e}"[:90]
        ok = "ok" if res == r["label"] else "<<< MISMATCH"
        bad += ok != "ok"
        print(f"{r['id']:<7}{r['label']:<12}{res:<13}{ok:<13}{note}")
    print(f"\n{len(rows)} claims audited; {bad} label mismatch(es).")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]) if len(sys.argv) > 1 else print(__doc__) or 0)
