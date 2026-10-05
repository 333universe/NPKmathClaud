"""
nkp_realtest.py - pre-registered real-claims test for NKP-Math.  One file; needs nkp_math.py.

The point of this test is that the labels are fixed BEFORE the engine sees the claims.  The order is enforced:

  1. write claims.txt            one claim per line (format below), each with a label and where it came from
  2. python nkp_realtest.py check  claims.txt     syntax check only; runs nothing
  3. python nkp_realtest.py freeze claims.txt     locks claims + criteria with a fingerprint (sha256)
  4. python nkp_realtest.py run    claims.txt     refuses unless frozen and unchanged; scores once
  5. python nkp_realtest.py audit  claims.txt     lists every disagreement for review (no engine changes yet)
     python nkp_realtest.py --test                self-checks; prints "all N checks passed" (empty = failure)
     add  --ledger nkp_claims.db  to `run` to also store the claims in the claims ledger

CLAIM FILE FORMAT (plain text, pipes between fields; blank lines and lines starting with # are ignored)

  id | label | kind | source | arg1 | arg2 | ...   ## original wording of the claim

  label  true | false | conditional      what an INDEPENDENT calculation or reference says (not this engine)
  kind and args:
    identity    | lhs | rhs [| {"x":[0.1,3]}]            optional domain as JSON
    value       | expr | claimed-decimal-string
    exceeds     | expr | var | lo | hi | c                the claim is  max |expr| > c  on [lo, hi]
    dimensions  | equation | {"F":"M L T^-2","m":"M"}    dims as JSON
    coincidence | a | b | formula                          label false = "the match is NOT meaningful"
  Ids starting with EX are examples and are refused at freeze time.

PRE-REGISTERED CRITERIA are the text in CRITERIA below; they are part of the fingerprint, so changing them
after freezing makes `run` refuse.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from nkp_math import ACCEPT, REJECT, NKPMath  # noqa: E402

CRITERIA = """PRE-REGISTERED CRITERIA (fixed before any claim is run)
SIZE   at least 50 claims, of which at least 15 are labelled false or conditional; otherwise the result is INCONCLUSIVE
R1     safety: ZERO false accepts (engine accepts a claim labelled false or conditional)
R2     agreement: of claims given a decided verdict (accept / reject / conditional), at least 90% match the label
R3     at most 5% of claims labelled true are rejected (false rejects)
R4     honesty: NOT_CHECKABLE (unparseable or unsupported) and UNDETERMINED are never counted as accepts;
       they are reported as coverage and not scored
SET    this set is run once.  Any later run of the same set is reported as RERUN and is no longer a pre-registered test.
       Fixes made after seeing results are judged on a NEW set, never on this one.
