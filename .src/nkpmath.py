
"""
NKP-Math: claim checking where claims are MATHEMATICAL OBJECTS and sources are COMPUTATIONS.

Text engines can only compare strings; this one asks "is it true?" and computes the answer.
Claim types (each returns a Verdict):
  identity(lhs, rhs)            symbolic proof, else 50-digit random-point testing (finds counterexamples)
  value(expr, "3.14159")        evaluate to 60 digits, compare to the claimed decimal at ITS precision
  exceeds(expr, x, lo, hi, c)   does |f(x)| exceed c somewhere?  interval arithmetic + branch-and-bound:
                                can PROVE "never" (sup bound) or FIND a witness
  dimensions("F = m*a", dims)   units check, with symbolic exponents ("consistent only if b = 0")
  coincidence(a, b, formula)    evidence in BITS = precision bits - formula bits - search bits
Statuses: PROVED, VERIFIED, SUPPORTED, CONSISTENT (accept) | REFUTED, ILL_FORMED, COINCIDENCE (reject)
          CONDITIONAL, UNDETERMINED, SIGNIFICANT (reported as-is)
A SourceLedger keeps the track record of whoever made each claim (NKP's source-reliability idea, but
with ground truth supplied by computation instead of consensus).

Needs sympy and mpmath (both preinstalled in Colab).   python nkp_math.py --test
"""
from __future__ import annotations

import math
import random
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import mpmath as mp
import sympy as sp

mp.mp.dps = 50
ACCEPT = {"PROVED", "VERIFIED", "SUPPORTED", "CONSISTENT", "SIGNIFICANT"}
REJECT = {"REFUTED", "ILL_FORMED", "COINCIDENCE"}

_FUNCS = ("sin", "cos", "tan", "exp", "log", "sqrt", "Abs", "atan", "sinh", "cosh", "tanh")
_GLOBALS = {k: getattr(sp, k) for k in ("Symbol", "Integer", "Float", "Rational", "Function", "Dummy") + _FUNCS}
_GLOBALS["__builtins__"] = {}
_LOCALS = {"phi": sp.GoldenRatio, "pi": sp.pi, "euler": sp.E}
_TRANSFORMS = sp.parsing.sympy_parser.standard_transformations + (sp.parsing.sympy_parser.convert_xor,)


def parse(s: str):
    """Parse text into a sympy expression.  Decimals become exact Rationals ("0.3333" is NOT a binary float)."""
    s = re.sub(r"(?<![\w.])(\d+\.\d+)(?![\w.])", r"Rational('\1')", s)
    return sp.parse_expr(s, local_dict=dict(_LOCALS), global_dict=dict(_GLOBALS), transformations=_TRANSFORMS)


@dataclass
class Verdict:
    status: str
    detail: str
    ms: float = 0.0

    @property
    def accepted(self) -> bool:
        return self.status in ACCEPT


class SourceLedger:
    """Track record of claim sources, scored by what computation found."""

    def __init__(self):
        self.c: Dict[str, Counter] = {}

    def record(self, source: Optional[str], status: str) -> None:
        if source is None:
            return
        k = self.c.setdefault(source, Counter())
        if status in ACCEPT:
            k["true"] += 1
        elif status in REJECT:
            k["false"] += 1
        else:
            k["open"] += 1

    def reliability(self, source: str) -> float:
        k = self.c.get(source, Counter())
        return (k["true"] + 1) / (k["true"] + k["false"] + 2)      # Beta(1,1) prior

    def table(self) -> List[Tuple[str, int, int, int, float]]:
        return sorted(((s, k["true"], k["false"], k["open"], self.reliability(s)) for s, k in self.c.items()),
                      key=lambda r: -r[4])


