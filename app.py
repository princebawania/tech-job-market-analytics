"""
Streamlit dashboard for the tech job-market analysis.

Reads the exported marts in data/marts/ (no database needed) and renders three
views: Market Overview, Skill Intelligence, and What Signals Seniority.

Run locally:   streamlit run app.py
Deploy free:   push to GitHub -> share.streamlit.io -> point it at app.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

MARTS = Path("data/marts")

st.set_page_config(page_title="Tech Job Market Analysis", layout="wide")


# --------------------------------------------------------------------------- #
# data loading + pure transforms (unit-tested separately)
# --------------------------------------------------------------------------- #
@st.cache_data
def load(name: str):
    p = MARTS / f"{name}.csv"
    return pd.read_csv(p) if p.exists() else None


def prep_rising(df: pd.DataFrame, n: int = 12) -> pd.DataFrame:
    d = df.copy()
    d["early_share"] = d["early_share"].fillna(0)
    d["late_share"] = d["late_share"].fillna(0)
    d["delta"] = d["late_share"] - d["early_share"]
    d = d.sort_values("delta", ascending=False)
    return pd.concat([d.head(n), d.tail(n)]).drop_duplicates("skill_name")


def prep_odds(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["feature"].astype(str).str.startswith("skill::")].copy()
    d["skill"] = d["feature"].str.replace("skill::", "", regex=False)
    return d.sort_values("odds_ratio", ascending=False)


def cooccur_matrix(df: pd.DataFrame, top: int = 15) -> pd.DataFrame:
    skills = (pd.concat([df["skill_a"], df["skill_b"]])
              .value_counts().head(top).index.tolist())
    d = df[df["skill_a"].isin(skills) & df["skill_b"].isin(skills)]
    m = d.pivot_table(index="skill_a", columns="skill_b",
                      values="pair_count", aggfunc="sum", fill_value=0)
    return m


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
st.title("What the Tech Job Market Actually Rewards")
st.caption("Source: HackerNews 'Who is hiring?' monthly threads · self-scraped · "
           "seniority/role inferred from text (associational, not causal).")

top_skills = load("top_skills")
if top_skills is None:
    st.error("No marts found. Run `python run_analysis.py` and `python model.py` first.")
    st.stop()

tab1, tab2, tab3 = st.tabs(["Market Overview", "Skill Intelligence",
                            "What Signals Seniority"])

# ---- Tab 1 ----
with tab1:
    remote = load("remote_by_month")
    c1, c2, c3 = st.columns(3)
    c1.metric("Skills tracked", int(top_skills.shape[0]))
    c2.metric("Top skill", f"{top_skills.iloc[0]['skill_name']}")
    if remote is not None:
        c3.metric("Latest remote share", f"{remote.iloc[-1]['remote_share']:.0%}",
                  f"{(remote.iloc[-1]['remote_share']-remote.iloc[0]['remote_share'])*100:+.0f} pts")

    st.subheader("Most in-demand skills")
    fig = px.bar(top_skills.head(20), x="n_postings", y="skill_name",
                 orientation="h", color="skill_category")
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=520)
    st.plotly_chart(fig, use_container_width=True)

    md = load("monthly_demand")
    if md is not None:
        st.subheader("Skill demand over time")
        defaults = top_skills.head(6)["skill_name"].tolist()
        picks = st.multiselect("Skills", sorted(md["skill_name"].unique()), defaults)
        sub = md[md["skill_name"].isin(picks)]
        st.plotly_chart(px.line(sub, x="month", y="n", color="skill_name"),
                        use_container_width=True)

    if remote is not None:
        st.subheader("Remote share over time")
        st.plotly_chart(px.line(remote, x="month", y="remote_share").update_yaxes(tickformat=".0%"),
                        use_container_width=True)

    fc = load("forecast_demand")
    if fc is not None:
        st.subheader("Demand forecast — next 6 months (dashed = forecast)")
        opts = sorted(fc["skill_name"].unique())
        defaults = [x for x in top_skills.head(4)["skill_name"].tolist() if x in opts]
        fpick = st.multiselect("Forecast skills", opts, defaults, key="fc")
        sub = fc[fc["skill_name"].isin(fpick)]
        st.plotly_chart(
            px.line(sub, x="month", y="share", color="skill_name", line_dash="kind")
            .update_yaxes(tickformat=".1%"),
            use_container_width=True)

# ---- Tab 2 ----
with tab2:
    rising = load("rising_skills")
    if rising is not None:
        st.subheader("Fastest rising & declining skills")
        r = prep_rising(rising)
        fig = px.bar(r, x="delta", y="skill_name", orientation="h",
                     color=r["delta"] > 0, color_discrete_map={True: "#2a9d8f", False: "#e76f51"})
        fig.update_layout(yaxis={"categoryorder": "total ascending"},
                          showlegend=False, height=520)
        fig.update_xaxes(tickformat=".1%")
        st.plotly_chart(fig, use_container_width=True)

    co = load("cooccurrence")
    if co is not None:
        st.subheader("Skill co-occurrence (which skills travel together)")
        m = cooccur_matrix(co)
        st.plotly_chart(px.imshow(m, aspect="auto", color_continuous_scale="Blues"),
                        use_container_width=True)

    sen = load("seniority_by_skill")
    if sen is not None:
        st.subheader("Share of postings that are senior, by skill")
        s = sen.sort_values("senior_share", ascending=False).head(20)
        st.plotly_chart(px.bar(s, x="senior_share", y="skill_name", orientation="h")
                        .update_layout(yaxis={"categoryorder": "total ascending"}, height=520)
                        .update_xaxes(tickformat=".0%"), use_container_width=True)

# ---- Tab 3 ----
with tab3:
    odds = load("skill_seniority_odds")
    if odds is not None:
        st.subheader("Which skills raise the odds of a SENIOR role")
        st.caption("Odds ratio > 1 = associated with more senior postings. Reference line at 1.")
        d = prep_odds(odds)
        show = pd.concat([d.head(10), d.tail(8)])
        fig = px.bar(show, x="odds_ratio", y="skill", orientation="h")
        fig.add_vline(x=1.0, line_dash="dash", line_color="gray")
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=560)
        st.plotly_chart(fig, use_container_width=True)

    sal = load("skill_salary_premium")
    if sal is not None:
        st.subheader("Salary premium by skill (where disclosed)")
        d = sal[sal["feature"].astype(str).str.startswith("skill::")].copy()
        d["skill"] = d["feature"].str.replace("skill::", "", regex=False)
        d = d.sort_values("pct_premium", ascending=False).head(12)
        st.plotly_chart(px.bar(d, x="pct_premium", y="skill", orientation="h")
                        .update_layout(yaxis={"categoryorder": "total ascending"})
                        .update_xaxes(tickformat=".0%"), use_container_width=True)

    st.info("Method & limits: HackerNews skews startup/remote/global; seniority is "
            "keyword-inferred (so results are associational); salary disclosed in ~26% of posts.")
