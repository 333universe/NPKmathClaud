"""
sieve_lab.py - audit and compare the Pi-Phi "1/3 sieve" as a token pre-filter.  One file, numpy only (no torch).

    python sieve_lab.py --audit     facts about the original sieve (share by window, period, aliasing)
    python sieve_lab.py --compare   original vs fixed vs stride vs random vs hybrid (synthetic, see caveats)
    python sieve_lab.py --test      self-checks; prints "all N checks passed" (empty output = failure)

Variants  (n = 1, 2, 3, ... token position)
  original  floor(n * 2*pi/phi^2) mod 3          (channel 0 = keep, 1 = compress, 2 = prune)
  fixed     floor(3 * frac(n / phi))             (same three channels, golden-ratio rotation in TURNS)
Helper API
  sieve_channels(n, variant)         -> int array of channels 0/1/2, length n
  sieve_select(x, variant)           -> survivors, position_ids, channels   (x: [seq, d] or [batch, seq, d])
  hybrid_keep(scores, rate, floor_share) -> bool mask: sieve coverage floor + highest-scored extra tokens
"""
from __future__ import annotations

import sys

import numpy as np

PHI = (1 + 5 ** 0.5) / 2
GOLDEN_ANGLE = 2 * np.pi / PHI ** 2          # 2.39996..., radians


# ------------------------------------------------------------------ the sieve
def sieve_channels(n: int, variant: str = "fixed", start: int = 1) -> np.ndarray:
    pos = np.arange(start, start + n, dtype=np.float64)
    if variant == "original":
        return np.floor(pos * GOLDEN_ANGLE).astype(np.int64) % 3
    if variant == "fixed":
        return np.floor(3 * ((pos / PHI) % 1.0)).astype(np.int64)
    raise ValueError(f"unknown variant {variant!r}")


def sieve_select(x: np.ndarray, variant: str = "fixed"):
    """Keep channel-0 tokens.  Returns (survivors, position_ids, channels).  Position ids are returned so a
    downstream model can still tell WHERE each survivor came from (the original dropped this information)."""
    seq_axis = x.ndim - 2
    ch = sieve_channels(x.shape[seq_axis], variant)
    keep = ch == 0
    pos_ids = np.flatnonzero(keep)
    return np.take(x, pos_ids, axis=seq_axis), pos_ids, ch


def hybrid_keep(scores: np.ndarray, rate: float, floor_share: float = 0.5) -> np.ndarray:
    """Coverage floor from the sieve + best-scoring extra tokens, within ONE total budget of rate * n.
    The floor (position-only, causal, content-blind) takes floor_share of the budget; a content scorer fills the
    rest.  The floor uses the fixed golden-ratio rotation with finer bins (keep share = rate * floor_share).
    scores: higher = more important."""
    n = len(scores)
    bins = max(int(round(1.0 / (rate * floor_share))), 1)
    pos = np.arange(1, n + 1, dtype=np.float64)
    keep = np.floor(bins * ((pos / PHI) % 1.0)).astype(np.int64) == 0
    extra = int(round(rate * n)) - int(keep.sum())
    if extra > 0:
        s = np.where(keep, -np.inf, scores)
        keep[np.argsort(-s)[:extra]] = True
    return keep


# ------------------------------------------------------------------ comparators
def stride_keep(n: int, k: int, offset: int = 0) -> np.ndarray:
    return (np.arange(n) % k) == offset


def random_keep(n: int, rate: float, rng) -> np.ndarray:
    m = np.zeros(n, bool); m[rng.choice(n, int(round(rate * n)), replace=False)] = True
    return m


# ------------------------------------------------------------------ metrics
def phase_retention(keep: np.ndarray, period: int) -> np.ndarray:
    """Share of tokens kept at each position-mod-period.  A fair filter keeps ~the same share at every phase."""
    pos = np.arange(1, len(keep) + 1)
    return np.array([keep[(pos % period) == p].mean() for p in range(period)])


def alias_score(keep: np.ndarray, periods=range(2, 13)) -> float:
    """Worst phase deviation from the overall keep rate over periods 2..12.  0 = no aliasing, ~0.8 = severe."""
    r = keep.mean()
    return float(max(np.abs(phase_retention(keep, p) - r).max() for p in periods))


def max_gap(keep: np.ndarray) -> int:
    idx = np.flatnonzero(keep)
    return int(np.diff(idx).max()) if len(idx) > 1 else len(keep)


# ------------------------------------------------------------------ audit
def audit() -> None:
    print(f"golden angle 2*pi/phi^2 = {GOLDEN_ANGLE:.10f}   divided by 3 = {GOLDEN_ANGLE / 3:.10f}")
    print(f"  that is within {0.8 - GOLDEN_ANGLE / 3:.2e} of 4/5, so the 'spiral' mod 3 is almost a period-5 pattern.")
    print(f"  the drift away from period 5 takes about {1 / (0.8 - GOLDEN_ANGLE / 3):,.0f} tokens.\n")
    ch = sieve_channels(12, "original")
    print("12-token demo routing:", ch.tolist(), " keep mask:", (ch == 0).astype(int).tolist(), "(matches the Colab output)\n")
    big = sieve_channels(1_000_000, "original")
    print(f"{'window':>14} {'keep':>7} {'compress':>9} {'prune':>7}   (original sieve; ideal is 0.333 each)")
    for a, b in [(0, 100), (0, 5000), (20000, 25000), (40000, 45000), (60000, 65000), (0, 1_000_000)]:
        w = big[a:b]
        print(f"{a:>7}:{b:<6} {(w == 0).mean():>7.3f} {(w == 1).mean():>9.3f} {(w == 2).mean():>7.3f}")
    k = sieve_channels(5000, "original") == 0
    print("\nkept positions, first 8:", (np.flatnonzero(k)[:8] + 1).tolist(), " -> every 5th token, same as stride 5")
    print("retention by position mod 5 (first 5000 tokens):", np.round(phase_retention(k, 5), 2).tolist())
    print("   (the sieve keeps 100% of one phase and 0% of the other four)")


