"""
nkp_ledger.py - the NKP claims ledger.  One file, Python standard library (sqlite3) + your nkp_math.py.

Every claim you check is stored once, with its verdict, its evidence, who made it, and what it depends on.

    python nkp_ledger.py --test                          self-checks; prints "all N checks passed" (empty = failure)
    python nkp_ledger.py seed-real                       check and store the 17 real claims from nkp_math_bench.py
    python nkp_ledger.py add identity "L" "R" [--source S] [--depends 1,2] [--domain '{"x":[0.1,3]}']
    python nkp_ledger.py add value "pi" "3.14159"        |  add dimensions "F = m*a" '{"F":"M L T^-2","m":"M","a":"L T^-2"}'
    python nkp_ledger.py add exceeds EXPR VAR LO HI C    |  add coincidence A B "formula"
    python nkp_ledger.py link CHILD PARENT               "CHILD is built on PARENT"
    python nkp_ledger.py list [STATUS]                   all claims, or only one verdict status
    python nkp_ledger.py search TEXT                     find claims by text (is this already known?)
    python nkp_ledger.py risk                            claims built on refuted (AT_RISK) or unverified (SHAKY) claims
    python nkp_ledger.py sources                         source track record
    python nkp_ledger.py recheck                         re-run every claim with the current engine, report any change
    python nkp_ledger.py stats | export claims.csv
    add  --db FILE   to any command to use a different database (default nkp_claims.db)

What "new" means here:  a claim is NEW only if its canonical form is not already stored.  Same claim written
differently (sides swapped, terms reordered) is a DUPLICATE.  A different claim about the same numeric function
is flagged RELATED.  Variable renames are not detected.  A stored claim is a verified statement of math, not a
fact about the world: the ledger records what computation found, with the evidence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
import sys
import time
from collections import defaultdict

import sympy as sp

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from nkp_math import ACCEPT, REJECT, NKPMath, parse  # noqa: E402

ARGS = {                                   # positional order of each claim kind (matches the engine)
    "identity": ["lhs", "rhs", "domain"],
    "value": ["expr", "claimed"],
    "exceeds": ["expr", "var", "lo", "hi", "c"],
    "dimensions": ["equation", "dims"],
    "coincidence": ["a", "b", "formula"],
}


def _engine_version() -> str:
    try:
        with open(os.path.join(HERE, "nkp_math.py"), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:10]
    except OSError:
        return "unknown"


def status_class(s: str) -> str:
    return "true" if s in ACCEPT else "false" if s in REJECT else "open"


# ------------------------------------------------------------------ canonical forms
def _fp(text: str):
    """Numeric fingerprint of an expression at fixed rational points (None if it cannot be evaluated)."""
    try:
        e = parse(text)
        syms = sorted(e.free_symbols, key=str)
        pts = {s: sp.Rational(7 + 6 * i, 10) for i, s in enumerate(syms)}
        return str(sp.N(e.subs(pts), 30))[:24] + "@" + ",".join(map(str, syms))
    except Exception:
        return None


def canonical(kind: str, kw: dict):
    """(canon, fingerprint, display).  canon decides DUPLICATE; fingerprint decides RELATED."""
    try:
        if kind == "identity":
            a, b = sorted([str(parse(kw["lhs"])), str(parse(kw["rhs"]))])
            dom = json.dumps(kw.get("domain"), sort_keys=True)
            fa, fb = _fp(kw["lhs"]), _fp(kw["rhs"])
            fp = None if None in (fa, fb) else "identity|" + "|".join(sorted([fa, fb])) + "|" + dom
            return f"identity|{a}|{b}|{dom}", fp, f"{kw['lhs']}  =  {kw['rhs']}" + (f"   [domain {dom}]" if kw.get("domain") else "")
        if kind == "value":
            c = f"value|{parse(kw['expr'])}|{kw['claimed']}"
            f = _fp(kw["expr"])
            return c, (None if f is None else f"value|{f}|{kw['claimed']}"), f"{kw['expr']}  =  {kw['claimed']}"
        if kind == "exceeds":
            c = f"exceeds|{parse(kw['expr'])}|{kw['var']}|{kw['lo']}|{kw['hi']}|{kw['c']}"
            f = _fp(kw["expr"])
            return c, (None if f is None else f"exceeds|{f}|{kw['var']}|{kw['lo']}|{kw['hi']}|{kw['c']}"), \
                f"|{kw['expr']}| > {kw['c']} on [{kw['lo']}, {kw['hi']}]"
        if kind == "dimensions":
            eq = kw["equation"]
            sides = sorted(str(parse(s)) for s in eq.split("=")) if "=" in eq else [eq]
            c = f"dimensions|{'=='.join(sides)}|{json.dumps(kw['dims'], sort_keys=True, default=str)}"
            return c, c, eq
        if kind == "coincidence":
            c = f"coincidence|{kw['a']}|{kw['b']}|{kw.get('formula', '')}"
            return c, c, f"{kw['a']} ~ {kw['b']}  via  {kw.get('formula', '') or '(no formula)'}"
    except Exception:
        pass
    raw = json.dumps(kw, sort_keys=True, default=str)
    return f"{kind}|RAW|{raw}", None, f"{kind}: {raw[:80]}"


def _revive(kind: str, kw: dict) -> dict:
    kw = dict(kw)
    if kind == "identity" and kw.get("domain"):
        kw["domain"] = {k: tuple(v) for k, v in kw["domain"].items()}
    return kw


# ------------------------------------------------------------------ the ledger
class ClaimLedger:
    def __init__(self, path: str = "nkp_claims.db", engine: NKPMath | None = None):
        self.path = path
        self.eng = engine or NKPMath(seed=0)
        self.ver = _engine_version()
        self.db = sqlite3.connect(path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS claims(
                id INTEGER PRIMARY KEY, kind TEXT NOT NULL, args TEXT NOT NULL, display TEXT NOT NULL,
                canon TEXT NOT NULL UNIQUE, fp TEXT, created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS verdicts(
                id INTEGER PRIMARY KEY, claim_id INTEGER NOT NULL REFERENCES claims(id), status TEXT NOT NULL,
                detail TEXT, source TEXT, engine TEXT, ts TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS deps(
                child INTEGER NOT NULL, parent INTEGER NOT NULL, UNIQUE(child, parent));
            CREATE INDEX IF NOT EXISTS ix_fp ON claims(fp);
            CREATE INDEX IF NOT EXISTS ix_v ON verdicts(claim_id);
        """)
        self.db.commit()

    # ---- internals
    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

    def _latest(self, cid: int):
        return self.db.execute("SELECT status, detail FROM verdicts WHERE claim_id=? ORDER BY id DESC LIMIT 1", (cid,)).fetchone()

    def _add_verdict(self, cid, status, detail, source):
        self.db.execute("INSERT INTO verdicts(claim_id,status,detail,source,engine,ts) VALUES(?,?,?,?,?,?)",
                        (cid, status, detail, source, self.ver, self._now()))

    def _link_many(self, child: int, parents):
        for p in parents:
            if p != child and self.db.execute("SELECT 1 FROM claims WHERE id=?", (p,)).fetchone():
                self.db.execute("INSERT OR IGNORE INTO deps(child,parent) VALUES(?,?)", (child, p))

    def _result(self, cid, novel, duplicate, related):
        s, d = self._latest(cid)
        r = self.risk().get(cid)
        return dict(id=cid, novel=novel, duplicate_of=cid if duplicate else None, related=related,
                    status=s, accepted=s in ACCEPT, detail=d, risk=r[0] if r else "")

    # ---- main entry
    def check(self, kind: str, source: str | None = None, depends_on=(), **kw) -> dict:
        if kind not in ARGS:
            raise ValueError(f"unknown claim kind {kind!r}; use one of {sorted(ARGS)}")
        canon, fp, display = canonical(kind, kw)
        row = self.db.execute("SELECT id FROM claims WHERE canon=?", (canon,)).fetchone()
        if row:                                                     # already known: no re-computation
            cid = row[0]
            if source is not None and not self.db.execute(
                    "SELECT 1 FROM verdicts WHERE claim_id=? AND source=?", (cid, source)).fetchone():
                s, d = self._latest(cid)
                self._add_verdict(cid, s, d, source)               # a new source asserted a known claim
            self._link_many(cid, depends_on)
            self.db.commit()
            return self._result(cid, novel=False, duplicate=True, related=[])
        v = getattr(self.eng, kind)(**kw, source=source)
        cur = self.db.execute("INSERT INTO claims(kind,args,display,canon,fp,created) VALUES(?,?,?,?,?,?)",
                              (kind, json.dumps(kw, default=str), display, canon, fp, self._now()))
        cid = cur.lastrowid
        self._add_verdict(cid, v.status, v.detail, source)
        self._link_many(cid, depends_on)
        related = [r[0] for r in self.db.execute("SELECT id FROM claims WHERE fp=? AND id!=?", (fp, cid))] if fp else []
        self.db.commit()
        return self._result(cid, novel=True, duplicate=False, related=related)

    def check_args(self, kind: str, args, source=None, depends_on=()):
        """Same, with positional arguments in the engine's order."""
        return self.check(kind, source=source, depends_on=depends_on, **dict(zip(ARGS[kind], args)))

    def link(self, child: int, parent: int) -> None:
        self._link_many(child, [parent]); self.db.commit()

    # ---- re-running
    def recheck(self, cid: int):
        kind, args = self.db.execute("SELECT kind,args FROM claims WHERE id=?", (cid,)).fetchone()
        old = self._latest(cid)[0]
        v = getattr(self.eng, kind)(**_revive(kind, json.loads(args)))
        self._add_verdict(cid, v.status, v.detail, None)           # source None: not counted in any source record
        self.db.commit()
        return v.status != old, old, v.status

    def recheck_all(self):
        out = []
        for (cid,) in self.db.execute("SELECT id FROM claims ORDER BY id").fetchall():
            changed, old, new = self.recheck(cid)
            if changed:
                out.append((cid, old, new))
        return out

    # ---- dependency risk
    def risk(self) -> dict:
        latest = {cid: self._latest(cid)[0] for (cid,) in self.db.execute("SELECT id FROM claims")}
        parents = defaultdict(list)
        for c, p in self.db.execute("SELECT child,parent FROM deps"):
            parents[c].append(p)
        out = {}
        for c in latest:
            seen, stack, bad, opn = set(), list(parents[c]), set(), set()
            while stack:
                p = stack.pop()
                if p in seen or p == c:
                    continue
                seen.add(p)
                cls = status_class(latest[p])
                if cls == "false":
                    bad.add(p)
                elif cls == "open":
                    opn.add(p)
                stack.extend(parents[p])
            if bad:
                out[c] = ("AT_RISK", sorted(bad), sorted(opn))
            elif opn:
                out[c] = ("SHAKY", [], sorted(opn))
        return out

    # ---- views
    def sources(self):
        k = defaultdict(lambda: {"true": 0, "false": 0, "open": 0})
        for s, st in self.db.execute("SELECT source,status FROM verdicts WHERE source IS NOT NULL"):
            k[s][status_class(st)] += 1
        rows = [(s, c["true"], c["false"], c["open"], (c["true"] + 1) / (c["true"] + c["false"] + 2)) for s, c in k.items()]
        return sorted(rows, key=lambda r: (-r[4], r[0]))

    def rows(self, status: str | None = None):
        out = []
        for cid, kind, display, created in self.db.execute("SELECT id,kind,display,created FROM claims ORDER BY id").fetchall():
            s, d = self._latest(cid)
            if status is None or s == status.upper():
                out.append((cid, kind, display, s, d, created))
        return out

    def search(self, text: str):
        like = f"%{text}%"
        ids = {r[0] for r in self.db.execute("SELECT id FROM claims WHERE display LIKE ? OR canon LIKE ?", (like, like))}
        return [r for r in self.rows() if r[0] in ids]

    def stats(self) -> dict:
        n = self.db.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
        by = defaultdict(int)
        for r in self.rows():
            by[r[3]] += 1
        return dict(claims=n, by_status=dict(by), deps=self.db.execute("SELECT COUNT(*) FROM deps").fetchone()[0],
                    at_risk=sum(1 for v in self.risk().values() if v[0] == "AT_RISK"),
                    shaky=sum(1 for v in self.risk().values() if v[0] == "SHAKY"))

    def export_csv(self, path: str) -> int:
        risk = self.risk()
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "kind", "claim", "status", "detail", "sources", "risk", "created"])
            for cid, kind, display, s, d, created in self.rows():
                srcs = ";".join(sorted({r[0] for r in self.db.execute(
                    "SELECT source FROM verdicts WHERE claim_id=? AND source IS NOT NULL", (cid,))}))
                w.writerow([cid, kind, display, s, d, srcs, risk.get(cid, ("",))[0], created])
        return len(self.rows())