"""
MIN_N, MIN_NEG = 50, 15
LABELS = {"true", "false", "conditional"}
NARGS = {"identity": (2, 3), "value": (2, 2), "exceeds": (5, 5), "dimensions": (2, 2), "coincidence": (3, 3)}
ARGNAMES = {"identity": ["lhs", "rhs", "domain"], "value": ["expr", "claimed"],
            "exceeds": ["expr", "var", "lo", "hi", "c"], "dimensions": ["equation", "dims"],
            "coincidence": ["a", "b", "formula"]}


# ------------------------------------------------------------------ parsing
def parse_claims(text: str):
    rows = []
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        body, _, original = line.partition(" ## ")
        f = [p.strip() for p in body.split("|")]
        if len(f) < 5:
            raise ValueError(f"line {no}: need  id | label | kind | source | args...")
        cid, label, kind, source, args = f[0], f[1].lower(), f[2].lower(), f[3], f[4:]
        if label not in LABELS:
            raise ValueError(f"line {no}: label must be true, false or conditional (got {label!r})")
        if kind not in NARGS:
            raise ValueError(f"line {no}: kind must be one of {sorted(NARGS)} (got {kind!r})")
        lo, hi = NARGS[kind]
        if not lo <= len(args) <= hi:
            raise ValueError(f"line {no}: {kind} takes {lo}..{hi} arguments, got {len(args)}")
        kw = dict(zip(ARGNAMES[kind], args))
        try:
            if kind == "identity" and "domain" in kw:
                kw["domain"] = {k: tuple(v) for k, v in json.loads(kw["domain"]).items()}
            if kind == "dimensions":
                kw["dims"] = json.loads(kw["dims"])
            if kind == "coincidence":
                kw["a"], kw["b"] = float(kw["a"]), float(kw["b"])
            if kind == "exceeds":
                kw["lo"], kw["hi"] = float(kw["lo"]), float(kw["hi"])
        except Exception as e:
            raise ValueError(f"line {no}: could not read an argument ({type(e).__name__}: {e})")
        rows.append(dict(id=cid, label=label, kind=kind, source=source, kw=kw, original=original.strip(), line=no))
    ids = [r["id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate claim ids: " + ", ".join(sorted({i for i in ids if ids.count(i) > 1})))
    return rows


def fingerprint(text: str, criteria: str = CRITERIA) -> str:
    return hashlib.sha256((criteria + "\n=====\n" + text).encode("utf-8")).hexdigest()


def _frozen_path(p): return p + ".frozen"
def _log_path(p): return os.path.join(os.path.dirname(os.path.abspath(p)), "realtest_runs.log")


# ------------------------------------------------------------------ scoring
def engine_verdict(eng: NKPMath, row):
    """-> (class, status, detail).  class: accept | reject | conditional | undetermined | not_checkable.  Never guesses."""
    try:
        v = getattr(eng, row["kind"])(**row["kw"], source=row["source"])
    except Exception as e:
        return "not_checkable", "NOT_CHECKABLE", f"{type(e).__name__}: {e}"[:120]
    if v.status in ACCEPT:
        return "accept", v.status, v.detail
    if v.status in REJECT:
        return "reject", v.status, v.detail
    if v.status == "CONDITIONAL":
        return "conditional", v.status, v.detail
    return "undetermined", v.status, v.detail


WANT = {"true": "accept", "false": "reject", "conditional": "conditional"}


def evaluate(rows, results, criteria_ok=True) -> dict:
    n = len(rows)
    neg = sum(r["label"] != "true" for r in rows)
    fa = [r["id"] for r, x in zip(rows, results) if r["label"] != "true" and x[0] == "accept"]
    t_rows = [(r, x) for r, x in zip(rows, results) if r["label"] == "true"]
    fr = [r["id"] for r, x in t_rows if x[0] == "reject"]
    decided = [(r, x) for r, x in zip(rows, results) if x[0] in ("accept", "reject", "conditional")]
    agree = [r["id"] for r, x in decided if x[0] == WANT[r["label"]]]
    disagree = [r["id"] for r, x in decided if x[0] != WANT[r["label"]]]
    out = dict(n=n, neg=neg, decided=len(decided), coverage=len(decided) / n if n else 0.0,
               not_checkable=sum(x[0] == "not_checkable" for x in results),
               undetermined=sum(x[0] == "undetermined" for x in results),
               false_accepts=fa, false_rejects=fr, disagree=disagree,
               agreement=(len(agree) / len(decided)) if decided else 0.0,
               false_reject_rate=(len(fr) / len(t_rows)) if t_rows else 0.0)
    out["size_ok"] = n >= MIN_N and neg >= MIN_NEG
    out["R1"] = not fa
    out["R2"] = out["agreement"] >= 0.90 and len(decided) > 0
    out["R3"] = out["false_reject_rate"] <= 0.05
    out["verdict"] = ("INCONCLUSIVE (too few claims or too few false/conditional claims)" if not out["size_ok"]
                      else "PASS" if out["R1"] and out["R2"] and out["R3"] else "FAIL")
    return out


def breakdown(rows, results) -> dict:
    """Per-batch report, using the text after the last ':' in each claim's source (e.g. ai-A:b1 -> b1)."""
    groups = {}
    for r, x in zip(rows, results):
        tag = r["source"].rsplit(":", 1)[-1] if ":" in r["source"] else "all"
        groups.setdefault(tag, []).append((r, x))
    out = {}
    for tag, items in groups.items():
        dec = [(r, x) for r, x in items if x[0] in ("accept", "reject", "conditional")]
        out[tag] = dict(n=len(items), decided=len(dec),
                        false_accepts=sum(1 for r, x in items if r["label"] != "true" and x[0] == "accept"),
                        false_rejects=sum(1 for r, x in items if r["label"] == "true" and x[0] == "reject"),
                        agree=sum(1 for r, x in dec if x[0] == WANT[r["label"]]))
    return out


