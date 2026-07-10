"""
Parse raw HN job postings into structured signals:
  - skills           (via a curated dictionary + word-boundary regex)
  - role_family      (SDE / Data-ML / Analyst / Other)
  - seniority        (junior / mid / senior)
  - remote_flag      (bool)
  - salary_min/max   (USD-ish, best-effort from currency-tagged numbers)

Inputs : data/raw/postings.csv   (from scrape.py)
Outputs: data/clean/postings_parsed.csv   (one row per posting)
         data/clean/posting_skills.csv     (one row per posting-skill: the bridge table)

Usage:  python parse.py
"""
from __future__ import annotations

import csv
import os
import re

RAW = "data/raw/postings.csv"
OUT_POSTINGS = "data/clean/postings_parsed.csv"
OUT_SKILLS = "data/clean/posting_skills.csv"

# --------------------------------------------------------------------------- #
# Skill dictionary: canonical -> (category, [aliases])
# aliases are matched with word boundaries, case-insensitive unless noted.
# --------------------------------------------------------------------------- #
SKILLS = {
    # languages
    "Python": ("language", ["python"]),
    "JavaScript": ("language", ["javascript", "js"]),
    "TypeScript": ("language", ["typescript", "ts"]),
    "Java": ("language", ["java"]),          # note: excludes 'javascript' via boundary+alias order
    "C++": ("language", [r"c\+\+"]),
    "C#": ("language", [r"c#", r"\.net", "dotnet"]),
    "Go": ("language", ["golang", r"\bgo\b"]),
    "Rust": ("language", ["rust"]),
    "Ruby": ("language", ["ruby"]),
    "PHP": ("language", ["php"]),
    "Scala": ("language", ["scala"]),
    "Kotlin": ("language", ["kotlin"]),
    "Swift": ("language", ["swift"]),
    "R": ("language", [r"\br programming\b", "rstats", "rstudio"]),
    "SQL": ("data", ["sql"]),
    # frontend
    "React": ("frontend", ["react", "react.js", "reactjs"]),
    "Vue": ("frontend", ["vue", "vue.js", "vuejs"]),
    "Angular": ("frontend", ["angular"]),
    "Next.js": ("frontend", ["next.js", "nextjs"]),
    "Svelte": ("frontend", ["svelte"]),
    "Tailwind": ("frontend", ["tailwind"]),
    # backend
    "Node.js": ("backend", ["node.js", "nodejs", r"\bnode\b"]),
    "Django": ("backend", ["django"]),
    "Flask": ("backend", ["flask"]),
    "FastAPI": ("backend", ["fastapi"]),
    "Spring": ("backend", ["spring boot", "springboot", r"\bspring\b"]),
    "Rails": ("backend", ["rails", "ruby on rails"]),
    "GraphQL": ("backend", ["graphql"]),
    # data / db
    "PostgreSQL": ("data", ["postgresql", "postgres"]),
    "MySQL": ("data", ["mysql"]),
    "MongoDB": ("data", ["mongodb", "mongo"]),
    "Redis": ("data", ["redis"]),
    "Elasticsearch": ("data", ["elasticsearch", "elastic search"]),
    "Snowflake": ("data", ["snowflake"]),
    "Spark": ("data", ["spark", "pyspark"]),
    "Kafka": ("data", ["kafka"]),
    "Airflow": ("data", ["airflow"]),
    "dbt": ("data", [r"\bdbt\b"]),
    "Pandas": ("data", ["pandas"]),
    # cloud / devops
    "AWS": ("cloud", ["aws", "amazon web services"]),
    "GCP": ("cloud", ["gcp", "google cloud"]),
    "Azure": ("cloud", ["azure"]),
    "Docker": ("cloud", ["docker"]),
    "Kubernetes": ("cloud", ["kubernetes", "k8s"]),
    "Terraform": ("cloud", ["terraform"]),
    "CI/CD": ("cloud", ["ci/cd", "cicd"]),
    "Linux": ("cloud", ["linux"]),
    # ml / ai
    "Machine Learning": ("ml", ["machine learning", r"\bml\b"]),
    "Deep Learning": ("ml", ["deep learning"]),
    "PyTorch": ("ml", ["pytorch"]),
    "TensorFlow": ("ml", ["tensorflow"]),
    "LLM": ("ml", ["llm", "large language model", "gpt", "rag"]),
    "NLP": ("ml", ["nlp", "natural language processing"]),
    "Computer Vision": ("ml", ["computer vision", r"\bcv\b"]),
    "scikit-learn": ("ml", ["scikit-learn", "sklearn"]),
    # mobile
    "iOS": ("mobile", ["ios", "swiftui"]),
    "Android": ("mobile", ["android"]),
    "React Native": ("mobile", ["react native"]),
    "Flutter": ("mobile", ["flutter"]),
    # bi / analytics
    "Tableau": ("bi", ["tableau"]),
    "Power BI": ("bi", ["power bi", "powerbi"]),
    "Looker": ("bi", ["looker"]),
    "Excel": ("bi", ["excel"]),
}


def _compile(aliases):
    pats = []
    for a in aliases:
        # if alias already looks like a regex (has escapes/anchors), use as-is
        if any(ch in a for ch in r"\[](){}+*?^$"):
            pats.append(re.compile(a, re.IGNORECASE))
        else:
            pats.append(re.compile(r"\b" + re.escape(a) + r"\b", re.IGNORECASE))
    return pats


