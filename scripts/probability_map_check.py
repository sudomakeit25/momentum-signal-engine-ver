"""Walk-forward check of the probability map across many stocks. Read-only.

Runs src/scanner/probability_map.calibrate on each symbol (each session of
the last CAL_SESSIONS scored using only what was known then), pools the
Brier scores and reports how often what the map said came true. The
volatility settings in probability_map.py were chosen with this script on
the whole universe rather than on one stock.

Usage, from the repo root:
  .venv/bin/python scripts/probability_map_check.py [SYMBOL ...]
With no symbols it uses the intraday universe plus the crypto miners.
Skill = 1 - Brier(map) / Brier(the stock's usual, unscaled odds): above 0
means the map beat the usual odds; 0.02 or more is called "more accurate".
"""
import sys
import time

sys.path.insert(0, ".")

import numpy as np  # noqa: E402

from src.data import client  # noqa: E402
from src.scanner import probability_map as pmap  # noqa: E402


def skill(m, u):
    return 1 - m / u if u else float("nan")


def universe() -> list[str]:
    if len(sys.argv) > 1:
        return [s.upper() for s in sys.argv[1:]]
    from src.scanner import intraday_movers as m
    from src.scanner.spike_reversal import EXTRA_GROUPS
    return list(dict.fromkeys(m._intraday_universe(None) + list(EXTRA_GROUPS["crypto_miners"])))


def main():
    syms = universe()
    bars = {}
    for i in range(0, len(syms), 40):
        bars.update(client.get_multi_bars(syms[i:i + 40], days=pmap.HISTORY_DAYS))
    data = {s: pmap.clean_bars(df) for s, df in bars.items()}
    data = {s: d for s, d in data.items() if len(d) >= pmap.WARMUP + pmap.MIN_ORIGINS + 40}
    print(f"{len(data)} symbols with enough history (of {len(syms)})")

    tot = {k: 0.0 for k in ("gm", "gu", "gm10", "gu10", "bm", "bu", "bo", "buo")}
    per_symbol, better, t0 = {}, 0, time.time()
    for s, d in data.items():
        cal = pmap.calibrate(pmap.prepare(d))
        if not cal or not cal["grid"] or not cal["big_day"]:
            continue
        g, b = cal["grid"], cal["big_day"]
        for k, v in (("gm", g["brier_model"]), ("gu", g["brier_usual"]), ("gm10", g["brier_model_10"]),
                     ("gu10", g["brier_usual_10"]), ("bm", b["brier_model"]), ("bu", b["brier_usual"]),
                     ("bo", b["brier_open"]), ("buo", b["brier_usual_open"])):
            tot[k] += v
        better += skill(g["brier_model"], g["brier_usual"]) > 0
        per_symbol[s] = (cal, len(d))
    secs = time.time() - t0
    print(f"pooled skill against each stock's usual odds: map {skill(tot['gm'], tot['gu']):+.3f}, "
          f"10% rows {skill(tot['gm10'], tot['gu10']):+.3f}, next-session 10% close from the close "
          f"{skill(tot['bm'], tot['bu']):+.3f}, from the open {skill(tot['bo'], tot['buo']):+.3f}; "
          f"map beat usual on {better} of {len(per_symbol)} stocks ({secs / max(len(per_symbol), 1):.2f}s each)")

    # Reliability of the default settings, pooled over every stock.
    pooled = {}
    for cal, _ in per_symbol.values():
        for b in cal["grid"]["bins"]:
            agg = pooled.setdefault((b["lo"], b["hi"]), [0, 0.0, 0.0])
            agg[0] += b["n"]
            agg[1] += b["said"] * b["n"]
            agg[2] += b["happened"] * b["n"]
    print("\nWhen the map said ... it happened (every stock, level and window pooled)")
    for (lo, hi), (n, said, happened) in sorted(pooled.items()):
        print(f"  {lo * 100:>4.0f}-{hi * 100:<4.0f}%  said {said / n * 100:5.1f}%  happened {happened / n * 100:5.1f}%  ({n} cases)")

    focus = [s for s in ("CLSK", "RIOT", "MARA", "IREN", "CIFR", "WULF", "HUT", "MSTR", "AAPL", "SPY", "TSLA", "NVDA")
             if s in per_symbol]
    print(f"\n{'symbol':<6} {'sessions':>8} {'map skill':>9} {'10% rows':>9} {'10% close':>9} {'at open':>8} {'10% closes':>10}")
    for s in focus:
        cal, _ = per_symbol[s]
        g, b = cal["grid"], cal["big_day"]
        print(f"{s:<6} {g['sessions']:>8} {skill(g['brier_model'], g['brier_usual']):>+9.3f}"
              f" {skill(g['brier_model_10'], g['brier_usual_10']):>+9.3f} {skill(b['brier_model'], b['brier_usual']):>+9.3f}"
              f" {skill(b['brier_open'], b['brier_usual_open']):>+8.3f} {b['happened']:>10}")
    sk = np.array([skill(c["grid"]["brier_model"], c["grid"]["brier_usual"]) for c, _ in per_symbol.values()])
    print(f"\nper-stock map skill: median {np.median(sk):+.3f}, 10th pct {np.percentile(sk, 10):+.3f}, "
          f"90th pct {np.percentile(sk, 90):+.3f}")


if __name__ == "__main__":
    main()