# ------------------------------------------------------------------ commands
def read(path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def cmd_check(path):
    rows = parse_claims(read(path))
    ex = [r["id"] for r in rows if r["id"].upper().startswith("EX")]
    from collections import Counter
    c = Counter((r["kind"], r["label"]) for r in rows)
    print(f"{len(rows)} claims read.  by kind/label: " + ", ".join(f"{k[0]}:{k[1]}={v}" for k, v in sorted(c.items())))
    neg = sum(r["label"] != "true" for r in rows)
    print(f"false/conditional claims: {neg}   (need >= {MIN_NEG}; total need >= {MIN_N})")
    if ex:
        print(f"NOTE: example ids still present {ex}: delete them before freezing")
    return 0


def cmd_freeze(path):
    text = read(path)
    rows = parse_claims(text)
    ex = [r["id"] for r in rows if r["id"].upper().startswith("EX")]
    if ex:
        print(f"REFUSED: example claims are still in the file {ex}.  Delete them, then freeze.")
        return 1
    fp = fingerprint(text)
    with open(_frozen_path(path), "w") as f:
        json.dump(dict(sha256=fp, n=len(rows), frozen=time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())), f)
    print(f"FROZEN: {len(rows)} claims.  fingerprint {fp[:16]}...  Labels and criteria can no longer change without detection.")
    print(CRITERIA)
    return 0


def cmd_run(path, ledger_path=None):
    if not os.path.exists(_frozen_path(path)):
        print("REFUSED: the claim file is not frozen.  Run `freeze` first (that is what makes this a pre-registered test).")
        return 1
    text = read(path)
    fz = json.load(open(_frozen_path(path)))
    fp = fingerprint(text)
    if fp != fz["sha256"]:
        print("REFUSED: the claim file or the criteria changed after freezing.  Results would not be pre-registered.")
        return 1
    rows = parse_claims(text)
    log = _log_path(path)
    seen = os.path.exists(log) and any(json.loads(l).get("sha256") == fp for l in open(log) if l.strip())
    eng = NKPMath(seed=0)
    results = [engine_verdict(eng, r) for r in rows]
    ev = evaluate(rows, results)
    print(f"{'id':<8}{'label':<12}{'engine':<14}{'ok':<5}claim")
    for r, x in zip(rows, results):
        ok = "ok" if x[0] == WANT[r["label"]] else "--" if x[0] in ("undetermined", "not_checkable") else "BAD"
        name = r["original"] or " | ".join(str(v) for v in r["kw"].values())
        print(f"{r['id']:<8}{r['label']:<12}{x[0]:<14}{ok:<5}{name[:60]}")
    print(f"\n{ev['n']} claims; {ev['decided']} decided ({ev['coverage']:.0%} coverage); "
          f"{ev['undetermined']} undetermined, {ev['not_checkable']} not checkable (reported, not scored)")
    print(f"R1 false accepts: {len(ev['false_accepts'])} {ev['false_accepts'] or ''} -> {'PASS' if ev['R1'] else 'FAIL'}")
    print(f"R2 agreement on decided claims: {ev['agreement']:.1%} (need >= 90%) -> {'PASS' if ev['R2'] else 'FAIL'}")
    print(f"R3 false-reject rate on true claims: {ev['false_reject_rate']:.1%} (need <= 5%) -> {'PASS' if ev['R3'] else 'FAIL'}")
    print("\nby batch (the text after ':' in each source):")
    for tag, b in sorted(breakdown(rows, results).items()):
        pct = f"{b['agree'] / b['decided']:.0%}" if b["decided"] else "n/a"
        print(f"  {tag:<6} {b['n']:>3} claims, {b['decided']:>3} decided, agreement {pct:>4}, false accepts {b['false_accepts']}, false rejects {b['false_rejects']}")
    print(f"\nRESULT: {ev['verdict']}" + ("   [RERUN: this set was run before, so this is NOT a pre-registered result]" if seen else ""))
    if ev["disagree"] or ev["false_accepts"]:
        print("Disagreements are NOT automatically engine errors: the label may be wrong.  Run `audit`, check labels first.")
    with open(log, "a") as f:
        f.write(json.dumps(dict(sha256=fp, time=time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), verdict=ev["verdict"],
                                n=ev["n"], false_accepts=ev["false_accepts"], agreement=round(ev["agreement"], 4))) + "\n")
    out_csv = path + ".results.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["id", "label", "kind", "source", "engine_class", "status", "detail", "original"])
        for r, x in zip(rows, results):
            w.writerow([r["id"], r["label"], r["kind"], r["source"], x[0], x[1], x[2], r["original"]])
    print(f"results written to {out_csv}")
    if ledger_path:
        from nkp_ledger import ClaimLedger
        L = ClaimLedger(ledger_path)
        stored = 0
        for r, x in zip(rows, results):
            if x[0] != "not_checkable":
                L.check(r["kind"], source=r["source"], **r["kw"]); stored += 1
        print(f"{stored} claims stored in the ledger {ledger_path}")
    return 0