COMPILED = {name: (cat, _compile(al)) for name, (cat, al) in SKILLS.items()}


def extract_skills(text: str):
    found = []
    low = text or ""
    for name, (cat, pats) in COMPILED.items():
        if any(p.search(low) for p in pats):
            found.append((name, cat))
    # de-conflict: 'Java' shouldn't fire from 'javascript'
    names = {n for n, _ in found}
    if "JavaScript" in names and "Java" in names:
        # keep Java only if 'java' appears NOT as part of javascript
        if not re.search(r"\bjava\b(?!script)", low, re.IGNORECASE):
            found = [(n, c) for n, c in found if n != "Java"]
    return found


ROLE_PATTERNS = [
    ("Data-ML", ["machine learning", "ml engineer", "data scientist", "data science",
                 "data engineer", "ai engineer", "mlops", "deep learning", "research scientist"]),
    ("Analyst", ["data analyst", "business analyst", "analytics engineer",
                 "business intelligence", r"\bbi\b"]),
    ("SDE", ["software engineer", "backend", "front end", "frontend", "full stack",
             "full-stack", "developer", r"\bsde\b", r"\bswe\b", "devops", "sre",
             "site reliability", "platform engineer", "mobile engineer"]),
]
ROLE_COMPILED = [(fam, _compile(kw)) for fam, kw in ROLE_PATTERNS]


def role_family(text: str) -> str:
    low = text or ""
    for fam, pats in ROLE_COMPILED:      # order matters: Data-ML/Analyst before SDE
        if any(p.search(low) for p in pats):
            return fam
    return "Other"


SENIOR = _compile(["senior", r"sr\.", "staff", "principal", r"\blead\b", "architect", "head of"])
JUNIOR = _compile(["junior", r"jr\.", "intern", "internship", "new grad", "entry level",
                   "entry-level", "graduate"])


def seniority(text: str) -> str:
    low = text or ""
    if any(p.search(low) for p in SENIOR):
        return "senior"
    if any(p.search(low) for p in JUNIOR):
        return "junior"
    return "mid"


def remote_flag(text: str) -> int:
    low = (text or "").lower()
    if "remote" not in low:
        return 0
    if any(neg in low for neg in ("no remote", "not remote", "onsite only", "on-site only")):
        return 0
    return 1


_MONEY = re.compile(r"[$€£₹]\s?(\d{2,3})(,\d{3})?\s?([kK])?")


def salary(text: str):
    """Best-effort: collect currency-tagged figures, return (min,max) in plausible range."""
    vals = []
    for m in _MONEY.finditer(text or ""):
        num = int(m.group(1) + (m.group(2) or "").replace(",", ""))
        if m.group(3):            # 'k'
            num *= 1000
        elif num < 1000:          # bare 2-3 digit with currency but no k -> assume k (e.g. $120)
            num *= 1000
        vals.append(num)
    vals = [v for v in vals if 20_000 <= v <= 1_000_000]   # plausible annual salary band
    if not vals:
        return ("", "")
    return (min(vals), max(vals))


def main():
    os.makedirs("data/clean", exist_ok=True)
    with open(RAW, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"Loaded {len(rows)} raw postings")

    post_cols = ["posting_id", "thread_month", "role_family", "seniority",
                 "remote_flag", "salary_min", "salary_max", "n_skills"]
    skill_rows = []
    with open(OUT_POSTINGS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=post_cols)
        w.writeheader()
        for r in rows:
            text = r.get("text_clean") or ""
            skills = extract_skills(text)
            smin, smax = salary(text)
            w.writerow({
                "posting_id": r["posting_id"],
                "thread_month": r["thread_month"],
                "role_family": role_family(text),
                "seniority": seniority(text),
                "remote_flag": remote_flag(text),
                "salary_min": smin, "salary_max": smax,
                "n_skills": len(skills),
            })
            for name, cat in skills:
                skill_rows.append({"posting_id": r["posting_id"],
                                   "skill_name": name, "skill_category": cat})

    with open(OUT_SKILLS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["posting_id", "skill_name", "skill_category"])
        w.writeheader()
        w.writerows(skill_rows)

    print(f"Wrote {OUT_POSTINGS} and {OUT_SKILLS} ({len(skill_rows)} posting-skill rows)")

    # --- quick sanity summary ---
    from collections import Counter
    sk = Counter(r["skill_name"] for r in skill_rows)
    print("\nTop 15 skills:")
    for name, n in sk.most_common(15):
        print(f"   {name:<16} {n}")
    with open(OUT_POSTINGS, encoding="utf-8") as f:
        import csv as _csv
        pr = list(_csv.DictReader(f))
    print("\nRole family:", dict(Counter(r["role_family"] for r in pr)))
    print("Seniority:  ", dict(Counter(r["seniority"] for r in pr)))
    remote = sum(1 for r in pr if r["remote_flag"] == "1")
    print(f"Remote:      {remote}/{len(pr)} ({remote/len(pr):.0%})")
    withsal = sum(1 for r in pr if r["salary_min"])
    print(f"Salary present: {withsal}/{len(pr)} ({withsal/len(pr):.0%})")


if __name__ == "__main__":
    main()