# ------------------------------------------------------------------ compare
def compare(n: int = 4000, trials: int = 200, rate: float = 1 / 3) -> None:
    rng = np.random.default_rng(0)
    print(f"n={n} tokens, target keep rate {rate:.3f}.  Positional metrics are exact; the needle test is SYNTHETIC.\n")
    rows = {
        "original": sieve_channels(n, "original") == 0,
        "fixed": sieve_channels(n, "fixed") == 0,
        "stride-3": stride_keep(n, 3),
        "stride-5": stride_keep(n, 5, 4),
        "random": random_keep(n, rate, rng),
    }
    print(f"{'method':<10}{'keep':>7}{'max gap':>9}{'alias score':>13}")
    for k, m in rows.items():
        print(f"{k:<10}{m.mean():>7.3f}{max_gap(m):>9}{alias_score(m):>13.3f}")

    # synthetic needle test: 5% of tokens are 'important'; a content scorer sees them with noise
    print("\nneedle test: share of important tokens retained (mean of", trials, "trials)")
    res = {k: [] for k in ["original", "fixed", "stride-5", "random", "hybrid"]}
    for t in range(trials):
        important = rng.random(n) < 0.05
        scores = important * 1.0 + rng.normal(0, 0.5, n)                  # noisy scorer, honest but imperfect
        for k in ["original", "fixed", "stride-5", "random"]:
            m = rows[k] if k != "random" else random_keep(n, rate, rng)
            res[k].append(m[important].mean())
        res["hybrid"].append(hybrid_keep(scores, rate)[important].mean())
    for k, v in res.items():
        print(f"  {k:<14}{np.mean(v):.3f}")
    # worst case: important tokens sit at one phase mod 5 (tables, rows, repeated templates)
    print("\nworst case: every important token at position = 4 (mod 5)  (periodic structure)")
    imp = (np.arange(1, n + 1) % 5) == 4
    for k in ["original", "fixed", "stride-5", "stride-3"]:
        print(f"  {k:<10}{rows[k][imp].mean():.3f}")
    print("  (original and stride-5 keep either all of them or none, depending on phase)")


# ------------------------------------------------------------------ tests
def run_tests() -> None:
    n_ok = 0

    def check(cond, msg):
        nonlocal n_ok
        assert cond, msg
        n_ok += 1
    c12 = sieve_channels(12, "original")
    check(c12.tolist() == [2, 1, 1, 0, 2, 2, 1, 1, 0, 2, 2, 1], "original routing must match the Colab run")
    check((c12 == 0).astype(int).tolist() == [0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0], "keep mask must match the Colab run")
    k = sieve_channels(5000, "original") == 0
    check(abs(k.mean() - 0.2) < 1e-9, "original keeps 1/5 over the first 5000 tokens, not 1/3")
    check(np.array_equal(k, stride_keep(5000, 5, 3)), "original is exactly stride-5 early on")
    check(abs(GOLDEN_ANGLE / 3 - 0.8) < 2e-5, "golden angle / 3 is almost 4/5")
    big = sieve_channels(1_000_000, "original")
    check(all(abs((big == j).mean() - 1 / 3) < 0.01 for j in range(3)), "original is 1/3 each only in the very long run")
    f = sieve_channels(100_000, "fixed")
    check(all(abs((f == j).mean() - 1 / 3) < 0.005 for j in range(3)), "fixed gives 1/3 per channel")
    check(abs((f[:50] == 0).mean() - 1 / 3) < 0.1, "fixed is about 1/3 even in short windows")
    check(alias_score(k) > 0.7, "original aliases badly")
    check(alias_score(f == 0) < 0.05, "fixed barely aliases")
    check(max_gap(f == 0) <= 5, "fixed has bounded gaps (three-gap property)")
    x = np.random.default_rng(1).random((2, 30, 8))
    s, ids, ch = sieve_select(x, "fixed")
    check(s.shape == (2, len(ids), 8) and np.array_equal(s, x[:, ids, :]), "select keeps the channel-0 tokens")
    check(len(ch) == 30 and len(ids) == (ch == 0).sum(), "position ids match the mask")
    check(np.array_equal(sieve_channels(30, "fixed"), sieve_channels(300, "fixed")[:30]), "mask for position n ignores total length (causal / streamable)")
    sc = np.random.default_rng(2).random(300)
    h = hybrid_keep(sc, 0.5)
    check(h.sum() == 150, "hybrid uses exactly the total budget")
    top = np.argsort(-sc)[:30]
    check(h[top].all() or h[top].mean() > 0.8, "hybrid keeps nearly all top-scored tokens")
    check(max_gap(hybrid_keep(np.zeros(300), 0.5)) <= 5, "with no scores the hybrid is still evenly spread (no big holes)")
    print(f"all {n_ok} checks passed")


if __name__ == "__main__":
    a = sys.argv
    if "--test" in a:
        run_tests()
    elif "--audit" in a:
        audit()
    elif "--compare" in a:
        compare()
    else:
        print(__doc__)
