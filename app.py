"""
AI-Native CRM — demo
Streamlit + SQLite. Works with no API key (rule-based fallback);
add ANTHROPIC_API_KEY in Streamlit secrets to switch on Claude.
"""
import json
import os
import random
import re
import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

DB = "crm_demo.db"
STAGES = ["New", "Contacted", "Proposal", "Negotiation", "Won", "Lost"]
OPEN_STAGES = STAGES[:4]
OWNERS = ["Priya", "Rahul", "Sneha"]
TEAL, SAFFRON, INK = "#1F6F78", "#E9A23B", "#14213D"
MODEL = "claude-haiku-5-5"

st.set_page_config(page_title="AI CRM Demo", page_icon="📇", layout="wide")

st.markdown(
    f"""
<style>
  h1, h2, h3 {{ letter-spacing: -0.01em; }}
  div[data-testid="stMetric"] {{
      background: #fff; border: 1px solid #DDE3E8; border-left: 4px solid {TEAL};
      padding: 14px 16px; border-radius: 6px;
  }}
  .pill {{ display:inline-block; padding:2px 9px; border-radius:10px; font-size:12px;
           background:#E6F0F1; color:{TEAL}; margin-right:6px; }}
  .pill.hot {{ background:#FCEBCB; color:#8A5A00; }}
  .muted {{ color:#5B6775; font-size:13px; }}
</style>
""",
    unsafe_allow_html=True,
)


# ───────────────────────── database ─────────────────────────
def con():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def q(sql, params=()):
    with con() as c:
        return pd.read_sql_query(sql, c, params=params)


def ex(sql, params=()):
    with con() as c:
        cur = c.execute(sql, params)
        c.commit()
        return cur.lastrowid


def init_db():
    with con() as c:
        c.executescript(
            """
        CREATE TABLE IF NOT EXISTS contacts(
            id INTEGER PRIMARY KEY, name TEXT, company TEXT, industry TEXT,
            email TEXT, phone TEXT, source TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS deals(
            id INTEGER PRIMARY KEY, contact_id INTEGER, title TEXT, stage TEXT,
            value INTEGER, owner TEXT, score INTEGER, created TEXT, updated TEXT);
        CREATE TABLE IF NOT EXISTS activities(
            id INTEGER PRIMARY KEY, contact_id INTEGER, deal_id INTEGER,
            type TEXT, note TEXT, created TEXT);
        """
        )
        if c.execute("SELECT COUNT(*) FROM contacts").fetchone()[0] == 0:
            seed(c)


