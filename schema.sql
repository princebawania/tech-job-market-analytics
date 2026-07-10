-- Star-style schema for the tech job-market warehouse.
-- Works on SQLite (3.25+) and PostgreSQL.

CREATE TABLE IF NOT EXISTS dim_month (
    month       TEXT PRIMARY KEY,      -- 'YYYY-MM'
    year        INTEGER,
    month_num   INTEGER
);

CREATE TABLE IF NOT EXISTS fact_posting (
    posting_id  TEXT PRIMARY KEY,
    month       TEXT REFERENCES dim_month(month),
    role_family TEXT,                  -- SDE / Data-ML / Analyst / Other
    seniority   TEXT,                  -- junior / mid / senior
    remote_flag INTEGER,              -- 0/1
    salary_min  INTEGER,
    salary_max  INTEGER,
    n_skills    INTEGER
);

CREATE TABLE IF NOT EXISTS dim_skill (
    skill_id       INTEGER PRIMARY KEY,
    skill_name     TEXT UNIQUE,
    skill_category TEXT
);

CREATE TABLE IF NOT EXISTS bridge_posting_skill (
    posting_id TEXT REFERENCES fact_posting(posting_id),
    skill_id   INTEGER REFERENCES dim_skill(skill_id),
    PRIMARY KEY (posting_id, skill_id)
);

CREATE INDEX IF NOT EXISTS idx_bps_skill ON bridge_posting_skill(skill_id);
CREATE INDEX IF NOT EXISTS idx_fact_month ON fact_posting(month);