class NKPMath:
    def __init__(self, n_points: int = 12, seed: int = 0, node_limit: int = 4000):
        self.n_points, self.rng, self.node_limit = n_points, random.Random(seed), node_limit
        self.ledger = SourceLedger()

    def _done(self, v: Verdict, t0: float, source: Optional[str]) -> Verdict:
        v.ms = (time.perf_counter() - t0) * 1000
        self.ledger.record(source, v.status)
        return v

    # ------------------------------------------------------------------ identity
    def identity(self, lhs: str, rhs: str, domain: Optional[Dict[str, Tuple[float, float]]] = None,
                 source: Optional[str] = None) -> Verdict:
        t0 = time.perf_counter()
        L, R = parse(lhs), parse(rhs)
        d = L - R
        syms = sorted(d.free_symbols, key=str)
        if not syms:
            if sp.simplify(d) == 0:
                return self._done(Verdict("PROVED", "exact: the difference simplifies to 0"), t0, source)
            val = sp.N(d, 60)
            if abs(val) > sp.Float(10) ** -40:
                return self._done(Verdict("REFUTED", f"lhs - rhs = {sp.N(d, 12)}"), t0, source)
            return self._done(Verdict("SUPPORTED", "agrees to 40 digits (not proved symbolically)"), t0, source)
        domain = domain or {}
        fL, fR = sp.lambdify(syms, L, modules="mpmath"), sp.lambdify(syms, R, modules="mpmath")
        for _ in range(self.n_points):
            pt = []
            for s in syms:
                lo, hi = domain.get(str(s), (0.1, 3.0))
                pt.append(mp.mpf(lo) + (mp.mpf(hi) - mp.mpf(lo)) * mp.mpf(self.rng.getrandbits(170)) / mp.mpf(2) ** 170)
            a, b = fL(*pt), fR(*pt)
            if abs(a - b) > mp.mpf(10) ** -35 * max(1, abs(a), abs(b)):
                where = ", ".join(f"{s}={mp.nstr(v, 6)}" for s, v in zip(syms, pt))
                return self._done(Verdict("REFUTED", f"counterexample at {where}: lhs-rhs = {mp.nstr(a - b, 6)}"), t0, source)
        if sp.simplify(d) == 0 or sp.simplify(sp.expand_trig(d)) == 0:
            return self._done(Verdict("PROVED", "symbolic: the difference simplifies to 0"), t0, source)
        return self._done(Verdict("SUPPORTED", f"agrees to 35 digits at {self.n_points} random points; not proved"), t0, source)

    # ------------------------------------------------------------------ value
    def value(self, expr: str, claimed: str, source: Optional[str] = None) -> Verdict:
        t0 = time.perf_counter()
        v = mp.mpmathify(str(sp.N(parse(expr), 60)))
        decimals = len(claimed.split(".")[1]) if "." in claimed else 0
        tol = mp.mpf(10) ** (-decimals) / 2
        err = abs(v - mp.mpf(claimed))
        if err <= tol * (1 + mp.mpf(10) ** -15):
            return self._done(Verdict("VERIFIED", f"matches to the claimed {decimals} decimals (true value {mp.nstr(v, decimals + 3)})"), t0, source)
        return self._done(Verdict("REFUTED", f"claimed {claimed}; true value {mp.nstr(v, decimals + 3)} (error {mp.nstr(err, 3)})"), t0, source)

    # ------------------------------------------------------------------ bound (interval arithmetic)
    def exceeds(self, expr: str, var: str, lo, hi, c, source: Optional[str] = None) -> Verdict:
        """Claim: there is an x in [lo, hi] with |f(x)| > c.  Proves 'never' or finds a witness."""
        t0 = time.perf_counter()
        x = sp.Symbol(var)
        e = parse(expr).subs(sp.GoldenRatio, (1 + sp.sqrt(5)) / 2)
        iv = mp.iv
        ns = {n: getattr(iv, n) for n in ("sin", "cos", "tan", "exp", "log", "sqrt") if hasattr(iv, n)}
        ns.update({"Abs": abs, "pi": iv.pi, "e": iv.e, "mpf": iv.mpf})   # constants must be intervals too          # (mpmath intervals have no atan/sinh: such terms are unsupported)
        f_iv = sp.lambdify(x, e, modules=[ns, "mpmath"])
        f_pt = sp.lambdify(x, e, modules="mpmath")
        c = mp.mpf(str(c)) if isinstance(c, str) else mp.mpf(c)
        lo, hi = mp.mpf(lo), mp.mpf(hi)

        def upper(a, b):
            r = f_iv(iv.mpf([a, b]))
            return max(abs(r.a), abs(r.b)) if hasattr(r, "a") else abs(r)

        U = upper(lo, hi)
        if U <= c:
            return self._done(Verdict("REFUTED", f"proved by interval arithmetic: |f| <= {mp.nstr(U, 8)} <= {mp.nstr(c, 8)} on [{lo}, {hi}]"), t0, source)
        stack, nodes, width0 = [(lo, hi)], 0, hi - lo
        while stack and nodes < self.node_limit:
            a, b = stack.pop()
            nodes += 1
            if upper(a, b) <= c:
                continue
            m = (a + b) / 2
            fm = abs(f_pt(m))
            if fm > c:
                return self._done(Verdict("PROVED", f"witness x = {mp.nstr(m, 12)}: |f| = {mp.nstr(fm, 10)} > {mp.nstr(c, 8)}"), t0, source)
            if (b - a) < width0 * mp.mpf(10) ** -14:
                continue
            stack.extend([(a, m), (m, b)])
        if not stack:
            return self._done(Verdict("REFUTED", f"proved by branch-and-bound: |f| <= {mp.nstr(c, 8)} everywhere ({nodes} boxes)"), t0, source)
        return self._done(Verdict("UNDETERMINED", f"no witness and no proof after {nodes} boxes"), t0, source)

    # ------------------------------------------------------------------ dimensions
    def dimensions(self, equation: str, dims: Dict[str, object], source: Optional[str] = None) -> Verdict:
        t0 = time.perf_counter()
        D = {k: self._dimspec(v) for k, v in dims.items()}
        issues: List[str] = []
        constraints: List[sp.Expr] = []

        def sub(a, b):
            return {k: sp.simplify(a.get(k, 0) - b.get(k, 0)) for k in set(a) | set(b)}

        def same(a, b, ctx):
            for k, dv in sub(a, b).items():
                if dv == 0:
                    continue
                if dv.free_symbols:
                    constraints.append(dv)
                else:
                    issues.append(f"{ctx}: [{self._fmt(a)}] vs [{self._fmt(b)}]")
                    return

        def dim(e):
            if e.is_Number or e in (sp.pi, sp.E, sp.GoldenRatio):
                return {}
            if e.is_Symbol:
                return dict(D.get(str(e), {}))
            if e.is_Add:
                first = dim(e.args[0])
                for a in e.args[1:]:
                    same(first, dim(a), f"cannot add terms in {sp.sstr(e)}")
                return first
            if e.is_Mul:
                out: Dict[str, sp.Expr] = {}
                for a in e.args:
                    for k, v in dim(a).items():
                        out[k] = sp.simplify(out.get(k, 0) + v)
                return out
            if e.is_Pow:
                b, ex = e.args
                if dim(ex):
                    issues.append(f"exponent has units in {sp.sstr(e)}")
                bd = dim(b)
                return {k: sp.simplify(v * ex) for k, v in bd.items()} if bd else {}
            if e.func in (sp.sin, sp.cos, sp.tan, sp.exp, sp.log, sp.atan, sp.sinh, sp.cosh, sp.tanh):
                same({}, dim(e.args[0]), f"argument of {e.func.__name__} must be dimensionless, in {sp.sstr(e)}")
                return {}
            if e.func == sp.Abs:
                return dim(e.args[0])
            issues.append(f"unsupported term {sp.sstr(e)}")
            return {}

        lhs, rhs = equation.split("=")
        same(dim(parse(lhs)), dim(parse(rhs)), "both sides of the equation")
        if issues:
            return self._done(Verdict("ILL_FORMED", "; ".join(issues)), t0, source)
        if constraints:
            unknowns = sorted({s for c in constraints for s in c.free_symbols}, key=str)
            sol = sp.solve(constraints, unknowns, dict=True)
            if not sol:
                return self._done(Verdict("ILL_FORMED", f"no choice of {unknowns} makes the units agree"), t0, source)
            return self._done(Verdict("CONDITIONAL", f"units agree ONLY if {sol[0]}"), t0, source)
        return self._done(Verdict("CONSISTENT", "units agree"), t0, source)

    @staticmethod
    def _dimspec(v):
        if isinstance(v, dict):
            return {k: sp.nsimplify(x) for k, x in v.items()}
        out = {}
        for tok in str(v).split():
            m = re.fullmatch(r"([A-Za-z]+)(?:\^(-?[\d/]+))?", tok)
            out[m.group(1)] = sp.Rational(m.group(2)) if m.group(2) else sp.Integer(1)
        return out

    @staticmethod
    def _fmt(d):
        s = " ".join(f"{k}^{v}" for k, v in sorted(d.items()) if v != 0)
        return s or "dimensionless"

    # ------------------------------------------------------------------ coincidence meter
    @staticmethod
    def formula_bits(formula: str, n_leaf: int = 30, n_op: int = 6) -> float:
        e = parse(formula)
        leaves = [a for a in sp.preorder_traversal(e) if a.is_Atom]
        bits = 0.0
        for a in leaves:
            bits += math.log2(n_leaf)
            if a.is_Integer and abs(a) > 12:
                bits += math.log2(abs(int(a)) + 1)          # big integers cost more to specify
        return bits + sp.count_ops(e) * math.log2(n_op)

    def coincidence(self, a: float, b: float, formula: str = "", rel_unc: float = 0.0,
                    search_bits: float = 8.6, threshold: float = 10.0, source: Optional[str] = None) -> Verdict:
        """Is 'a is close to b' evidence of a real relation?  net bits = precision - formula - search."""
        t0 = time.perf_counter()
        rel = max(abs(a - b) / max(abs(a), abs(b)), rel_unc)
        prec = math.log2(1 / (2 * rel)) if rel > 0 else 64.0
        fb = self.formula_bits(formula) if formula else 0.0
        net = prec - fb - search_bits
        txt = f"match to {rel:.2e} = {prec:.1f} bits; formula costs {fb:.1f} bits; search freedom {search_bits:.1f} bits; net {net:+.1f} bits"
        return self._done(Verdict("SIGNIFICANT" if net >= threshold else "COINCIDENCE", txt), t0, source)