def seed(c):
    random.seed(7)
    now = datetime.now()
    people = [
        ("Aarav Mehta", "Mehta Textiles", "Textiles", "Website", "Bulk order tracking CRM", 650000, "Negotiation"),
        ("Neha Kulkarni", "CityCare Clinic", "Healthcare", "WhatsApp", "Patient appointment system", 400000, "Proposal"),
        ("Rohit Sinha", "Brightpath Coaching", "Education", "Meta Ads", "Fee tracking + reminders", 250000, "Contacted"),
        ("Farah Khan", "Khan Realty", "Real Estate", "Referral", "Property lead matching", 900000, "Proposal"),
        ("Vikram Rao", "Rao Logistics", "Logistics", "Website", "Fleet + client CRM", 1200000, "Won"),
        ("Ananya Das", "Das Travel Co.", "Travel", "Meta Ads", "Itinerary + enquiry CRM", 180000, "New"),
        ("Sanjay Gupta", "Gupta Finserv", "Finance", "LinkedIn", "Loan lead pipeline", 750000, "Negotiation"),
        ("Meera Iyer", "Iyer Dental", "Healthcare", "WhatsApp", "Recall + reminders", 120000, "Won"),
        ("Karan Malhotra", "Malhotra Motors", "Automobile", "Website", "Test-drive lead capture", 500000, "Lost"),
        ("Divya Nair", "Nair Academy", "Education", "Referral", "Admissions CRM", 300000, "Contacted"),
        ("Imran Sheikh", "Sheikh Exports", "Export", "LinkedIn", "Quotation + follow-ups", 450000, "New"),
        ("Pooja Verma", "Verma Interiors", "Design", "Meta Ads", "Project lead tracker", 220000, "Proposal"),
    ]
    types = ["Call", "Email", "Meeting", "WhatsApp", "Note"]
    notes = [
        "Discussed requirements and current Excel workflow.",
        "Shared demo link; asked about WhatsApp integration.",
        "Concerned about data privacy and hosting location.",
        "Wants a quote with onboarding and training included.",
        "Follow-up: waiting on internal approval from partner.",
        "Asked for reference customers in the same industry.",
    ]
    for i, (n, co, ind, src, title, val, stage) in enumerate(people, start=1):
        created = now - timedelta(days=random.randint(6, 45))
        c.execute(
            "INSERT INTO contacts VALUES(?,?,?,?,?,?,?,?)",
            (i, n, co, ind, f"{n.split()[0].lower()}@{co.split()[0].lower()}.in",
             f"+91 98{random.randint(10000000, 99999999)}", src, created.isoformat()),
        )
        score = {"New": 45, "Contacted": 55, "Proposal": 70, "Negotiation": 82, "Won": 95, "Lost": 20}[stage] + random.randint(-6, 6)
        c.execute(
            "INSERT INTO deals VALUES(?,?,?,?,?,?,?,?,?)",
            (i, i, title, stage, val, random.choice(OWNERS), score, created.isoformat(), now.isoformat()),
        )
        for _ in range(random.randint(2, 4)):
            when = created + timedelta(days=random.randint(0, 5), hours=random.randint(0, 9))
            when = min(when, now - timedelta(days=random.choice([0, 1, 2, 9, 12])))
            c.execute(
                "INSERT INTO activities(contact_id,deal_id,type,note,created) VALUES(?,?,?,?,?)",
                (i, i, random.choice(types), random.choice(notes), when.isoformat()),
            )
    c.commit()


def log(contact_id, deal_id, kind, note):
    ex(
        "INSERT INTO activities(contact_id,deal_id,type,note,created) VALUES(?,?,?,?,?)",
        (contact_id, deal_id, kind, note, datetime.now().isoformat()),
    )


def inr(v):
    v = float(v or 0)
    if v >= 1e7:
        return f"₹{v / 1e7:.2f} Cr"
    if v >= 1e5:
        return f"₹{v / 1e5:.1f} L"
    return f"₹{v:,.0f}"


# ───────────────────────── AI layer ─────────────────────────
def get_key():
    try:
        return st.secrets.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    except Exception:
        return os.getenv("ANTHROPIC_API_KEY")


def llm(system, user, max_tokens=700):
    key = get_key()
    if not key:
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key)
        r = client.messages.create(
            model=MODEL, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in r.content if b.type == "text")
    except Exception as e:  # keep the demo alive on any API failure
        st.warning(f"AI call failed, using fallback: {e}")
        return None


QUALIFY_SYSTEM = """You qualify inbound sales leads for a software agency. Return ONLY JSON with keys:
name, company, industry, need, budget_inr (integer or null), timeline_days (integer or null),
urgency ("low"|"medium"|"high"), score (0-100), reasoning (one sentence),
next_action (one sentence), suggested_reply (a short friendly WhatsApp reply asking the single most useful next question)."""


def heuristic_qualify(msg):
    text = msg.lower()
    budget = None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(lakh|lac|l\b|cr|crore|k\b)", text)
    if m:
        n, unit = float(m.group(1)), m.group(2)
        budget = int(n * {"lakh": 1e5, "lac": 1e5, "l": 1e5, "cr": 1e7, "crore": 1e7, "k": 1e3}[unit])
    days = None
    m = re.search(r"(\d+)\s*(day|week|month)", text)
    if m:
        days = int(m.group(1)) * {"day": 1, "week": 7, "month": 30}[m.group(2)]
    urgent = any(w in text for w in ["urgent", "asap", "immediately", "this week", "within"])
    urgency = "high" if urgent or (days and days <= 30) else ("medium" if days else "low")
    score = 25 + (25 if budget else 0) + (15 if budget and budget >= 300000 else 0)
    score += {"high": 25, "medium": 12, "low": 0}[urgency] + (10 if len(msg) > 80 else 0)
    nm = re.search(r"(?:[-–—]\s*|i am |this is |my name is )([A-Z][a-z]+(?: [A-Z][a-z]+)*)", msg)
    return {
        "name": nm.group(1) if nm else "Unknown",
        "company": "", "industry": "", "need": msg[:90],
        "budget_inr": budget, "timeline_days": days, "urgency": urgency,
        "score": min(score, 100),
        "reasoning": "Rule-based score from budget, timeline and message detail (add an API key for Claude).",
        "next_action": "Call within 1 hour" if score >= 70 else "Send qualifying questions",
        "suggested_reply": "Thanks for reaching out! Could you share your approximate budget and when you'd like to go live?",
    }


