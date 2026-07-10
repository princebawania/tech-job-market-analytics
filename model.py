"""
The statistical centrepiece: which skills raise the odds of a SENIOR role?

Fits a logistic regression   P(senior) ~ skills + role_family + remote
and reports each skill's ODDS RATIO with a 95% confidence interval
(odds ratio > 1 => the skill is associated with more senior postings).

Bonus (where salary is disclosed): an OLS on log(salary) gives an approximate
percentage salary premium per skill.

Inputs : the warehouse built by load.py
Outputs: data/marts/skill_seniority_odds.csv  (+ skill_salary_premium.csv if enough salary data)
         prints the headline odds ratios + model AUC.

Requires: pandas, scikit-learn, statsmodels
Usage:   python model.py            (SQLite)
         python model.py --postgres "postgresql://..."
"""
from __future__ import annotations

import argparse
import numpy as np
import pandas as pd


def get_conn(args):
    if args.postgres:
        import psycopg2
        return psycopg2.connect(args.postgres)
    import sqlite3
    return sqlite3.connect(args.sqlite)


def load_frames(conn):
    posts = pd.read_sql_query(
        "SELECT posting_id, seniority, remote_flag, role_family, salary_min, salary_max "
        "FROM fact_posting", conn)
    sk = pd.read_sql_query(
        "SELECT b.posting_id, s.skill_name FROM bridge_posting_skill b "
        "JOIN dim_skill s ON s.skill_id=b.skill_id", conn)
    return posts, sk


def build_design(posts, sk, top_n):
    posts = posts.set_index("posting_id")
    top = sk["skill_name"].value_counts().head(top_n).index.tolist()
    sk = sk[sk["skill_name"].isin(top)]
    skill_dum = (pd.crosstab(sk["posting_id"], sk["skill_name"])
                 .clip(upper=1)
                 .reindex(posts.index).fillna(0).astype(int))
    skill_dum.columns = [f"skill::{c}" for c in skill_dum.columns]
    role_dum = pd.get_dummies(posts["role_family"], prefix="role", drop_first=True).astype(int)
    X = skill_dum.join(role_dum)
    X["remote"] = posts["remote_flag"].astype(int)
    return X, posts, top


def seniority_model(X, posts):
    import statsmodels.api as sm
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import roc_auc_score

    y = (posts["seniority"] == "senior").astype(int)

    # AUC via a held-out split (sklearn)
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
    clf = LogisticRegression(max_iter=1000, C=1.0)
    clf.fit(Xtr, ytr)
    auc = roc_auc_score(yte, clf.predict_proba(Xte)[:, 1])

    # odds ratios + CIs (statsmodels)
    Xc = sm.add_constant(X.astype(float))
    try:
        res = sm.Logit(y, Xc).fit(disp=0, maxiter=200)
        params, ci, pvals = res.params, res.conf_int(), res.pvalues
        rows = []
        for name in X.columns:
            rows.append({
                "feature": name,
                "odds_ratio": float(np.exp(params[name])),
                "ci_low": float(np.exp(ci.loc[name, 0])),
                "ci_high": float(np.exp(ci.loc[name, 1])),
                "p_value": float(pvals[name]),
            })
        table = pd.DataFrame(rows)
    except Exception as e:                       # noqa: BLE001
        print(f"  [statsmodels fell back to sklearn coefs, no CIs: {e}]")
        table = pd.DataFrame({
            "feature": X.columns,
            "odds_ratio": np.exp(clf.coef_[0]),
            "ci_low": np.nan, "ci_high": np.nan, "p_value": np.nan})
    table = table.sort_values("odds_ratio", ascending=False).reset_index(drop=True)
    return table, auc


def salary_model(X, posts, min_rows=150):
    import statsmodels.api as sm
    sal = ((posts["salary_min"].astype(float) + posts["salary_max"].astype(float)) / 2)
    mask = sal.notna() & (sal > 0)
    if mask.sum() < min_rows:
        return None
    y = np.log(sal[mask])
    Xc = sm.add_constant(X[mask].astype(float))
    res = sm.OLS(y, Xc).fit()
    rows = []
    for name in X.columns:
        if name in res.params:
            rows.append({"feature": name,
                         "pct_premium": float(np.exp(res.params[name]) - 1),
                         "p_value": float(res.pvalues[name])})
    return (pd.DataFrame(rows).sort_values("pct_premium", ascending=False)
            .reset_index(drop=True), int(mask.sum()))


def _skill_only(df):
    d = df[df["feature"].str.startswith("skill::")].copy()
    d["feature"] = d["feature"].str.replace("skill::", "", regex=False)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", default="data/jobmarket.db")
    ap.add_argument("--postgres", default="")
    ap.add_argument("--top-n", type=int, default=40, help="model the top-N skills")
    args = ap.parse_args()

    conn = get_conn(args)
    posts, sk = load_frames(conn)
    X, posts, top = build_design(posts, sk, args.top_n)
    print(f"Modelling {len(posts)} postings, {len(top)} skills; "
          f"senior rate = {(posts['seniority']=='senior').mean():.1%}")

    table, auc = seniority_model(X, posts)
    import os
    os.makedirs("data/marts", exist_ok=True)
    table.to_csv("data/marts/skill_seniority_odds.csv", index=False)

    skills = _skill_only(table)
    print(f"\nSeniority model AUC = {auc:.3f}")
    print("\nTop skills RAISING odds of a senior role:")
    for _, r in skills.head(8).iterrows():
        ci = "" if np.isnan(r["ci_low"]) else f"  (95% CI {r['ci_low']:.2f}-{r['ci_high']:.2f})"
        print(f"   {r['feature']:<16} OR={r['odds_ratio']:.2f}{ci}")
    print("\nSkills LOWERING odds of a senior role:")
    for _, r in skills.tail(5).iloc[::-1].iterrows():
        ci = "" if np.isnan(r["ci_low"]) else f"  (95% CI {r['ci_low']:.2f}-{r['ci_high']:.2f})"
        print(f"   {r['feature']:<16} OR={r['odds_ratio']:.2f}{ci}")

    sal = salary_model(X, posts)
    if sal is not None:
        stab, n = sal
        stab.to_csv("data/marts/skill_salary_premium.csv", index=False)
        sk_sal = _skill_only(stab)
        print(f"\nSalary premium model (n={n} postings with salary):")
        for _, r in sk_sal.head(6).iterrows():
            print(f"   {r['feature']:<16} {r['pct_premium']:+.0%}")
    else:
        print("\n(Salary model skipped: too few postings with disclosed salary.)")

    conn.close()
    print("\nExported model results to data/marts/")


if __name__ == "__main__":
    main()
