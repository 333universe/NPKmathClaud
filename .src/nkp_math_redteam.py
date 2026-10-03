%%writefile nkp_math_redteam.py
"""
Red-team set for NKP-Math: hand-written claims chosen to FOOL the engine (domain traps, precision limits,
hard-but-true identities, subtle falsehoods, near-integers, tricky bounds, unit traps, numerology).

Set A and set B contain DIFFERENT instances of the SAME categories.  Both were written before any fix:
fix the engine using A, then B tells you whether the fix generalizes (B is held out).
Expected verdict classes: accept | reject | conditional     (UNDETERMINED counts as "reject": no proof, no acceptance)

    python nkp_math_redteam.py          run both sets
"""
from __future__ import annotations

import sys
from decimal import ROUND_HALF_UP, Decimal, getcontext

import mpmath as mp

from nkp_math import NKPMath

getcontext().prec = 140
POS = {"x": (0.1, 3.0), "y": (0.1, 3.0)}


def digits(const: str, k: int, delta: int = 0) -> str:
    """Independent computation of a constant to k decimals (mpmath at 160 digits), optionally last digit + delta."""
    with mp.workdps(160):
        v = {"pi": mp.pi, "e": mp.e, "sqrt2": mp.sqrt(2)}[const]
        d = Decimal(mp.nstr(v, 150))
    q = d.quantize(Decimal(1).scaleb(-k), rounding=ROUND_HALF_UP) + delta * Decimal(1).scaleb(-k)
    return format(q, "f")


def dm(kind, **kw):
    return kind, kw


RED_A = [
    ("A1  sqrt(x^2) = x, no domain stated", "identity", dict(lhs="sqrt(x**2)", rhs="x"), "reject"),
    ("A2  sqrt(x^2) = x, declared x>0", "identity", dict(lhs="sqrt(x**2)", rhs="x", domain=POS), "accept"),
    ("A3  log(x^2) = 2 log x, no domain", "identity", dict(lhs="log(x**2)", rhs="2*log(x)"), "reject"),
    ("A4  log(x^2) = 2 log x, declared x>0", "identity", dict(lhs="log(x**2)", rhs="2*log(x)", domain=POS), "accept"),
    ("A5  x = x + 1e-60 x^2", "identity", dict(lhs="x", rhs="x + 10**(-60)*x**2"), "reject"),
    ("A6  pi to 55 decimals (correct)", "value", dict(expr="pi", claimed=digits("pi", 55)), "accept"),
    ("A7  pi to 55 decimals (last digit +1)", "value", dict(expr="pi", claimed=digits("pi", 55, +1)), "reject"),
    ("A8  sin3x = 3sinx - 4sin^3x", "identity", dict(lhs="sin(3*x)", rhs="3*sin(x)-4*sin(x)**3"), "accept"),
    ("A9  cos^4 - sin^4 = cos2x", "identity", dict(lhs="cos(x)**4-sin(x)**4", rhs="cos(2*x)"), "accept"),
    ("A10 cos5x = 16c^5-20c^3+5c", "identity", dict(lhs="cos(5*x)", rhs="16*cos(x)**5-20*cos(x)**3+5*cos(x)"), "accept"),
    ("A11 e^(pi sqrt163) = 640320^3+744", "identity", dict(lhs="exp(pi*sqrt(163))", rhs="640320**3+744"), "reject"),
    ("A12 e^pi - pi = 20", "identity", dict(lhs="exp(pi)-pi", rhs="20"), "reject"),
    ("A13 (x+y)^2 = x^2+y^2", "identity", dict(lhs="(x+y)**2", rhs="x**2+y**2"), "reject"),
    ("A14 sin(x+y) = sin x + sin y", "identity", dict(lhs="sin(x+y)", rhs="sin(x)+sin(y)"), "reject"),
    ("A15 sin^2 x = x^2 - x^4/3 (truncated series)", "identity", dict(lhs="sin(x)**2", rhs="x**2-x**4/3"), "reject"),
    ("A16 |sin x e^-x| > 0.35 on [0,10]  (sup .3224)", "exceeds", dict(expr="sin(x)*exp(-x)", var="x", lo=0, hi=10, c="0.35"), "reject"),
    ("A17 |sin x e^-x| > 0.30 on [0,10]", "exceeds", dict(expr="sin(x)*exp(-x)", var="x", lo=0, hi=10, c="0.30"), "accept"),
    ("A18 |sin x e^-x| > 0.3223 on [0,10]", "exceeds", dict(expr="sin(x)*exp(-x)", var="x", lo=0, hi=10, c="0.3223"), "accept"),
    ("A19 |sin x e^-x| > 0.3224 on [0,10]", "exceeds", dict(expr="sin(x)*exp(-x)", var="x", lo=0, hi=10, c="0.3224"), "reject"),
    ("A20 T = 2 pi sqrt(L/g)", "dimensions", dict(equation="T = 2*pi*sqrt(L/g)", dims={"T": "T", "L": "L", "g": "L T^-2"}), "accept"),
    ("A21 T = 2 pi sqrt(g/L)", "dimensions", dict(equation="T = 2*pi*sqrt(g/L)", dims={"T": "T", "L": "L", "g": "L T^-2"}), "reject"),
    ("A22 E = m v^n (unknown n)", "dimensions", dict(equation="En = m*v**n", dims={"En": "M L^2 T^-2", "m": "M", "v": "L T^-1"}), "conditional"),
    ("A23 E = h f", "dimensions", dict(equation="En = h*f", dims={"En": "M L^2 T^-2", "h": "M L^2 T^-1", "f": "T^-1"}), "accept"),
    ("A24 e^pi - pi ~ 20 is meaningful", "coincidence", dict(a=19.99909997, b=20.0, formula="exp(pi)-pi"), "reject"),
    ("A25 6 pi^5 ~ proton/electron mass ratio", "coincidence", dict(a=1836.118108, b=1836.15267343, formula="6*pi**5"), "reject"),
    ("A26 (x^2-1)/(x-1) = x+1", "identity", dict(lhs="(x**2-1)/(x-1)", rhs="x+1"), "accept"),
    ("A27 x/x = 1", "identity", dict(lhs="x/x", rhs="1"), "accept"),
]

