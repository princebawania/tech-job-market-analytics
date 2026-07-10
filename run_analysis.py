"""
Run the analysis queries against the warehouse, export result tables to
data/marts/*.csv (for Power BI), and print headline numbers (for your resume).

Usage:
    python run_analysis.py                       # SQLite (data/jobmarket.db)
    python run_analysis.py --postgres "postgresql://user:pass@localhost:5432/jobmarket"
"""
from __future__ import annotations

import argparse
import csv
import os

MARTS = "data/marts"

QUERIES = {
"top_skills": """
SELECT s.skill_name, s.skill_category, COUNT(*) AS n_postings
FROM bridge_posting_skill b JOIN dim_skill s ON s.skill_id=b.skill_id
GROUP BY s.skill_name, s.skill_category ORDER BY n_postings DESC;""",

"skills_by_role": """
SELECT role_family, skill_name, n, rk FROM (
  SELECT f.role_family, s.skill_name, COUNT(*) AS n,
         RANK() OVER (PARTITION BY f.role_family ORDER BY COUNT(*) DESC) AS rk
  FROM fact_posting f
  JOIN bridge_posting_skill b ON b.posting_id=f.posting_id
  JOIN dim_skill s ON s.skill_id=b.skill_id
  WHERE f.role_family IN ('SDE','Data-ML','Analyst')
  GROUP BY f.role_family, s.skill_name) t
WHERE rk<=8 ORDER BY role_family, rk;""",

"monthly_demand": """
WITH monthly AS (
  SELECT b.skill_id, f.month, COUNT(*) AS n
  FROM fact_posting f JOIN bridge_posting_skill b ON b.posting_id=f.posting_id
  GROUP BY b.skill_id, f.month)
SELECT s.skill_name, m.month, m.n,
  AVG(m.n) OVER (PARTITION BY m.skill_id ORDER BY m.month
                 ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS rolling_3m
FROM monthly m JOIN dim_skill s ON s.skill_id=m.skill_id
ORDER BY s.skill_name, m.month;""",

"rising_skills": """
WITH months AS (
  SELECT month, ROW_NUMBER() OVER (ORDER BY month) AS rn, COUNT(*) OVER () AS total_m
  FROM (SELECT DISTINCT month FROM fact_posting) d),
tagged AS (
  SELECT f.posting_id,
    CASE WHEN m.rn<=6 THEN 'early' WHEN m.rn>m.total_m-6 THEN 'late' END AS period
  FROM fact_posting f JOIN months m ON m.month=f.month),
ptot AS (SELECT period, COUNT(DISTINCT posting_id) AS tot
         FROM tagged WHERE period IS NOT NULL GROUP BY period),
sp AS (
  SELECT s.skill_name, t.period, COUNT(*) AS n
  FROM tagged t JOIN bridge_posting_skill b ON b.posting_id=t.posting_id
  JOIN dim_skill s ON s.skill_id=b.skill_id
  WHERE t.period IS NOT NULL GROUP BY s.skill_name, t.period)
SELECT skill_name,
  MAX(CASE WHEN period='early' THEN 1.0*n/(SELECT tot FROM ptot WHERE period='early') END) AS early_share,
  MAX(CASE WHEN period='late'  THEN 1.0*n/(SELECT tot FROM ptot WHERE period='late')  END) AS late_share
FROM sp GROUP BY skill_name
ORDER BY (COALESCE(late_share,0)-COALESCE(early_share,0)) DESC;""",

"cooccurrence": """
SELECT s1.skill_name AS skill_a, s2.skill_name AS skill_b, COUNT(*) AS pair_count
FROM bridge_posting_skill x
JOIN bridge_posting_skill y ON x.posting_id=y.posting_id AND x.skill_id<y.skill_id
JOIN dim_skill s1 ON s1.skill_id=x.skill_id
JOIN dim_skill s2 ON s2.skill_id=y.skill_id
GROUP BY s1.skill_name, s2.skill_name
ORDER BY pair_count DESC LIMIT 50;""",

"remote_by_month": """
SELECT month, 1.0*SUM(remote_flag)/COUNT(*) AS remote_share, COUNT(*) AS n_postings
FROM fact_posting GROUP BY month ORDER BY month;""",

"seniority_by_skill": """
SELECT s.skill_name,
  1.0*SUM(CASE WHEN f.seniority='senior' THEN 1 ELSE 0 END)/COUNT(*) AS senior_share,
  COUNT(*) AS n
FROM fact_posting f JOIN bridge_posting_skill b ON b.posting_id=f.posting_id
JOIN dim_skill s ON s.skill_id=b.skill_id
GROUP BY s.skill_name HAVING COUNT(*)>=30 ORDER BY senior_share DESC;""",
}

SALARY_SQLITE = """
SELECT s.skill_name, AVG((f.salary_min+f.salary_max)/2.0) AS avg_salary, COUNT(*) AS n
FROM fact_posting f JOIN bridge_posting_skill b ON b.posting_id=f.posting_id
JOIN dim_skill s ON s.skill_id=b.skill_id
WHERE f.salary_min IS NOT NULL GROUP BY s.skill_name HAVING COUNT(*)>=20
ORDER BY avg_salary DESC;"""

SALARY_PG = """
SELECT s.skill_name,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY (f.salary_min+f.salary_max)/2.0) AS median_salary,
  COUNT(*) AS n
FROM fact_posting f JOIN bridge_posting_skill b ON b.posting_id=f.posting_id
JOIN dim_skill s ON s.skill_id=b.skill_id
WHERE f.salary_min IS NOT NULL GROUP BY s.skill_name HAVING COUNT(*)>=20
ORDER BY median_salary DESC;"""


def run(conn, sql):
    cur = conn.cursor()
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return cols, cur.fetchall()


def export(name, cols, rows):
    os.makedirs(MARTS, exist_ok=True)
    with open(f"{MARTS}/{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", default="data/jobmarket.db")
    ap.add_argument("--postgres", default="")
    args = ap.parse_args()

    if args.postgres:
        import psycopg2
        conn = psycopg2.connect(args.postgres)
        queries = {**QUERIES, "salary_by_skill": SALARY_PG}
    else:
        import sqlite3
        conn = sqlite3.connect(args.sqlite)
        queries = {**QUERIES, "salary_by_skill": SALARY_SQLITE}

    for name, sql in queries.items():
        try:
            cols, rows = run(conn, sql)
            export(name, cols, rows)
            print(f"  exported {name:<20} ({len(rows)} rows)")
        except Exception as e:                       # noqa: BLE001
            print(f"  [skip] {name}: {e}")

    # headline numbers
    print("\n===== HEADLINES =====")
    _, ts = run(conn, QUERIES["top_skills"])
    print("Top 10 skills:", ", ".join(f"{r[0]}({r[2]})" for r in ts[:10]))
    _, rm = run(conn, QUERIES["remote_by_month"])
    if rm:
        print(f"Remote share: {rm[0][0]} = {rm[0][1]:.0%}  ->  {rm[-1][0]} = {rm[-1][1]:.0%}")
    _, rs = run(conn, QUERIES["rising_skills"])
    rs2 = [r for r in rs if r[1] is not None and r[2] is not None]
    if rs2:
        top = rs2[0]
        print(f"Fastest riser: {top[0]} ({top[1]:.1%} -> {top[2]:.1%})")
    _, co = run(conn, QUERIES["cooccurrence"])
    if co:
        print(f"Top skill pair: {co[0][0]} + {co[0][1]} ({co[0][2]} postings)")
    conn.close()
    print(f"\nMarts exported to {MARTS}/ (load these into Power BI)")


if __name__ == "__main__":
    main()
