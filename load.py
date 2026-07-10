"""
Load the parsed CSVs into a SQL warehouse (SQLite by default, PostgreSQL optional).

Inputs : data/clean/postings_parsed.csv, data/clean/posting_skills.csv
Output : a populated database with dim_month, fact_posting, dim_skill, bridge_posting_skill

Usage:
    python load.py                                  # SQLite -> data/jobmarket.db
    python load.py --postgres "postgresql://user:pass@localhost:5432/jobmarket"
"""
from __future__ import annotations

import argparse
import csv
import os

POSTINGS = "data/clean/postings_parsed.csv"
SKILLS = "data/clean/posting_skills.csv"
SCHEMA = "schema.sql"


def connect(args):
    if args.postgres:
        import psycopg2
        conn = psycopg2.connect(args.postgres)
        return conn, "%s"
    import sqlite3
    os.makedirs(os.path.dirname(args.sqlite) or ".", exist_ok=True)
    conn = sqlite3.connect(args.sqlite)
    return conn, "?"


def run_schema(conn):
    cur = conn.cursor()
    # idempotent: drop existing tables so re-runs don't collide
    for t in ("bridge_posting_skill", "fact_posting", "dim_skill", "dim_month"):
        cur.execute(f"DROP TABLE IF EXISTS {t}")
    sql = open(SCHEMA, encoding="utf-8").read()
    for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
        cur.execute(stmt)
    conn.commit()


def load(args):
    conn, ph = connect(args)
    run_schema(conn)
    cur = conn.cursor()

    with open(POSTINGS, encoding="utf-8") as f:
        postings = list(csv.DictReader(f))
    with open(SKILLS, encoding="utf-8") as f:
        pskills = list(csv.DictReader(f))

    # dim_month
    months = {}
    for r in postings:
        m = r["thread_month"]
        if m and m not in months:
            y, mm = m.split("-")
            months[m] = (int(y), int(mm))
    cur.executemany(
        f"INSERT INTO dim_month(month,year,month_num) VALUES({ph},{ph},{ph})",
        [(m, y, mm) for m, (y, mm) in months.items()])

    # fact_posting
    def _int(x):
        return int(x) if str(x).strip() not in ("", "None") else None
    cur.executemany(
        f"""INSERT INTO fact_posting
            (posting_id,month,role_family,seniority,remote_flag,salary_min,salary_max,n_skills)
            VALUES({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})""",
        [(r["posting_id"], r["thread_month"], r["role_family"], r["seniority"],
          _int(r["remote_flag"]), _int(r["salary_min"]), _int(r["salary_max"]),
          _int(r["n_skills"])) for r in postings])

    # dim_skill (distinct)
    skills = {}
    for r in pskills:
        skills.setdefault(r["skill_name"], r["skill_category"])
    skill_id = {name: i + 1 for i, name in enumerate(sorted(skills))}
    cur.executemany(
        f"INSERT INTO dim_skill(skill_id,skill_name,skill_category) VALUES({ph},{ph},{ph})",
        [(skill_id[n], n, c) for n, c in skills.items()])

    # bridge (dedupe)
    seen = set()
    bridge = []
    for r in pskills:
        key = (r["posting_id"], skill_id[r["skill_name"]])
        if key not in seen:
            seen.add(key)
            bridge.append(key)
    cur.executemany(
        f"INSERT INTO bridge_posting_skill(posting_id,skill_id) VALUES({ph},{ph})", bridge)

    conn.commit()
    print(f"Loaded: {len(postings)} postings, {len(skills)} skills, {len(bridge)} bridge rows")
    print(f"DB ready: {'PostgreSQL' if args.postgres else args.sqlite}")
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", default="data/jobmarket.db")
    ap.add_argument("--postgres", default="", help="postgres DSN; overrides sqlite")
    load(ap.parse_args())