def qualify(msg):
    out = llm(QUALIFY_SYSTEM, msg)
    if out:
        try:
            return json.loads(re.sub(r"^```(?:json)?|```$", "", out.strip(), flags=re.M).strip()), "Claude"
        except Exception:
            pass
    return heuristic_qualify(msg), "Rule-based"


def precall_brief(contact, deals, acts):
    ctx = (
        f"Contact: {contact['name']} ({contact['company']}, {contact['industry']}), source {contact['source']}\n"
        f"Deals: {deals.to_dict('records')}\nActivities (latest first): {acts.head(8).to_dict('records')}"
    )
    out = llm(
        "You prepare sales reps for calls. Write a brief with: Summary (2 lines), Open concerns, "
        "Suggested talking points (3 bullets), Next best action. Be concrete and short.",
        ctx, 500,
    )
    if out:
        return out, "Claude"
    last = acts.iloc[0] if len(acts) else None
    d = deals.iloc[0] if len(deals) else None
    txt = f"**Summary:** {contact['name']} from {contact['company']} is in *{d['stage'] if d is not None else 'n/a'}* "
    txt += f"on '{d['title'] if d is not None else ''}' worth {inr(d['value']) if d is not None else '—'}.\n\n"
    if last is not None:
        txt += f"**Last touch:** {last['type']} — {last['note']}\n\n"
    txt += "**Next best action:** Confirm decision timeline and send a short recap email.\n\n*(Template brief — add an API key for AI-written briefs.)*"
    return txt, "Template"


# ───────────────────────── pages ─────────────────────────
def page_dashboard():
    st.title("Dashboard")
    deals = q("SELECT d.*, c.name, c.company, c.source FROM deals d JOIN contacts c ON c.id=d.contact_id")
    open_d = deals[deals.stage.isin(OPEN_STAGES)]
    won, lost = deals[deals.stage == "Won"], deals[deals.stage == "Lost"]
    conv = len(won) / max(len(won) + len(lost), 1)

    k = st.columns(4)
    k[0].metric("Open pipeline", inr(open_d.value.sum()), f"{len(open_d)} deals")
    k[1].metric("Won revenue", inr(won.value.sum()), f"{len(won)} deals")
    k[2].metric("Win rate", f"{conv:.0%}")
    k[3].metric("Avg. lead score", f"{deals.score.mean():.0f}")

    c1, c2 = st.columns(2)
    f = deals.groupby("stage").value.sum().reindex(STAGES).fillna(0).reset_index()
    fig = px.bar(f, x="stage", y="value", color_discrete_sequence=[TEAL], title="Value by stage")
    fig.update_layout(height=320, margin=dict(l=0, r=0, t=40, b=0), yaxis_title=None, xaxis_title=None)
    c1.plotly_chart(fig, width="stretch")
    s = deals.groupby("source").agg(deals=("id", "count"), value=("value", "sum")).reset_index()
    fig2 = px.pie(s, names="source", values="deals", hole=0.55, title="Leads by source",
                  color_discrete_sequence=[TEAL, SAFFRON, INK, "#7FB3B8", "#C9CED6"])
    fig2.update_layout(height=320, margin=dict(l=0, r=0, t=40, b=0))
    c2.plotly_chart(fig2, width="stretch")

    st.subheader("Needs attention")
    last = q("SELECT deal_id, MAX(created) last FROM activities GROUP BY deal_id")
    m = open_d.merge(last, left_on="id", right_on="deal_id", how="left")
    m["days_quiet"] = (datetime.now() - pd.to_datetime(m["last"])).dt.days
    quiet = m[m.days_quiet >= 7].sort_values("value", ascending=False)
    if quiet.empty:
        st.success("Every open deal has had contact in the last week.")
    else:
        t = quiet[["name", "company", "title", "stage", "value", "days_quiet", "owner"]].copy()
        t["value"] = t["value"].map(inr)
        t.columns = ["Contact", "Company", "Deal", "Stage", "Value", "Days quiet", "Owner"]
        st.dataframe(t, hide_index=True, width="stretch")