# ------------------------------------------------------------------ seeding with the real claims
def seed_real(led: ClaimLedger) -> list:
    from nkp_math_bench import REAL
    return [(src, led.check_args(kind, args, source=src)) for kind, args, _exp, src in REAL]


# ------------------------------------------------------------------ tests
def run_tests() -> None:
    n_ok = 0

    def check(cond, msg):
        nonlocal n_ok
        assert cond, msg
        n_ok += 1
    L = ClaimLedger(":memory:")
    a = L.check("identity", lhs="sin(x)**2+cos(x)**2", rhs="1", source="doc:A")
    check(a["novel"] and a["status"] == "PROVED" and a["accepted"], "true identity is stored as PROVED and novel")
    b = L.check("identity", lhs="1", rhs="cos(x)**2+sin(x)**2", source="doc:A")
    check(b["duplicate_of"] == a["id"] and not b["novel"], "sides swapped and terms reordered = DUPLICATE")
    check(L.stats()["claims"] == 1, "duplicate adds no claim")
    c = L.check("identity", lhs="cos(2*x)", rhs="1-2*sin(x)**2", source="doc:B")
    d = L.check("identity", lhs="cos(2*x)", rhs="2*cos(x)**2-1", source="doc:B")
    check(c["novel"] and d["novel"] and c["id"] in d["related"], "different claim about the same function is RELATED, not a duplicate")
    f = L.check("identity", lhs="(x+1)**2", rhs="x**2+3*x+1", source="doc:C")
    check(f["status"] == "REFUTED" and not f["accepted"], "false identity is REFUTED")
    g = L.check("identity", lhs="sqrt(x**2)", rhs="x", source="doc:C")
    check(g["status"] == "CONDITIONAL", "domain trap is CONDITIONAL")
    h = L.check("identity", lhs="x**2-4", rhs="(x-2)*(x+2)", source="doc:C", depends_on=[f["id"]])
    check(h["risk"] == "AT_RISK", "claim built on a refuted claim is AT_RISK")
    i = L.check("identity", lhs="x**3-8", rhs="(x-2)*(x**2+2*x+4)", source="doc:C", depends_on=[h["id"]])
    check(i["risk"] == "AT_RISK", "risk travels through a chain")
    j = L.check("identity", lhs="x*(1/x)", rhs="1", source="doc:D", depends_on=[g["id"]])
    check(j["risk"] == "SHAKY", "claim built on an unverified (conditional) claim is SHAKY")
    L.link(a["id"], j["id"]); L.link(j["id"], a["id"])
    check(isinstance(L.risk(), dict), "dependency cycles do not hang")
    ch = L.check("identity", lhs="1", rhs="cos(x)**2+sin(x)**2", source="doc:E")
    check(ch["duplicate_of"] == a["id"] and L.stats()["claims"] == 8, "second source on a known claim adds a verdict, not a claim")
    n0 = L.db.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0]
    L.check("identity", lhs="1", rhs="cos(x)**2+sin(x)**2", source="doc:E")
    check(L.db.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0] == n0, "same source repeating a claim is not double counted")
    t = {r[0]: r for r in L.sources()}
    check(t["doc:A"][1:4] == (1, 0, 0) and abs(t["doc:A"][4] - 2 / 3) < 1e-9, "source record: 1 true, reliability 2/3")
    check(t["doc:C"][1:4] == (2, 1, 1), "source record counts true / false / open separately")
    ok = L.check("value", expr="pi", claimed="3.14159265358979323846", source="doc:V")
    check(ok["status"] in ACCEPT, "value claim to 20 decimals")
    bad = L.check("value", expr="pi", claimed="3.14159265358979323847", source="doc:V")
    check(bad["status"] == "REFUTED", "value claim with last digit wrong is REFUTED")
    dm = L.check("dimensions", equation="F = m*a", dims={"F": "M L T^-1", "m": "M", "a": "L T^-2"}, source="doc:U")
    check(dm["status"] == "ILL_FORMED", "dimension claim with wrong units is ILL_FORMED")
    rc = L.recheck(a["id"])
    check(rc[0] is False, "recheck with the same engine changes nothing")
    L.db.execute("UPDATE verdicts SET status='REFUTED' WHERE claim_id=?", (a["id"],)); L.db.commit()
    rc2 = L.recheck(a["id"])
    check(rc2[0] is True and rc2[1] == "REFUTED" and rc2[2] == "PROVED", "recheck detects a changed verdict")
    check(len(L.search("sin")) >= 2 and len(L.search("zzzz")) == 0, "search finds stored claims by text")
    try:
        L.check("poem", x=1); check(False, "unknown kind must raise")
    except ValueError:
        check(True, "unknown kind raises ValueError")
    import tempfile
    p = os.path.join(tempfile.mkdtemp(), "t.db")
    P = ClaimLedger(p); P.check("identity", lhs="x*1", rhs="x", source="s"); P.db.close()
    P2 = ClaimLedger(p)
    check(P2.stats()["claims"] == 1 and P2.rows()[0][3] == "PROVED", "the database persists on disk")
    q = os.path.join(os.path.dirname(p), "e.csv")
    check(L.export_csv(q) == L.stats()["claims"] and os.path.getsize(q) > 100, "csv export")
    R = ClaimLedger(":memory:")
    from nkp_math_bench import REAL
    res = seed_real(R)
    exp = {"accept": ACCEPT, "reject": REJECT}
    ok_all = all((r["status"] in exp["accept"]) if e == "accept" else (r["status"] in exp["reject"]) if e == "reject"
                 else (r["status"] not in ACCEPT | REJECT) for (_k, _a, e, _s), (_s2, r) in zip(REAL, res))
    check(ok_all and len(res) == len(REAL), "all 17 real claims get the expected verdict through the ledger")
    check(R.stats()["claims"] == len({r["id"] for _s, r in res}), "every real claim is stored once")
    eng = NKPMath(seed=0)
    for kind, args, _e, src in REAL:
        getattr(eng, kind)(*args, source=src)
    mine = {r[0]: round(r[4], 9) for r in R.sources()}
    theirs = {r[0]: round(r[4], 9) for r in eng.ledger.table()}
    check(mine == theirs, "source reliability matches the engine's own ledger")
    print(f"all {n_ok} checks passed")