def cmd_audit(path):
    rows = parse_claims(read(path))
    eng = NKPMath(seed=0)
    n = 0
    for r in rows:
        c, s, d = engine_verdict(eng, r)
        if c != WANT[r["label"]]:
            n += 1
            print(f"{r['id']}: label {r['label']}, engine {c} ({s})\n    claim:  {r['original'] or r['kw']}\n    engine: {d[:140]}\n"
                  f"    source: {r['source']}")
    print(f"\n{n} claim(s) to review.  Check the LABEL with an independent calculation first.  "
          f"Do not change the engine on this set; use a new set.")
    return 0


# ------------------------------------------------------------------ tests
def run_tests() -> None:
    n_ok = 0

    def check(cond, msg):
        nonlocal n_ok
        assert cond, msg
        n_ok += 1
    good = ("# comment\n\n"
            "c1 | true | identity | src:a | sin(x)**2+cos(x)**2 | 1 ## sin^2+cos^2=1\n"
            "c2 | false | identity | src:a | (x+1)**2 | x**2+1\n"
            "c3 | conditional | identity | src:b | sqrt(x**2) | x\n"
            "c4 | true | value | src:c | pi | 3.14159\n"
            "c5 | false | value | src:c | pi | 3.14160\n"
            "c6 | true | dimensions | src:d | F = m*a | {\"F\":\"M L T^-2\",\"m\":\"M\",\"a\":\"L T^-2\"}\n"
            "c7 | false | exceeds | src:e | sin(x)*exp(-x) | x | 0 | 10 | 0.35\n"
            "c8 | false | coincidence | src:f | 19.99909997 | 20.0 | exp(pi)-pi\n"
            "c9 | true | identity | src:g | sqrt(y**2) | y | {\"y\":[0.1,3]}\n")
    rows = parse_claims(good)
    check(len(rows) == 9 and rows[0]["original"] == "sin^2+cos^2=1", "claims and original wording parsed")
    check(rows[8]["kw"]["domain"] == {"y": (0.1, 3.0)}, "domain JSON becomes a tuple")
    for bad, why in [("c1 | maybe | value | s | pi | 3", "bad label"), ("c1 | true | poem | s | a", "bad kind"),
                     ("c1 | true | value | s | pi", "wrong argument count"), ("a | true | value | s | pi | 3\na | true | value | s | e | 2", "duplicate id")]:
        try:
            parse_claims(bad); check(False, f"{why} must be rejected")
        except ValueError:
            check(True, f"{why} is rejected")
    eng = NKPMath(seed=0)
    res = [engine_verdict(eng, r) for r in rows]
    got = [x[0] for x in res]
    check(got == ["accept", "reject", "conditional", "accept", "reject", "accept", "reject", "reject", "accept"], f"verdict classes {got}")
    ev = evaluate(rows, res)
    check(ev["R1"] and ev["R2"] and ev["R3"] and not ev["size_ok"] and ev["verdict"].startswith("INCONCLUSIVE"),
          "small set is INCONCLUSIVE even when everything agrees")
    wrong = [dict(r) for r in rows]; wrong[1]["label"] = "true"; wrong[1] = dict(wrong[1])
    flipped = [dict(r) for r in rows]; flipped[0]["label"] = "false"
    ev2 = evaluate(flipped, res)
    check(ev2["false_accepts"] == ["c1"] and not ev2["R1"], "an accepted claim labelled false is a false accept")
    ev3 = evaluate(wrong, res)
    check(ev3["false_rejects"] == ["c2"], "a rejected claim labelled true is a false reject")
    junk = dict(id="j1", label="true", kind="identity", source="s", kw=dict(lhs="foo(", rhs="1"), original="", line=1)
    jr = engine_verdict(eng, junk)
    check(jr[0] == "not_checkable", "unparseable claim is NOT_CHECKABLE, never guessed")
    ev4 = evaluate([junk], [jr])
    check(ev4["decided"] == 0 and not ev4["R2"], "not-checkable claims are not scored as accepts")
    check(fingerprint("a") != fingerprint("b") and fingerprint("a") != fingerprint("a", criteria="other"), "fingerprint covers claims and criteria")
    d = tempfile.mkdtemp(); p = os.path.join(d, "claims.txt")
    open(p, "w").write(good)
    check(cmd_run(p) == 1, "run refuses before freeze")
    ex = os.path.join(d, "ex.txt"); open(ex, "w").write("EX1 | true | value | s | pi | 3.14")
    check(cmd_freeze(ex) == 1, "freeze refuses example ids")
    check(cmd_freeze(p) == 0, "freeze works")
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r1 = cmd_run(p)
    check(r1 == 0 and "RESULT: INCONCLUSIVE" in buf.getvalue() and "RERUN" not in buf.getvalue(), "first run is not flagged")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_run(p)
    check("RERUN" in buf.getvalue(), "second run of the same set is flagged RERUN")
    check(os.path.exists(p + ".results.csv"), "results csv written")
    open(p, "a").write("c10 | true | value | s | e | 2.71\n")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r3 = cmd_run(p)
    check(r3 == 1 and "REFUSED" in buf.getvalue(), "editing the file after freezing makes run refuse")
    bd = breakdown([dict(r, source=r["source"] + (":b1" if i < 5 else ":b2")) for i, r in enumerate(rows)], res)
    check(set(bd) == {"b1", "b2"} and bd["b1"]["n"] == 5 and bd["b2"]["n"] == 4 and bd["b1"]["false_accepts"] == 0,
          "breakdown groups claims by the batch tag in the source")
    print(f"all {n_ok} checks passed")


def main(argv) -> int:
    if "--test" in argv:
        run_tests(); return 0
    if len(argv) < 2 or argv[0] not in ("check", "freeze", "run", "audit"):
        print(__doc__); return 0
    cmd, path = argv[0], argv[1]
    try:
        if cmd == "check": return cmd_check(path)
        if cmd == "freeze": return cmd_freeze(path)
        if cmd == "audit": return cmd_audit(path)
        led = argv[argv.index("--ledger") + 1] if "--ledger" in argv else None
        return cmd_run(path, led)
    except (ValueError, FileNotFoundError) as e:
        print(f"ERROR: {e}"); return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