def move_deal(deal_id, contact_id, step):
    row = q("SELECT stage FROM deals WHERE id=?", (deal_id,)).iloc[0]
    new = STAGES[max(0, min(len(STAGES) - 1, STAGES.index(row.stage) + step))]
    ex("UPDATE deals SET stage=?, updated=? WHERE id=?", (new, datetime.now().isoformat(), deal_id))
    log(contact_id, deal_id, "Note", f"Stage moved: {row.stage} → {new}")


def page_pipeline():
    st.title("Pipeline")
    owner = st.selectbox("Owner", ["All"] + OWNERS, label_visibility="collapsed")
    deals = q("SELECT d.*, c.name, c.company FROM deals d JOIN contacts c ON c.id=d.contact_id")
    if owner != "All":
        deals = deals[deals.owner == owner]
    cols = st.columns(len(STAGES))
    for col, stage in zip(cols, STAGES):
        sub = deals[deals.stage == stage]
        col.markdown(f"**{stage}**  \n<span class='muted'>{len(sub)} · {inr(sub.value.sum())}</span>", unsafe_allow_html=True)
        for _, d in sub.sort_values("value", ascending=False).iterrows():
            with col.container(border=True):
                st.markdown(f"**{d['company']}**")
                st.markdown(f"<span class='muted'>{d['title']}</span>", unsafe_allow_html=True)
                hot = "hot" if d["score"] >= 75 else ""
                st.markdown(f"<span class='pill {hot}'>{inr(d['value'])}</span><span class='pill'>score {d['score']}</span>", unsafe_allow_html=True)
                b1, b2 = st.columns(2)
                b1.button("◀", key=f"l{d['id']}", on_click=move_deal, args=(d["id"], d["contact_id"], -1), disabled=stage == STAGES[0], width="stretch")
                b2.button("▶", key=f"r{d['id']}", on_click=move_deal, args=(d["id"], d["contact_id"], 1), disabled=stage == STAGES[-1], width="stretch")


def page_contacts():
    st.title("Contacts")
    df = q("SELECT * FROM contacts ORDER BY created DESC")
    search = st.text_input("Search", placeholder="Name, company or industry", label_visibility="collapsed")
    if search:
        mask = df[["name", "company", "industry"]].apply(lambda s: s.str.contains(search, case=False)).any(axis=1)
        df = df[mask]
    if df.empty:
        st.info("No contacts match. Clear the search or add a lead from Lead inbox.")
        return
    left, right = st.columns([1, 2])
    pick = left.radio("Contacts", df.id.tolist(), format_func=lambda i: f"{df.set_index('id').loc[i, 'name']} — {df.set_index('id').loc[i, 'company']}", label_visibility="collapsed")
    c = df[df.id == pick].iloc[0]
    deals = q("SELECT * FROM deals WHERE contact_id=?", (int(pick),))
    acts = q("SELECT * FROM activities WHERE contact_id=? ORDER BY created DESC", (int(pick),))
    with right:
        st.subheader(c["name"])
        st.markdown(f"{c['company']} · {c['industry']}  \n{c['email']} · {c['phone']}  \nSource: {c['source']}")
        for _, d in deals.iterrows():
            st.markdown(f"<span class='pill'>{d['stage']}</span><span class='pill'>{inr(d['value'])}</span><span class='pill'>score {d['score']}</span> {d['title']}", unsafe_allow_html=True)

        if st.button("Generate pre-call brief"):
            with st.spinner("Reading history…"):
                text, src = precall_brief(c, deals, acts)
            st.info(text)
            st.caption(f"Generated by: {src}")

        st.markdown("##### Add activity")
        with st.form(f"act{pick}", clear_on_submit=True):
            a, b = st.columns([1, 3])
            kind = a.selectbox("Type", ["Call", "Email", "Meeting", "WhatsApp", "Note"])
            note = b.text_input("Note")
            if st.form_submit_button("Save activity") and note:
                log(int(pick), int(deals.iloc[0]["id"]) if len(deals) else None, kind, note)
                st.rerun()

        st.markdown("##### Timeline")
        for _, a in acts.iterrows():
            st.markdown(f"**{a['type']}** · <span class='muted'>{pd.to_datetime(a['created']):%d %b, %H:%M}</span>  \n{a['note']}", unsafe_allow_html=True)