# ----------------------------------------------------------------------------- tests
def run_tests() -> None:
    m = NKPMath()
    assert m.identity("sin(x)**2 + cos(x)**2", "1").status == "PROVED"
    r = m.identity("sin(x)", "x - x**3/6")
    assert r.status == "REFUTED" and "counterexample" in r.detail
    assert m.identity("x", "x + 10**(-20)*x**2").status == "REFUTED"                    # a 1e-20 near-identity
    assert m.identity("3*0.3333", "1").status == "REFUTED"                               # 0.9999, exact decimal
    assert m.identity("3*Rational(1,3)", "1").status == "PROVED"
    assert m.identity("2*cos(pi/5)", "phi").status in ("PROVED", "SUPPORTED")
    assert m.identity("1 - 3*(10**4 - 1)/(3*10**4)", "10**(-4)").status == "PROVED"     # the 'flaw' F_n = 10^-n
    assert m.value("pi", "3.14159").status == "VERIFIED" and m.value("pi", "3.14160").status == "REFUTED"
    assert m.value("2*pi/phi**2", "2.3999632297").status == "VERIFIED"
    assert m.value("3**9", "19683").status == "VERIFIED"
    # the 'balanced gate' claim: potential exceeds 1/3 somewhere on [0, 10]
    g = m.exceeds("sin(x*pi)*phi**(x/10)/(pi*phi)", "x", 0, 10, "0.3333333333333333")
    assert g.status == "REFUTED" and "interval" in g.detail, g
    # a narrow peak that a coarse grid would miss
    p = m.exceeds("2*exp(-((x-3.14159)/0.001)**2)", "x", 0, 10, "1.9")
    assert p.status == "PROVED", p
    assert m.exceeds("2*exp(-((x-3.14159)/0.001)**2)", "x", 0, 10, "2.01").status == "REFUTED"
    base = {"m": "M", "a": "L T^-2", "v": "L T^-1", "d": "L", "t": "T", "F": "M L T^-2", "En": "M L^2 T^-2"}
    assert m.dimensions("F = m*a", base).status == "CONSISTENT"
    assert m.dimensions("En = m*v**2/2", base).status == "CONSISTENT"
    bad = m.dimensions("En = m*v", base)
    assert bad.status == "ILL_FORMED", bad
    assert m.dimensions("En = m*v**2 + m*v", base).status == "ILL_FORMED"
    assert m.dimensions("En = m*sin(d)", base).status == "ILL_FORMED"                    # sin of a length
    # Copilot's 'single equation': consistent with GR only if b*s = 0
    gr = {"Gmn": "L^-2", "G": "L^3 M^-1 T^-2", "c": "L T^-1", "Tmn": "M L^-1 T^-2", "X": "M L^-1 T^-2"}
    assert m.dimensions("Gmn = 8*pi*G/c**4*Tmn", gr).status == "CONSISTENT"
    cond = m.dimensions("Gmn = 8*pi*G/c**4*(I*sqrt(X))**(1+b)*Tmn/sqrt(X)", gr)
    assert cond.status == "CONDITIONAL" and "b: 0" in cond.detail, cond
    # coincidence meter: golden angle (deg) vs 1/alpha is a coincidence; a 1e-14 match to a simple formula is not
    ga = 360 * (1 - 1 / ((1 + 5 ** 0.5) / 2))
    assert m.coincidence(ga, 137.035999084, "360*(1-1/phi)").status == "COINCIDENCE"
    assert m.coincidence(3.141592653589793, 3.1415926535897936, "pi").status == "SIGNIFICANT"
    # ledger
    m2 = NKPMath()
    m2.identity("x", "x+1", source="chatA"); m2.identity("x", "x", source="chatA"); m2.identity("x", "x+1", source="chatB")
    assert m2.ledger.reliability("chatA") > m2.ledger.reliability("chatB")
    print("all 20 checks passed")


if __name__ == "__main__":
    run_tests() if "--test" in sys.argv else print(__doc__)
