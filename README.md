# What the Tech Job Market Actually Rewards

An end-to-end analytics project: scrape thousands of tech job postings, warehouse them in SQL,
and use advanced SQL + a logistic-regression model to answer **which skills are in demand, which
are rising, which travel together, and which raise the odds of a senior/high-pay role** — served
as a Power BI dashboard.

## Headline findings (7,907 postings, Aug 2024 - Jul 2026, HackerNews "Who is hiring?")
- **Most in-demand:** TypeScript, Python, React, PostgreSQL, AWS.
- **Fastest-rising skill:** LLM — roughly doubled its share of postings (5.0% -> 9.9%).
- **Remote is retreating:** remote share fell from **62% to 55%** over two years.
- **Skills that signal seniority** (logistic regression, AUC 0.64): Ruby (OR 2.0), Azure, Django,
  AWS, Go — mature backend/enterprise stacks. Newer frontend (Next.js, Vue, iOS) skews junior/mid.
- **Biggest salary premiums** (where disclosed, n=2,044): Android, Kafka, Rails, Java (+20-32%).

## Pipeline
```
scrape.py        HN Algolia API -> data/raw/postings.csv           (job posts)
parse.py         skill dictionary + role/seniority/remote/salary   -> data/clean/*.csv
load.py          -> SQL warehouse (SQLite default; --postgres opt) (star schema, schema.sql)
run_analysis.py  runs analysis.sql queries -> data/marts/*.csv     (for Power BI) + headlines
model.py         logistic regression (senior odds) + salary OLS    -> data/marts/*.csv
```

## Run it
```bash
pip install -r requirements.txt          # pandas, scikit-learn, statsmodels
python scrape.py --months 24
python parse.py
python load.py                           # SQLite: data/jobmarket.db
python run_analysis.py                   # exports marts + prints headlines
python model.py                          # odds ratios + salary premiums
# then build the dashboard per POWERBI_GUIDE.md
```
PostgreSQL (optional, for the warehouse keyword + native Power BI connection):
`python load.py --postgres "postgresql://user:pass@localhost:5432/jobmarket"` (same for run_analysis/model).

## Method & SQL depth
- **Star schema:** `fact_posting`, `dim_skill`, `dim_month`, `bridge_posting_skill` (see `schema.sql`).
- **Advanced SQL** (`analysis.sql`): window functions (rolling demand), a **skill co-occurrence
  self-join**, rising-skill share comparison, seniority mix, salary aggregation.
- **Model** (`model.py`): logistic regression `P(senior) ~ skills + role + remote` with odds ratios
  and 95% CIs; OLS on log-salary for premiums.

## Honest limitations
- Seniority and role are inferred from posting text (keyword-based) -> treat results as
  **associational, not causal**; the AUC is modest by design.
- HackerNews skews startup / remote / global; salary is disclosed in only ~26% of posts.
- Skills are matched via a curated dictionary (high precision, not exhaustive recall).
