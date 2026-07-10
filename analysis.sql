-- Analysis queries for the tech job-market warehouse.
-- Portable across SQLite (3.25+) and PostgreSQL, except where noted.

-- 1. Top skills by demand ----------------------------------------------------
SELECT s.skill_name, s.skill_category, COUNT(*) AS n_postings
FROM bridge_posting_skill b
JOIN dim_skill s ON s.skill_id = b.skill_id
GROUP BY s.skill_name, s.skill_category
ORDER BY n_postings DESC;

-- 2. Top 8 skills PER role family (window RANK in a subquery) -----------------
SELECT role_family, skill_name, n, rk FROM (
    SELECT f.role_family, s.skill_name, COUNT(*) AS n,
           RANK() OVER (PARTITION BY f.role_family ORDER BY COUNT(*) DESC) AS rk
    FROM fact_posting f
    JOIN bridge_posting_skill b ON b.posting_id = f.posting_id
    JOIN dim_skill s ON s.skill_id = b.skill_id
    WHERE f.role_family IN ('SDE','Data-ML','Analyst')
    GROUP BY f.role_family, s.skill_name
) t
WHERE rk <= 8
ORDER BY role_family, rk;

-- 3. Monthly demand + 3-month rolling average (window functions) --------------
WITH monthly AS (
    SELECT b.skill_id, f.month, COUNT(*) AS n
    FROM fact_posting f
    JOIN bridge_posting_skill b ON b.posting_id = f.posting_id
    GROUP BY b.skill_id, f.month
)
SELECT s.skill_name, m.month, m.n,
       AVG(m.n) OVER (PARTITION BY m.skill_id ORDER BY m.month
                      ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS rolling_3m
FROM monthly m
JOIN dim_skill s ON s.skill_id = m.skill_id
ORDER BY s.skill_name, m.month;

-- 4. Fastest-rising skills: share in last 6 months vs first 6 months ----------
WITH months AS (
    SELECT month, ROW_NUMBER() OVER (ORDER BY month) AS rn,
           COUNT(*) OVER () AS total_m
    FROM (SELECT DISTINCT month FROM fact_posting) d
),
tagged AS (
    SELECT f.posting_id,
           CASE WHEN m.rn <= 6 THEN 'early'
                WHEN m.rn > m.total_m - 6 THEN 'late' END AS period
    FROM fact_posting f JOIN months m ON m.month = f.month
),
ptot AS (SELECT period, COUNT(DISTINCT posting_id) AS tot
         FROM tagged WHERE period IS NOT NULL GROUP BY period),
sp AS (
    SELECT s.skill_name, t.period, COUNT(*) AS n
    FROM tagged t
    JOIN bridge_posting_skill b ON b.posting_id = t.posting_id
    JOIN dim_skill s ON s.skill_id = b.skill_id
    WHERE t.period IS NOT NULL
    GROUP BY s.skill_name, t.period
)
SELECT skill_name,
       MAX(CASE WHEN period='early' THEN 1.0*n/(SELECT tot FROM ptot WHERE period='early') END) AS early_share,
       MAX(CASE WHEN period='late'  THEN 1.0*n/(SELECT tot FROM ptot WHERE period='late')  END) AS late_share
FROM sp GROUP BY skill_name
ORDER BY (COALESCE(late_share,0) - COALESCE(early_share,0)) DESC;

-- 5. Skill co-occurrence (self-join) -> edge list for the network -------------
SELECT s1.skill_name AS skill_a, s2.skill_name AS skill_b, COUNT(*) AS pair_count
FROM bridge_posting_skill x
JOIN bridge_posting_skill y
     ON x.posting_id = y.posting_id AND x.skill_id < y.skill_id
JOIN dim_skill s1 ON s1.skill_id = x.skill_id
JOIN dim_skill s2 ON s2.skill_id = y.skill_id
GROUP BY s1.skill_name, s2.skill_name
ORDER BY pair_count DESC
LIMIT 50;

-- 6. Remote share by month ---------------------------------------------------
SELECT month,
       1.0 * SUM(remote_flag) / COUNT(*) AS remote_share,
       COUNT(*) AS n_postings
FROM fact_posting
GROUP BY month
ORDER BY month;

-- 7. Seniority mix per skill (>=30 postings) ---------------------------------
SELECT s.skill_name,
       1.0 * SUM(CASE WHEN f.seniority='senior' THEN 1 ELSE 0 END) / COUNT(*) AS senior_share,
       COUNT(*) AS n
FROM fact_posting f
JOIN bridge_posting_skill b ON b.posting_id = f.posting_id
JOIN dim_skill s ON s.skill_id = b.skill_id
GROUP BY s.skill_name
HAVING COUNT(*) >= 30
ORDER BY senior_share DESC;

-- 8. Median salary by skill (PostgreSQL) -------------------------------------
--    SQLite has no PERCENTILE_CONT; use AVG variant below instead.
-- SELECT s.skill_name,
--        PERCENTILE_CONT(0.5) WITHIN GROUP (
--            ORDER BY (f.salary_min + f.salary_max)/2.0) AS median_salary,
--        COUNT(*) AS n
-- FROM fact_posting f
-- JOIN bridge_posting_skill b ON b.posting_id = f.posting_id
-- JOIN dim_skill s ON s.skill_id = b.skill_id
-- WHERE f.salary_min IS NOT NULL
-- GROUP BY s.skill_name HAVING COUNT(*) >= 20
-- ORDER BY median_salary DESC;

-- 8b. Average mid-salary by skill (portable / SQLite) ------------------------
SELECT s.skill_name,
       AVG((f.salary_min + f.salary_max)/2.0) AS avg_salary,
       COUNT(*) AS n
FROM fact_posting f
JOIN bridge_posting_skill b ON b.posting_id = f.posting_id
JOIN dim_skill s ON s.skill_id = b.skill_id
WHERE f.salary_min IS NOT NULL
GROUP BY s.skill_name
HAVING COUNT(*) >= 20
ORDER BY avg_salary DESC;