SAMPLES = {
    "Clinic owner, hot lead": "Hi, I run a 40-bed clinic in Pune. Looking for a patient appointment system, budget around 4 lakh. Need it live within 3 weeks. - Neha Kulkarni",
    "Vague enquiry": "hello just checking prices, no idea yet",
    "Coaching institute": "We are a coaching institute in Patna with 800 students, want fee tracking and WhatsApp reminders. Budget 2.5L, can start next month. - Rohit Sinha",
}


def page_inbox():
    st.title("Lead inbox")
    st.caption("Simulates a WhatsApp or web-form message arriving. In production a webhook delivers it here.")
    choice = st.selectbox("Sample message", list(SAMPLES) + ["Write my own"])
    msg = st.text_area("Incoming message", SAMPLES.get(choice, ""), height=110)
    if st.button("Qualify lead", type="primary") and msg.strip():
        with st.spinner("Qualifying…"):
            result, source = qualify(msg)
        st.session_state.update(lead=result, lead_src=source, lead_msg=msg)
    lead = st.session_state.get("lead")
    if not lead:
        return
    st.divider()
    st.caption(f"Scored by: {st.session_state['lead_src']}")
    a, b, c = st.columns(3)
    a.metric("Lead score", lead.get("score", 0))
    b.metric("Budget", inr(lead["budget_inr"]) if lead.get("budget_inr") else "Not stated")
    c.metric("Urgency", str(lead.get("urgency", "—")).title())
    st.markdown(f"**Name:** {lead.get('name') or '—'}  \n**Need:** {lead.get('need') or '—'}  \n**Why this score:** {lead.get('reasoning', '')}  \n**Next action:** {lead.get('next_action', '')}")
    st.text_area("Suggested reply (review before sending)", lead.get("suggested_reply", ""), height=80)
    if st.button("Save to CRM"):
        now = datetime.now().isoformat()
        cid = ex(
            "INSERT INTO contacts(name,company,industry,email,phone,source,created) VALUES(?,?,?,?,?,?,?)",
            (lead.get("name") or "Unknown", lead.get("company") or "", lead.get("industry") or "", "", "", "WhatsApp", now),
        )
        did = ex(
            "INSERT INTO deals(contact_id,title,stage,value,owner,score,created,updated) VALUES(?,?,?,?,?,?,?,?)",
            (cid, (lead.get("need") or "New enquiry")[:60], "New", lead.get("budget_inr") or 0, random.choice(OWNERS), int(lead.get("score", 0)), now, now),
        )
        log(cid, did, "WhatsApp", st.session_state["lead_msg"])
        st.success("Saved. Open Pipeline to see the new deal in the New column.")
        st.session_state.pop("lead")


# ───────────────────────── shell ─────────────────────────
init_db()
with st.sidebar:
    st.markdown("### AI CRM demo")
    page = st.radio("Go to", ["Dashboard", "Pipeline", "Contacts", "Lead inbox"], label_visibility="collapsed")
    st.divider()
    st.caption("AI mode: " + ("Claude" if get_key() else "rule-based (no API key)"))
    if st.button("Reset demo data"):
        if os.path.exists(DB):
            os.remove(DB)
        st.session_state.clear()
        st.rerun()

{"Dashboard": page_dashboard, "Pipeline": page_pipeline, "Contacts": page_contacts, "Lead inbox": page_inbox}[page]()