RED_B = [
    ("B1  sqrt(x^4) = x^2 (true for all reals)", "identity", dict(lhs="sqrt(x**4)", rhs="x**2"), "accept"),
    ("B2  sqrt(x^2) = |x| (true for all reals)", "identity", dict(lhs="sqrt(x**2)", rhs="Abs(x)"), "accept"),
    ("B3  log(x^3) = 3 log x, no domain", "identity", dict(lhs="log(x**3)", rhs="3*log(x)"), "reject"),
    ("B4  log(x^3) = 3 log x, declared x>0", "identity", dict(lhs="log(x**3)", rhs="3*log(x)", domain=POS), "accept"),
    ("B5  y = y + 1e-70 y^3", "identity", dict(lhs="y", rhs="y + 10**(-70)*y**3"), "reject"),
    ("B6  e to 50 decimals (correct)", "value", dict(expr="exp(1)", claimed=digits("e", 50)), "accept"),
    ("B7  sqrt2 to 52 decimals (last digit -1)", "value", dict(expr="sqrt(2)", claimed=digits("sqrt2", 52, -1)), "reject"),
    ("B8  cos3x = 4c^3 - 3c", "identity", dict(lhs="cos(3*x)", rhs="4*cos(x)**3-3*cos(x)"), "accept"),
    ("B9  sin^4 - cos^4 = -cos2x", "identity", dict(lhs="sin(x)**4-cos(x)**4", rhs="-cos(2*x)"), "accept"),
    ("B10 sin5x = 16s^5-20s^3+5s", "identity", dict(lhs="sin(5*x)", rhs="16*sin(x)**5-20*sin(x)**3+5*sin(x)"), "accept"),
    ("B11 e^(pi sqrt67) = 5280^3+744", "identity", dict(lhs="exp(pi*sqrt(67))", rhs="5280**3+744"), "reject"),
    ("B12 pi^4 + pi^5 = e^6", "identity", dict(lhs="pi**4+pi**5", rhs="exp(6)"), "reject"),
    ("B13 (x+y)^3 = x^3+y^3", "identity", dict(lhs="(x+y)**3", rhs="x**3+y**3"), "reject"),
    ("B14 cos(x+y) = cos x + cos y", "identity", dict(lhs="cos(x+y)", rhs="cos(x)+cos(y)"), "reject"),
    ("B15 cos^2 x = 1 - x^2 + x^4/3 (truncated)", "identity", dict(lhs="cos(x)**2", rhs="1-x**2+x**4/3"), "reject"),
    ("B16 |cos x e^(-x/2)| > 0.99 on [0,10]", "exceeds", dict(expr="cos(x)*exp(-x/2)", var="x", lo=0, hi=10, c="0.99"), "accept"),
    ("B17 |cos x e^(-x/2)| > 1.01 on [0,10]", "exceeds", dict(expr="cos(x)*exp(-x/2)", var="x", lo=0, hi=10, c="1.01"), "reject"),
    ("B18 |x e^-x| > 0.3678 on [0,10]  (sup 1/e)", "exceeds", dict(expr="x*exp(-x)", var="x", lo=0, hi=10, c="0.3678"), "accept"),
    ("B19 |x e^-x| > 0.3680 on [0,10]", "exceeds", dict(expr="x*exp(-x)", var="x", lo=0, hi=10, c="0.3680"), "reject"),
    ("B20 v = sqrt(2 g h)", "dimensions", dict(equation="v = sqrt(2*g*h)", dims={"v": "L T^-1", "g": "L T^-2", "h": "L"}), "accept"),
    ("B21 v = sqrt(g/h)", "dimensions", dict(equation="v = sqrt(g/h)", dims={"v": "L T^-1", "g": "L T^-2", "h": "L"}), "reject"),
    ("B22 F = m v^n / t (unknown n)", "dimensions", dict(equation="F = m*v**n/t", dims={"F": "M L T^-2", "m": "M", "v": "L T^-1", "t": "T"}), "conditional"),
    ("B23 E = k x^2 / 2 (spring)", "dimensions", dict(equation="En = k*x**2/2", dims={"En": "M L^2 T^-2", "k": "M T^-2", "x": "L"}), "accept"),
    ("B24 2^10 ~ 10^3 is meaningful", "coincidence", dict(a=1024.0, b=1000.0, formula="2**10"), "reject"),
    ("B25 pi^2 ~ g = 9.80665 is meaningful", "coincidence", dict(a=9.8696044, b=9.80665, formula="pi**2"), "reject"),
    ("B26 (x^3-1)/(x-1) = x^2+x+1", "identity", dict(lhs="(x**3-1)/(x-1)", rhs="x**2+x+1"), "accept"),
    ("B27 x (1/x) = 1", "identity", dict(lhs="x*(1/x)", rhs="1"), "accept"),
]


def classify(v) -> str:
    if v.accepted:
        return "accept"
    return "conditional" if v.status == "CONDITIONAL" else "reject"


def run_set(name, items, eng):
    ok = 0
    print(f"\n=== red-team set {name} ===")
    for label, kind, kw, expected in items:
        v = getattr(eng, kind)(**kw)
        got = classify(v)
        good = got == expected
        ok += good
        print(f"{'ok ' if good else 'BAD'} {label:<46} expected {expected:<11} got {v.status:<12} {'' if good else '<- ' + v.detail[:95]}")
    print(f"set {name}: {ok} of {len(items)} correct")
    return ok, len(items)


if __name__ == "__main__":
    eng = NKPMath(seed=1)
    a = run_set("A", RED_A, eng)
    b = run_set("B", RED_B, eng)
    print(f"\nTOTAL {a[0] + b[0]} of {a[1] + b[1]}   (A = used for fixing, B = held out)")
