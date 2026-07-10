# What the Tech Job Market Actually Rewards

An end-to-end analytics project: scrape thousands of tech job postings, warehouse them in SQL,
and use advanced SQL, a logistic-regression model, and a backtested demand forecast to answer
**which skills are in demand, which are rising, which travel together, and which raise the odds
of a senior/high-pay role** — served as an interactive **Streamlit** dashboard.

## Headline findings (7,907 postings, Aug 2024 – Jul 2026, HackerNews "Who is hiring?")
- **Most in-demand:** TypeScript, Python, React, PostgreSQL, AWS.
- **Fastest-rising skill:** LLM — roughly doubled its share of postings (5.0% → 9.9%).
- **Remote is retreating:** remote share fell from **62% to 55%** over two years.
- **Dominant skill pairing:** React + TypeScript (1,203 postings).
- **Skills that signal seniority** (logistic regression, AUC 0.64): Ruby (OR 2.0), Azure, Django,
  AWS, Go — mature backend/enterprise stacks. Newer frontend (Next.js, Vue, iOS) skews junior/mid.
- **Biggest salary premiums** (where disclosed, n=2,044): Android, Kafka, Rails, Java (+20–32%).
- **Demand forecast:** a backtested 6-month forecast projects PostgreSQL, Python & AWS as top risers
  — but does **not** beat a naive baseline, showing monthly demand is largely a random walk (see limitations).

## Pipeline
```
scrape.py        HN Algolia API -> data/raw/postings.csv            (job posts)
parse.py         skill dictionary + role/seniority/remote/salary    -> data/clean/*.csv
load.py          -> SQL warehouse (SQLite default; --postgres opt)  (star schema, schema.sql)
run_analysis.py  runs analysis.sql queries -> data/marts/*.csv      (dashboard inputs) + headlines
model.py         logistic regression (senior odds) + salary OLS     -> data/marts/*.csv
forecast.py      Holt's exponential-smoothing forecast + backtest   -> data/marts/forecast_demand.csv
app.py           Streamlit dashboard over data/marts/*.csv
```

## Run it
```
pip install -r requirements.txt          # pandas, scikit-learn, statsmodels, streamlit, plotly
python scrape.py --months 24
python parse.py
python load.py                           # SQLite: data/jobmarket.db
python run_analysis.py                   # exports marts + prints headlines
python model.py                          # odds ratios + salary premiums
python forecast.py                       # 6-month demand forecast + backtest vs naive
streamlit run app.py                     # interactive dashboard
```
PostgreSQL (optional, for the warehouse keyword): `python load.py --postgres "postgresql://user:pass@localhost:5432/jobmarket"` (same flag for run_analysis / model / forecast).

## Method & depth
- **Star schema:** `fact_posting`, `dim_skill`, `dim_month`, `bridge_posting_skill` (see `schema.sql`).
- **Advanced SQL** (`analysis.sql`): window functions (rolling demand), a **skill co-occurrence
  self-join**, rising-skill share comparison, seniority mix, salary aggregation.
- **Model** (`model.py`): logistic regression `P(senior) ~ skills + role + remote` with odds ratios
  and 95% CIs; OLS on log-salary for premiums.
- **Forecast** (`forecast.py`): Holt's linear exponential smoothing on each skill's monthly share,
  **backtested against a naive last-value baseline** on a 3-month holdout.
- **Dashboard:** an interactive Streamlit app (`app.py`) driven by the exported marts.

## Honest limitations
- Seniority and role are inferred from posting text (keyword-based) → results are
  **associational, not causal**; the model AUC is modest by design.
- The demand forecast does **not** beat a naive baseline — monthly skill-demand share is
  noise-dominated, so it is best read as a **directional** trend indicator, not a precise predictor.
- HackerNews skews startup / remote / global; salary is disclosed in only ~26% of posts.
- Skills are matched via a curated dictionary (high precision, not exhaustive recall).