# ------------------------------------------------------------------ command line
def _fmt(r) -> str:
    cid, kind, display, s, d, created = r
    return f"#{cid:<3} {s:<12} {kind:<11} {display[:70]}"


def _cli_kw(kind, pos, domain_json):
    names = ARGS[kind]
    if kind == "identity":
        kw = dict(zip(names, pos))
        if domain_json:
            kw["domain"] = {k: tuple(v) for k, v in json.loads(domain_json).items()}
        return kw
    vals = list(pos)
    if kind == "dimensions" and len(vals) > 1:
        vals[1] = json.loads(vals[1])
    if kind == "coincidence":
        vals[:2] = [float(v) for v in vals[:2]]
    if kind == "exceeds" and len(vals) >= 4:
        vals[2], vals[3] = float(vals[2]), float(vals[3])
    return dict(zip(names, vals))


def main(argv) -> int:
    if "--test" in argv:
        run_tests()
        return 0
    ap = argparse.ArgumentParser(description="NKP claims ledger", add_help=True)
    ap.add_argument("--db", default="nkp_claims.db")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("add"); p.add_argument("kind"); p.add_argument("pos", nargs="+")
    p.add_argument("--source"); p.add_argument("--depends", default=""); p.add_argument("--domain")
    p = sub.add_parser("link"); p.add_argument("child", type=int); p.add_argument("parent", type=int)
    p = sub.add_parser("list"); p.add_argument("status", nargs="?")
    p = sub.add_parser("search"); p.add_argument("text")
    p = sub.add_parser("export"); p.add_argument("path")
    for n in ("seed-real", "risk", "sources", "recheck", "stats"):
        sub.add_parser(n)
    a = ap.parse_args(argv)
    if not a.cmd:
        print(__doc__)
        return 0
    L = ClaimLedger(a.db)
    if a.cmd == "add":
        deps = [int(x) for x in a.depends.split(",") if x.strip()]
        r = L.check(a.kind, source=a.source, depends_on=deps, **_cli_kw(a.kind, a.pos, a.domain))
        tag = "NEW" if r["novel"] else f"DUPLICATE of #{r['duplicate_of']}"
        print(f"#{r['id']} {tag}  {r['status']}  {r['detail'][:100]}")
        if r["related"]:
            print(f"   related (same numeric function): {r['related']}")
        if r["risk"]:
            print(f"   {r['risk']}")
    elif a.cmd == "link":
        L.link(a.child, a.parent); print(f"#{a.child} now depends on #{a.parent}")
    elif a.cmd == "seed-real":
        for src, r in seed_real(L):
            print(f"#{r['id']:<3} {'NEW' if r['novel'] else 'dup':<4} {r['status']:<12} {src}")
    elif a.cmd == "list":
        for r in L.rows(a.status): print(_fmt(r))
    elif a.cmd == "search":
        rows = L.search(a.text)
        print(f"{len(rows)} match(es)" if rows else "no match: nothing like this is stored yet")
        for r in rows: print(_fmt(r))
    elif a.cmd == "risk":
        rk = L.risk()
        print(f"{len(rk)} claim(s) built on refuted or unverified claims" if rk else "no claim is built on a refuted or unverified claim")
        for c, (lvl, bad, opn) in sorted(rk.items()):
            print(f"#{c:<3} {lvl:<8} refuted parents {bad or '-'}  unverified parents {opn or '-'}")
    elif a.cmd == "sources":
        for s, t, f, o, rel in L.sources(): print(f"{s:<36}{t} / {f} / {o}  -> {rel:.2f}")
    elif a.cmd == "recheck":
        ch = L.recheck_all()
        print("no verdict changed" if not ch else "CHANGED:")
        for c, old, new in ch: print(f"#{c}: {old} -> {new}")
    elif a.cmd == "stats":
        print(json.dumps(L.stats(), indent=1))
    elif a.cmd == "export":
        print(f"{L.export_csv(a.path)} claims written to {a.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
