# Power BI dashboard — build guide

You already generated the data in `data/marts/`. Power BI just visualises those CSVs.
No database connection required (though you can connect to Postgres later if you want).

## Load the data
1. Open **Power BI Desktop** -> **Home > Get data > Text/CSV**.
2. Import each file from `data/marts/`:
   `top_skills, skills_by_role, monthly_demand, rising_skills, cooccurrence,
    remote_by_month, seniority_by_skill, skill_seniority_odds, skill_salary_premium`.
3. Check column types (skill counts = whole number, shares/odds = decimal).

## Page 1 — Market Overview
| Visual | Data | Notes |
|--------|------|-------|
| Bar chart: top skills | `top_skills` | skill_name (axis) x n_postings (value), top 20 |
| Line chart: demand over time | `monthly_demand` | month (axis), n (value), legend = skill_name; filter to 6-8 top skills |
| Line chart: remote share | `remote_by_month` | month x remote_share (format %) — tell the RTO story |
| KPI cards | `top_skills` / `remote_by_month` | total postings, # skills, latest remote % |

## Page 2 — Skill Intelligence
| Visual | Data | Notes |
|--------|------|-------|
| Rising vs declining | `rising_skills` | bar of (late_share - early_share); add a calc column for the delta |
| Skill co-occurrence | `cooccurrence` | matrix/heatmap skill_a x skill_b (values = pair_count); or a Network visual if installed |
| Seniority mix | `seniority_by_skill` | bar of senior_share by skill (sorted) |
| Top skills per role | `skills_by_role` | matrix: role_family x skill_name (value n), or small multiples |

## Page 3 — What Pays / What Signals Seniority (the model)
| Visual | Data | Notes |
|--------|------|-------|
| Odds ratios | `skill_seniority_odds` | bar of odds_ratio by feature (skill:: rows); add error bars from ci_low/ci_high if desired; reference line at OR=1 |
| Salary premium | `skill_salary_premium` | bar of pct_premium by skill (format %) |
| Text box | — | 3-4 crisp takeaways + a one-line limitations note |

## Polish
- One accent colour; consistent number formatting; clear titles that state the finding
  ("Remote roles fell 62% -> 55%"), not just the metric name.
- Add a small "Data & method" text box: source (HN Who-is-Hiring), N postings, date range,
  and the honest caveat (keyword-based seniority label; HN skews startup/remote).
- Export a PNG of each page for your portfolio.
