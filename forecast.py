"""
Demand forecasting: predict where each skill's share of postings is heading.

For each top skill we model its MONTHLY SHARE (skill postings / all postings that
month, to remove volume effects), forecast the next 6 months with Holt's linear
exponential smoothing, and attach uncertainty bands.

Crucially, we BACKTEST: hold out the last 3 months, forecast them, and compare
the error to a naive "last value carried forward" baseline -- so the forecast is
validated, not just asserted.

Inputs : the warehouse from load.py
Outputs: data/marts/forecast_demand.csv  (actuals + forecast + bands, for the dashboard)
         prints backtest accuracy + the skills projected to rise/fall most.

Requires: pandas, numpy, statsmodels
Usage:   python forecast.py            (SQLite)
         python forecast.py --postgres "postgresql://..."
"""
from __future__ import annotations

import argparse
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HORIZON = 6           # months to forecast
HOLDOUT = 3           # months held out for backtest
MIN_MONTHS = 12       # need at least this much history to model a skill


def get_conn(args):
    if args.postgres:
        import psycopg2
        return psycopg2.connect(args.postgres)
    import sqlite3
    return sqlite3.connect(args.sqlite)


def add_months(month: str, k: int) -> str:
    y, m = map(int, month.split("-"))
    idx = (y * 12 + (m - 1)) + k
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def load_shares(conn, top_n: int):
    totals = pd.read_sql_query(
        "SELECT month, COUNT(*) AS n FROM fact_posting GROUP BY month", conn)
    sk = pd.read_sql_query(
        "SELECT s.skill_name, f.month, COUNT(*) AS n "
        "FROM fact_posting f "
        "JOIN bridge_posting_skill b ON b.posting_id=f.posting_id "
        "JOIN dim_skill s ON s.skill_id=b.skill_id "
        "GROUP BY s.skill_name, f.month", conn)
    months = sorted(totals["month"])
    tot = totals.set_index("month")["n"].reindex(months)
    top = sk.groupby("skill_name")["n"].sum().nlargest(top_n).index.tolist()
    shares = {}
    for skill in top:
        s = (sk[sk.skill_name == skill].set_index("month")["n"]
             .reindex(months).fillna(0))
        shares[skill] = (s / tot).fillna(0).values.astype(float)
    return months, shares


def smooth(y: np.ndarray, w: int) -> np.ndarray:
    """Centred-safe trailing moving average (min_periods=1) to model the trend, not the noise."""
    if w <= 1:
        return y
    return pd.Series(y).rolling(w, min_periods=1).mean().values


def _fit_forecast(y: np.ndarray, horizon: int):
    """Holt's linear exponential smoothing; linear-trend fallback."""
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    try:
        m = ExponentialSmoothing(y, trend="add", damped_trend=True,
                                 initialization_method="estimated").fit()
        fc = np.asarray(m.forecast(horizon))
        resid = y - np.asarray(m.fittedvalues)
        return fc, float(np.std(resid))
    except Exception:
        t = np.arange(len(y))
        a, b = np.polyfit(t, y, 1)
        fc = a * np.arange(len(y), len(y) + horizon) + b
        resid = y - (a * t + b)
        return fc, float(np.std(resid))


def backtest(shares: dict, w: int = 1):
    """Compare Holt forecast vs naive last-value on a 3-month holdout."""
    beat = tot_m = 0
    mae_model, mae_naive = [], []
    for y0 in shares.values():
        if len(y0) < HOLDOUT + 6:
            continue
        y = smooth(y0, w)
        train, test = y[:-HOLDOUT], y[-HOLDOUT:]
        pred, _ = _fit_forecast(train, HOLDOUT)
        naive = np.repeat(train[-1], HOLDOUT)
        mm, mn = np.mean(np.abs(test - pred)), np.mean(np.abs(test - naive))
        mae_model.append(mm)
        mae_naive.append(mn)
        tot_m += 1
        beat += 1 if mm <= mn else 0
    if not tot_m:
        return None
    return {
        "skills_tested": tot_m,
        "mae_model": float(np.mean(mae_model)),
        "mae_naive": float(np.mean(mae_naive)),
        "pct_beat_naive": beat / tot_m,
        "improvement": 1 - np.mean(mae_model) / np.mean(mae_naive),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", default="data/jobmarket.db")
    ap.add_argument("--postgres", default="")
    ap.add_argument("--top-n", type=int, default=25)
    ap.add_argument("--smooth", type=int, default=1,
                    help="months of moving-average smoothing on the target trend (1 = raw)")
    args = ap.parse_args()

    conn = get_conn(args)
    months, shares = load_shares(conn, args.top_n)
    shares = {k: v for k, v in shares.items() if (v > 0).sum() >= MIN_MONTHS}
    print(f"Forecasting {len(shares)} skills over {len(months)} months "
          f"({months[0]} .. {months[-1]}); horizon={HORIZON}mo; smooth={args.smooth}mo")

    bt = backtest(shares, args.smooth)
    if bt:
        print(f"\nBacktest (last {HOLDOUT} months held out, {bt['skills_tested']} skills):")
        print(f"   model MAE {bt['mae_model']:.4f}  vs  naive MAE {bt['mae_naive']:.4f}")
        verdict = "BEATS" if bt["improvement"] > 0 else "does NOT beat"
        print(f"   forecast {verdict} naive: {bt['improvement']:+.0%} error change, "
              f"wins on {bt['pct_beat_naive']:.0%} of skills")

    # full forecast for export + ranking
    rows, projected = [], []
    fut = [add_months(months[-1], k) for k in range(1, HORIZON + 1)]
    for skill, y0 in shares.items():
        y = y0
        for mo, val in zip(months, y0):
            rows.append({"skill_name": skill, "month": mo, "share": val,
                         "kind": "actual", "lower": val, "upper": val})
        y = smooth(y, args.smooth)
        fc, sd = _fit_forecast(y, HORIZON)
        for mo, val in zip(fut, fc):
            v = max(0.0, float(val))
            rows.append({"skill_name": skill, "month": mo, "share": v, "kind": "forecast",
                         "lower": max(0.0, v - 1.96 * sd), "upper": v + 1.96 * sd})
        projected.append((skill, float(fc[-1] - y[-1]), y[-1], float(max(0.0, fc[-1]))))

    import os
    os.makedirs("data/marts", exist_ok=True)
    pd.DataFrame(rows).to_csv("data/marts/forecast_demand.csv", index=False)

    projected.sort(key=lambda x: x[1], reverse=True)
    print("\nProjected to RISE most (next 6 months, share pts):")
    for name, chg, now, fut_v in projected[:6]:
        print(f"   {name:<16} {now:.1%} -> {fut_v:.1%}  ({chg*100:+.2f} pts)")
    print("\nProjected to DECLINE most:")
    for name, chg, now, fut_v in projected[-4:][::-1]:
        print(f"   {name:<16} {now:.1%} -> {fut_v:.1%}  ({chg*100:+.2f} pts)")

    conn.close()
    print("\nExported data/marts/forecast_demand.csv")


if __name__ == "__main__":
    main()
