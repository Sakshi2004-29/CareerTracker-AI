"""CareerTrack AI - Streamlit frontend.

This app NEVER talks to Supabase or Gemini directly. It only calls the FastAPI
backend, so no database or AI secrets ever exist on the frontend.

Run locally (inside the frontend folder):  streamlit run app.py
"""
import os
from datetime import date
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Configuration (Streamlit secrets on Cloud, environment variables locally)
# ---------------------------------------------------------------------------
STATUSES = ["Saved", "Applied", "Assessment", "Interview", "Offer", "Rejected", "Withdrawn"]
STATUS_ICON = {"Saved": "🔖", "Applied": "📤", "Assessment": "📝", "Interview": "🎤",
               "Offer": "🎉", "Rejected": "❌", "Withdrawn": "↩️"}
REQUEST_TIMEOUT = 90  # seconds; free Render servers need ~50 s to wake up


def get_config(name: str, default: str = "") -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # no secrets.toml file -> fall back to environment variables
        pass
    return os.getenv(name, default)


BACKEND_URL = get_config("BACKEND_URL", "http://localhost:8000").rstrip("/")
BACKEND_API_KEY = get_config("BACKEND_API_KEY", "")

st.set_page_config(page_title="CareerTrack AI", page_icon="🧭", layout="wide")

# ---------------------------------------------------------------------------
# UI theme — polished JobTrakr-inspired layout
# ---------------------------------------------------------------------------
st.markdown("""
<style>
:root { --ct-ink:#17233c; --ct-blue:#3266d5; --ct-muted:#68758a; }
.stApp { background:#f7f9fc; color:var(--ct-ink); }
.block-container { padding-top:1.45rem; padding-bottom:2.5rem; max-width:1500px; }
[data-testid="stSidebar"] { background:#ffffff; border-right:1px solid #e6eaf1; }
[data-testid="stSidebar"] > div:first-child { padding-top:1.25rem; }
[data-testid="stSidebar"] h1 { color:#2f6edb; font-size:1.35rem; letter-spacing:-.03em; }
[data-testid="stSidebar"] [data-testid="stRadio"] label { border-radius:10px; padding:.35rem .45rem; }
h1,h2,h3 { color:#17233c; letter-spacing:-.025em; }
h1 { font-size:2rem !important; }
h2 { font-size:1.55rem !important; }
h3 { font-size:1.18rem !important; }
p, label, .stCaption { color:#5e6b80; }
div[data-testid="stMetric"] { background:#fff; border:1px solid #e7ebf2; padding:18px 20px; border-radius:16px; box-shadow:0 3px 12px rgba(25,42,70,.035); }
div[data-testid="stMetricLabel"] { color:#66748a; font-weight:600; }
div[data-testid="stMetricValue"] { color:#17233c; font-weight:750; }
.stButton > button, .stFormSubmitButton > button { border-radius:10px; min-height:2.6rem; font-weight:600; border:1px solid #dce4f0; }
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] { background:#2e4f91; border-color:#2e4f91; }
.stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"], .stDateInput input { border-radius:10px; }
div[data-testid="stExpander"] { background:#fff; border:1px solid #e6ebf3; border-radius:12px; }
div[data-testid="stTabs"] button { font-weight:600; }
.ct-intro { background:linear-gradient(115deg,#edf4ff 0%,#f5f2ff 100%); border:1px solid #e1e9fb; padding:20px 24px; border-radius:18px; margin:0 0 20px 0; }
.ct-intro h3 { margin:0 0 5px 0; font-size:1.25rem; }
.ct-intro p { margin:0; color:#66748a; }
.ct-job-card { min-height:220px; padding:18px; border:1px solid rgba(40,60,100,.08); border-radius:16px; box-shadow:0 5px 16px rgba(24,42,75,.045); margin-bottom:14px; color:#18243a; }
.ct-job-card .ct-date { color:#56657b; font-size:.82rem; margin-bottom:14px; }
.ct-job-card .ct-company { font-size:.88rem; margin-bottom:4px; color:#4d5c72; }
.ct-job-card .ct-role { font-size:1.05rem; font-weight:750; line-height:1.35; margin-bottom:13px; color:#17233c; }
.ct-tags { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px; }
.ct-tag { display:inline-block; padding:4px 9px; background:rgba(255,255,255,.78); border:1px solid rgba(40,60,100,.06); border-radius:999px; color:#34445d; font-size:.74rem; }
.ct-card-foot { color:#34445d; font-size:.83rem; border-top:1px solid rgba(40,60,100,.08); padding-top:10px; }
@media (max-width: 800px) {
  .block-container { padding-left:1rem; padding-right:1rem; }
  .ct-job-card { min-height:190px; }
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Backend client
# ---------------------------------------------------------------------------
class ApiError(Exception):
    """A readable error message coming from the backend or the network."""


def api(method: str, path: str, params: Optional[Dict[str, Any]] = None, body: Optional[Dict[str, Any]] = None) -> Any:
    headers = {"X-API-Key": BACKEND_API_KEY} if BACKEND_API_KEY else {}
    access_token = st.session_state.get("access_token")
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    clean_params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
    try:
        resp = requests.request(method, f"{BACKEND_URL}{path}", params=clean_params,
                                json=body, headers=headers, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.ConnectionError:
        raise ApiError(f"Cannot reach the backend at {BACKEND_URL}. Is it running? "
                       "(On Render's free plan the first request after a pause can take ~50 seconds.)")
    except requests.exceptions.Timeout:
        raise ApiError("The backend took too long to answer. Please try again.")
    if resp.status_code == 204:
        return None
    if not resp.ok:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text[:200] or f"HTTP {resp.status_code}"
        raise ApiError(str(detail))
    return resp.json()



def upload_file(path: str, uploaded_file) -> Any:
    """Upload a Streamlit file through the authenticated backend."""
    headers = {"X-API-Key": BACKEND_API_KEY} if BACKEND_API_KEY else {}
    access_token = st.session_state.get("access_token")
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    try:
        resp = requests.post(
            f"{BACKEND_URL}{path}",
            files={"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")},
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.ConnectionError:
        raise ApiError(f"Cannot reach the backend at {BACKEND_URL}. Is it running?")
    except requests.exceptions.Timeout:
        raise ApiError("The backend took too long to answer. Please try again.")
    if not resp.ok:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text[:200] or f"HTTP {resp.status_code}"
        raise ApiError(str(detail))
    return resp.json()


def load(path: str, params: Optional[Dict[str, Any]] = None, default: Any = None) -> Any:
    """GET helper that shows a friendly error instead of crashing the page."""
    try:
        return api("GET", path, params)
    except ApiError as err:
        st.error(f"⚠️ {err}")
        return default


def flash(message: str, kind: str = "success") -> None:
    """Remember a message so it survives st.rerun()."""
    st.session_state["flash"] = (kind, message)


def show_flash() -> None:
    if "flash" in st.session_state:
        kind, message = st.session_state.pop("flash")
        {"success": st.success, "error": st.error, "info": st.info}.get(kind, st.info)(message)


def to_date(value: Optional[str]) -> Optional[date]:
    return date.fromisoformat(value[:10]) if value else None


def iso(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value else None


def app_label(a: Dict[str, Any]) -> str:
    return f"{STATUS_ICON.get(a['status'], '')} {a['company_name']} — {a['job_title']} ({a['status']})"


def show_extracted(info: Dict[str, Any]) -> None:
    """Pretty-print the AI extraction result."""
    cols = st.columns(3)
    cols[0].markdown(f"**Company:** {info.get('company_name') or '—'}")
    cols[1].markdown(f"**Role:** {info.get('job_title') or '—'}")
    cols[2].markdown(f"**Location:** {info.get('location') or '—'}")
    cols = st.columns(3)
    cols[0].markdown(f"**Experience:** {info.get('experience_required') or '—'}")
    cols[1].markdown(f"**Work mode:** {info.get('work_mode') or '—'}")
    cols[2].markdown(f"**Type / Salary:** {info.get('employment_type') or '—'} / {info.get('salary_range') or '—'}")
    if info.get("skills"):
        st.markdown("**Skills:** " + " · ".join(f"`{s}`" for s in info["skills"]))
    if info.get("summary"):
        st.caption(info["summary"])
    for title, key in (("Responsibilities", "responsibilities"), ("Qualifications", "qualifications")):
        if info.get(key):
            with st.expander(title):
                st.markdown("\n".join(f"- {x}" for x in info[key]))



# ---------------------------------------------------------------------------
# Page: My Resumes
# ---------------------------------------------------------------------------
def page_resumes() -> None:
    st.markdown(
        "<div class='ct-intro'><h3>Keep your resumes organized 📄</h3>"
        "<p>Upload PDF versions and choose the right one for each job application.</p></div>",
        unsafe_allow_html=True,
    )
    st.header("My Resumes")
    st.caption("Private storage · PDF only · Maximum 5 MB per file")
    show_flash()

    picked = st.file_uploader(
        "Choose a resume PDF", type=["pdf"], accept_multiple_files=False,
        key="resume_upload",
        help="Upload a PDF file up to 5 MB. Your resume is stored in your private account folder.",
    )
    if picked is not None and st.button("⬆️ Upload resume", type="primary", key="upload_resume_button"):
        if picked.size > 5 * 1024 * 1024:
            st.error("This file is larger than 5 MB. Please choose a smaller PDF.")
        else:
            try:
                with st.spinner("Uploading your resume securely..."):
                    upload_file("/api/resumes", picked)
                flash("Resume uploaded successfully.")
                st.rerun()
            except ApiError as err:
                st.error(f"⚠️ {err}")

    st.divider()
    st.subheader("Uploaded resumes")
    resumes = load("/api/resumes", default=[])
    if resumes is None:
        return
    if not resumes:
        st.info("You haven't uploaded any resumes yet. Choose a PDF above to get started.")
        return

    for item in resumes:
        c1, c2, c3 = st.columns([5, 2, 1])
        c1.markdown(f"📄 **{item.get('display_name') or item.get('name', 'Resume')}**")
        size = item.get("size_bytes")
        c2.caption(f"{round(int(size) / 1024)} KB" if size else "PDF resume")
        with c3:
            name = item.get("name", "")
            confirm_key = f"confirm_delete_resume_{name}"
            if st.button("🗑️", key=f"delete_resume_{name}", help="Delete this resume"):
                st.session_state[confirm_key] = True
            if st.session_state.get(confirm_key):
                st.warning(f"Delete {item.get('display_name') or name}?")
                yes, no = st.columns(2)
                if yes.button("Confirm", key=f"confirm_yes_{name}"):
                    try:
                        api("DELETE", f"/api/resumes/{quote(name, safe='')}")
                        st.session_state.pop(confirm_key, None)
                        flash("Resume deleted.")
                        st.rerun()
                    except ApiError as err:
                        st.error(f"⚠️ {err}")
                if no.button("Cancel", key=f"confirm_no_{name}"):
                    st.session_state.pop(confirm_key, None)
                    st.rerun()
        st.divider()


# ---------------------------------------------------------------------------
# Page: Dashboard
# ---------------------------------------------------------------------------
def page_dashboard() -> None:
    st.markdown("<div class='ct-intro'><h3>Welcome to your career command center 👋</h3><p>Keep every application organized, stay ahead of follow-ups, and prepare for your next opportunity.</p></div>", unsafe_allow_html=True)
    st.header("Dashboard")
    stats = load("/api/dashboard/stats")
    if stats is None:
        return

    if stats["total_applications"] == 0:
        st.info("No applications yet. Add your first one, or load a few fictional examples to explore the app.")
        if st.button("Load demo data"):
            try:
                with st.spinner("Loading demo data..."):
                    result = api("POST", "/api/demo/seed")
                flash(f"Loaded {result['inserted']} demo applications.")
                st.rerun()
            except ApiError as err:
                st.error(f"⚠️ {err}")
        return

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total applications", stats["total_applications"])
    c2.metric("Interviews", stats["interviews"])
    c3.metric("Offers", stats["offers"])
    c4.metric("Rejections", stats["rejections"])
    c5.metric("Follow-ups due", stats["follow_ups_due"], help="Open applications with a follow-up date of today or earlier.")

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Applications by status")
        st.bar_chart(pd.Series(stats["status_counts"], name="Applications"))
    with right:
        st.subheader("Follow-ups this week")
        data = load("/api/followups", {"days": 7}, default={"overdue": [], "today": [], "upcoming": []})
        rows = ([("🔴 Overdue", i) for i in data["overdue"]] + [("🟠 Today", i) for i in data["today"]]
                + [("🟢 Upcoming", i) for i in data["upcoming"]])
        if not rows:
            st.success("Nothing due. You're all caught up!")
        for label, item in rows[:8]:
            st.markdown(f"{label} · **{item['company_name']}** — {item['job_title']} · {item['follow_up_date']}")
        if rows:
            st.caption("Open the Follow-ups page to draft emails.")


# ---------------------------------------------------------------------------
# Page: Applications (search, filter, view, edit, delete)
# ---------------------------------------------------------------------------
def page_applications() -> None:
    st.markdown("<div class='ct-intro'><h3>Your job search, all in one place</h3><p>Track progress, review details, and keep your next steps clear.</p></div>", unsafe_allow_html=True)
    st.header("My Applications")
    show_flash()

    with st.expander("🔎 Search & filter", expanded=True):
        f1, f2, f3 = st.columns(3)
        company = f1.text_input("Company contains")
        role = f2.text_input("Role contains")
        status = f3.selectbox("Status", ["All"] + STATUSES)
        d1, d2 = st.columns(2)
        date_from = d1.date_input("Applied from", value=None)
        date_to = d2.date_input("Applied to", value=None)

    with st.spinner("Loading applications..."):
        apps = load("/api/applications", {
            "company": company, "role": role,
            "status": None if status == "All" else status,
            "date_from": iso(date_from), "date_to": iso(date_to),
        })
    if apps is None:
        return
    if not apps:
        st.info("No applications match. Clear the filters or add a new application.")
        return

    st.caption(f"{len(apps)} application(s) · Select a card below, then edit its details.")
    # JobTrakr-inspired responsive card grid. The existing edit/history actions remain below.
    tint = {
        "Offer": "#ddf8e8", "Interview": "#dceaff", "Assessment": "#eee8ff",
        "Rejected": "#ffe5e7", "Withdrawn": "#f0f2f6", "Saved": "#e4f7f3",
        "Applied": "#e1efff",
    }
    for start in range(0, len(apps), 3):
        cols = st.columns(3, gap="medium")
        for col, a in zip(cols, apps[start:start + 3]):
            bg = tint.get(a.get("status", "Applied"), "#e1efff")
            applied = a.get("application_date") or "Date not set"
            location_text = a.get("location") or "Location not specified"
            follow = a.get("follow_up_date") or "No follow-up set"
            html = f"""
            <div class="ct-job-card" style="background:{bg}">
              <div class="ct-date">{applied}</div>
              <div class="ct-company">{a['company_name']}</div>
              <div class="ct-role">{a['job_title']}</div>
              <div class="ct-tags">
                <span class="ct-tag">{a['status']}</span>
                <span class="ct-tag">{location_text}</span>
              </div>
              <div class="ct-card-foot">Follow-up: {follow}</div>
            </div>
            """
            with col:
                st.markdown(html, unsafe_allow_html=True)

    st.divider()
    by_id = {a["id"]: a for a in apps}
    selected_id = st.selectbox("Select an application to view or edit", list(by_id), format_func=lambda i: app_label(by_id[i]))
    current = by_id[selected_id]

    tab_edit, tab_desc, tab_history = st.tabs(["✏️ Details & edit", "📄 Job description & AI info", "🕘 History"])

    with tab_edit:
        with st.form(f"edit_form_{selected_id}"):
            e1, e2 = st.columns(2)
            company_name = e1.text_input("Company name *", value=current["company_name"])
            job_title = e2.text_input("Job title *", value=current["job_title"])
            e3, e4 = st.columns(2)
            job_url = e3.text_input("Job URL", value=current["job_url"] or "")
            location = e4.text_input("Location", value=current["location"] or "")
            e5, e6, e7 = st.columns(3)
            new_status = e5.selectbox("Status", STATUSES, index=STATUSES.index(current["status"]) if current["status"] in STATUSES else 0)
            application_date = e6.date_input("Application date", value=to_date(current["application_date"]))
            follow_up_date = e7.date_input("Follow-up date", value=to_date(current["follow_up_date"]))
            uploaded_resumes = load("/api/resumes", default=[])
            uploaded_resumes = uploaded_resumes if isinstance(uploaded_resumes, list) else []
            resume_labels = [item.get("display_name") or item.get("name") for item in uploaded_resumes]
            current_resume = current.get("resume_version") or ""
            resume_options = ["— None —"] + resume_labels
            if current_resume and current_resume not in resume_options:
                resume_options.append(current_resume)  # preserve older manually entered versions
            selected_resume = st.selectbox(
                "Resume used for this application",
                resume_options,
                index=resume_options.index(current_resume) if current_resume in resume_options else 0,
                help="Upload a PDF in My Resumes first, then select it here.",
            )
            resume_version = "" if selected_resume == "— None —" else selected_resume
            job_description = st.text_area("Job description", value=current["job_description"] or "", height=180)
            notes = st.text_area("Notes", value=current["notes"] or "", height=100)
            saved = st.form_submit_button("💾 Save changes", type="primary")
        if saved:
            payload = {
                "company_name": company_name, "job_title": job_title, "job_url": job_url or None,
                "location": location or None, "status": new_status,
                "application_date": iso(application_date), "follow_up_date": iso(follow_up_date),
                "resume_version": resume_version or None, "job_description": job_description or None,
                "notes": notes or None,
            }
            try:
                with st.spinner("Saving..."):
                    api("PUT", f"/api/applications/{selected_id}", body=payload)
                flash("✅ Application updated.")
                st.rerun()
            except ApiError as err:
                st.error(f"⚠️ Could not save: {err}")

        st.markdown("##### Delete")
        confirm = st.checkbox("Yes, permanently delete this application", key=f"confirm_{selected_id}")
        if st.button("🗑️ Delete application", disabled=not confirm, key=f"delete_{selected_id}"):
            try:
                with st.spinner("Deleting..."):
                    api("DELETE", f"/api/applications/{selected_id}")
                flash("🗑️ Application deleted.")
                st.rerun()
            except ApiError as err:
                st.error(f"⚠️ Could not delete: {err}")

    with tab_desc:
        if current.get("job_url"):
            st.link_button("Open job posting", current["job_url"])
        if current.get("extracted_info"):
            st.subheader("AI-extracted details")
            show_extracted(current["extracted_info"])
        elif current.get("job_description"):
            if st.button("✨ Extract details with AI", key=f"extract_{selected_id}"):
                try:
                    with st.spinner("Asking the AI..."):
                        result = api("POST", "/api/ai/extract-job", body={"job_description": current["job_description"]})
                    api("PUT", f"/api/applications/{selected_id}", body={"extracted_info": result["extracted"]})
                    flash("✨ Details extracted and saved.")
                    st.rerun()
                except ApiError as err:
                    st.error(f"⚠️ {err}")
        st.subheader("Job description")
        st.write(current.get("job_description") or "_No job description saved._")

    with tab_history:
        history = load(f"/api/applications/{selected_id}/history", default=[])
        if not history:
            st.caption("No history yet.")
        for h in history:
            when = h["changed_at"][:16].replace("T", " ")
            change = f"{h['old_status']} → **{h['new_status']}**" if h.get("old_status") else f"Created as **{h['new_status']}**"
            st.markdown(f"- `{when}` · {change}")


# ---------------------------------------------------------------------------
# Page: Add application (with AI extraction)
# ---------------------------------------------------------------------------
def page_add() -> None:
    st.markdown("<div class='ct-intro'><h3>Make every opportunity count ✨</h3><p>Add a role manually or paste a job description to pre-fill details.</p></div>", unsafe_allow_html=True)
    st.header("Add an Application")
    show_flash()
    st.session_state.setdefault("draft", {})
    st.session_state.setdefault("form_nonce", 0)
    draft: Dict[str, Any] = st.session_state["draft"]
    nonce = st.session_state["form_nonce"]

    st.subheader("1. Paste a job description (optional)")
    pasted = st.text_area("Job description", height=180, key="paste_jd",
                          placeholder="Paste the full job posting here, then click 'Extract with AI' to pre-fill the form below.")
    if st.button("✨ Extract with AI"):
        if len(pasted.strip()) < 30:
            st.warning("Paste at least a few sentences of the job description first.")
        else:
            try:
                with st.spinner("Reading the job description..."):
                    result = api("POST", "/api/ai/extract-job", body={"job_description": pasted})
                info = result["extracted"]
                st.session_state["draft"] = {
                    "company_name": info.get("company_name") or "", "job_title": info.get("job_title") or "",
                    "location": info.get("location") or "", "job_description": pasted, "extracted": info,
                    "source": result.get("source"),
                }
                st.session_state["form_nonce"] += 1  # new widget keys -> form shows the new defaults
                st.rerun()
            except ApiError as err:
                st.error(f"⚠️ {err}")

    if draft.get("extracted"):
        st.success("Details extracted. Review and edit them in the form below.")
        if draft.get("source") == "demo":
            st.caption("Demo mode: simple keyword extraction. Set GEMINI_API_KEY on the backend for real AI.")
        show_extracted(draft["extracted"])

    st.subheader("2. Application details")
    with st.form(f"add_form_{nonce}"):
        a1, a2 = st.columns(2)
        company_name = a1.text_input("Company name *", value=draft.get("company_name", ""), key=f"c_{nonce}")
        job_title = a2.text_input("Job title *", value=draft.get("job_title", ""), key=f"t_{nonce}")
        a3, a4 = st.columns(2)
        job_url = a3.text_input("Job URL", placeholder="https://...", key=f"u_{nonce}")
        location = a4.text_input("Location", value=draft.get("location", ""), key=f"l_{nonce}")
        a5, a6, a7 = st.columns(3)
        status = a5.selectbox("Status", STATUSES, index=0, key=f"s_{nonce}")
        application_date = a6.date_input("Application date", value=None, key=f"ad_{nonce}")
        follow_up_date = a7.date_input("Follow-up date", value=None, key=f"fd_{nonce}")
        uploaded_resumes = load("/api/resumes", default=[])
        uploaded_resumes = uploaded_resumes if isinstance(uploaded_resumes, list) else []
        resume_labels = [item.get("display_name") or item.get("name") for item in uploaded_resumes]
        resume_options = ["— None —"] + resume_labels
        selected_resume = st.selectbox(
            "Resume used for this application",
            resume_options,
            help="Upload a PDF in My Resumes first. You can select the resume you send to this company.",
            key=f"resume_choice_{nonce}",
        )
        resume_version = "" if selected_resume == "— None —" else selected_resume
        job_description = st.text_area("Job description", value=draft.get("job_description", ""), height=150, key=f"jd_{nonce}")
        notes = st.text_area("Notes", height=80, key=f"n_{nonce}")
        submitted = st.form_submit_button("💾 Save application", type="primary")

    if submitted:
        if not company_name.strip() or not job_title.strip():
            st.error("Company name and job title are required.")
            return
        payload = {
            "company_name": company_name, "job_title": job_title, "job_url": job_url or None,
            "location": location or None, "status": status,
            "application_date": iso(application_date), "follow_up_date": iso(follow_up_date),
            "resume_version": resume_version or None, "job_description": job_description or None,
            "notes": notes or None, "extracted_info": draft.get("extracted"),
        }
        try:
            with st.spinner("Saving..."):
                api("POST", "/api/applications", body=payload)
            st.session_state["draft"] = {}
            st.session_state["form_nonce"] += 1
            flash(f"✅ Saved {company_name.strip()} — {job_title.strip()}.")
            st.rerun()
        except ApiError as err:
            st.error(f"⚠️ Could not save: {err}")


# ---------------------------------------------------------------------------
# Page: Follow-ups (+ AI email drafts; nothing is ever sent automatically)
# ---------------------------------------------------------------------------
def page_followups() -> None:
    st.header("⏰ Follow-ups")
    days = st.slider("Show upcoming follow-ups within (days)", 1, 30, 7)
    data = load("/api/followups", {"days": days})
    if data is None:
        return

    groups = [("🔴 Overdue", data["overdue"]), ("🟠 Due today", data["today"]), (f"🟢 Next {days} days", data["upcoming"])]
    if not any(items for _, items in groups):
        st.success("No follow-ups due. Set follow-up dates on your applications to see them here.")
        return

    sender = st.text_input("Your name (used to sign the emails)")
    tone = st.selectbox("Email tone", ["professional", "friendly", "concise"])
    st.caption("✉️ CareerTrack AI only drafts emails. You review, edit and send them yourself.")

    for title, items in groups:
        if not items:
            continue
        st.subheader(f"{title} ({len(items)})")
        for item in items:
            key = item["id"]
            when = "today" if item["days_until"] == 0 else (f"{-item['days_until']} day(s) overdue" if item["days_until"] < 0 else f"in {item['days_until']} day(s)")
            with st.expander(f"{item['company_name']} — {item['job_title']} · {item['status']} · due {item['follow_up_date']} ({when})"):
                st.write(f"**Applied:** {item['application_date'] or '—'}  |  **Resume:** {item['resume_version'] or '—'}")
                if item.get("notes"):
                    st.caption(f"Notes: {item['notes']}")
                extra = st.text_input("Anything to mention? (optional)", key=f"extra_{key}")
                if st.button("✨ Draft follow-up email", key=f"draft_{key}"):
                    try:
                        with st.spinner("Writing a draft..."):
                            mail = api("POST", "/api/ai/follow-up-email", body={
                                "application_id": key, "tone": tone,
                                "sender_name": sender or None, "extra_context": extra or None})
                        st.session_state[f"subj_{key}"] = mail["subject"]
                        st.session_state[f"body_{key}"] = mail["body"]
                    except ApiError as err:
                        st.error(f"⚠️ {err}")
                if f"subj_{key}" in st.session_state:
                    subject = st.text_input("Subject", key=f"subj_{key}")
                    body = st.text_area("Email body (editable)", key=f"body_{key}", height=220)
                    st.link_button("Open in my email app", f"mailto:?subject={quote(subject)}&body={quote(body)}")


# ---------------------------------------------------------------------------
# Page: Interview prep
# ---------------------------------------------------------------------------
def page_interview() -> None:
    st.header("🎤 Interview preparation")
    source = st.radio("Generate questions from", ["A saved application", "A pasted job description"], horizontal=True)
    count = st.slider("Number of questions", 3, 20, 10)
    payload: Optional[Dict[str, Any]] = None

    if source == "A saved application":
        apps = load("/api/applications", default=[])
        if not apps:
            st.info("Save an application with a job description first.")
            return
        by_id = {a["id"]: a for a in apps}
        chosen = st.selectbox("Application", list(by_id), format_func=lambda i: app_label(by_id[i]))
        if st.button("✨ Generate questions", type="primary"):
            payload = {"application_id": chosen, "count": count}
    else:
        title = st.text_input("Job title (optional)")
        jd = st.text_area("Job description", height=200)
        if st.button("✨ Generate questions", type="primary"):
            if len(jd.strip()) < 30:
                st.warning("Paste at least a few sentences of the job description.")
            else:
                payload = {"job_title": title or None, "job_description": jd, "count": count}

    if payload:
        try:
            with st.spinner("Preparing your questions..."):
                st.session_state["iq"] = api("POST", "/api/ai/interview-questions", body=payload)
        except ApiError as err:
            st.error(f"⚠️ {err}")

    result = st.session_state.get("iq")
    if result:
        st.subheader(f"Questions{' for ' + result['job_title'] if result.get('job_title') else ''}")
        if result.get("source") == "demo":
            st.caption("Demo mode: generic template questions. Set GEMINI_API_KEY on the backend for tailored questions.")
        categories: Dict[str, List[Dict[str, Any]]] = {}
        for q in result["questions"]:
            categories.setdefault(q["category"], []).append(q)
        for cat, qs in categories.items():
            st.markdown(f"#### {cat}")
            for q in qs:
                with st.expander(q["question"]):
                    st.markdown("**💡 Hint**")
                    st.write(q.get("tip") or "No hint available.")
                    st.markdown("**✅ Sample Answer**")
                    st.write(q.get("answer") or "No sample answer available.")
        text = "\n\n".join(f"[{q['category']}]\n"
                           f"Question: {q['question']}\n"
                           f"Hint: {q.get('tip') or '-'}\n"
                           f"Sample Answer: {q.get('answer') or 'Not available'}"
                           for q in result["questions"])
        st.download_button("⬇️ Download as text", text, file_name="interview_questions.txt")


# ---------------------------------------------------------------------------
# Page: Analytics & history
# ---------------------------------------------------------------------------
def page_analytics() -> None:
    st.header("📈 Analytics & history")
    data = load("/api/analytics")
    if data is None:
        return
    if data["total_applications"] == 0:
        st.info("Add some applications to see analytics.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Response rate", f"{data['response_rate']}%", help="Submitted applications that moved past 'Applied'.")
    c2.metric("Interview rate", f"{data['interview_rate']}%", help="Submitted applications now at Interview or Offer.")
    c3.metric("Offer rate", f"{data['offer_rate']}%")
    st.caption("Rates use each application's current status; 'Saved' (not yet applied) is excluded.")

    left, right = st.columns(2)
    with left:
        st.subheader("Status breakdown")
        st.bar_chart(pd.Series(data["status_counts"], name="Applications"))
    with right:
        st.subheader("Applications per month")
        if data["monthly_applications"]:
            monthly = pd.DataFrame(data["monthly_applications"]).set_index("month")
            st.bar_chart(monthly["count"])
        else:
            st.caption("Set application dates to see this chart.")

    if data["resume_performance"]:
        st.subheader("Which resume version works best?")
        st.dataframe(pd.DataFrame(data["resume_performance"]).rename(columns={
            "resume_version": "Resume version", "applications": "Applications",
            "interviews_or_offers": "Interviews / offers"}), hide_index=True)

    st.subheader("Recent activity")
    history = load("/api/history", {"limit": 25}, default=[])
    if not history:
        st.caption("No activity yet.")
    for h in history:
        when = h["changed_at"][:16].replace("T", " ")
        change = f"{h['old_status']} → **{h['new_status']}**" if h.get("old_status") else f"added as **{h['new_status']}**"
        st.markdown(f"- `{when}` · **{h.get('company_name') or '?'}** ({h.get('job_title') or '?'}) {change}")


# ---------------------------------------------------------------------------
# Page: AI Resume Matching
# ---------------------------------------------------------------------------
def page_resume_matching() -> None:
    st.markdown(
        "<div class='ct-intro'><h3>Match your resume to the right opportunity 🤖</h3>"
        "<p>Compare an uploaded resume with a job description and identify strengths and skill gaps.</p></div>",
        unsafe_allow_html=True,
    )
    st.header("AI Resume Matching")
    st.caption("Your resume is processed through the CareerTrack AI backend. The match score is an estimate, not a hiring guarantee.")

    resumes = load("/api/resumes", default=[])
    if not isinstance(resumes, list):
        return
    if not resumes:
        st.info("You haven't uploaded a resume yet. Open **My Resumes** and upload a PDF first.")
        return

    valid_resumes = [item for item in resumes if item.get("name")]
    if not valid_resumes:
        st.warning("No usable resume files were returned. Please revisit My Resumes and try again.")
        return

    def resume_label(item: Dict[str, Any]) -> str:
        return str(item.get("display_name") or item.get("name") or "Resume")

    selected = st.selectbox(
        "Choose a resume",
        valid_resumes,
        format_func=resume_label,
        key="resume_match_selected",
    )
    job_description = st.text_area(
        "Paste the job description",
        height=260,
        key="resume_match_job_description",
        placeholder="Paste the complete job posting here, including responsibilities and required skills...",
        help="For a more useful comparison, include the role responsibilities and required qualifications.",
    )

    if st.button("✨ Analyze Resume", type="primary", use_container_width=True, key="analyze_resume_button"):
        if len(job_description.strip()) < 50:
            st.warning("Please paste a fuller job description (at least 50 characters).")
        else:
            resume_name = str(selected.get("name", ""))
            endpoint = f"/api/resumes/{quote(resume_name, safe='')}/match"
            try:
                with st.spinner("Reading your resume and comparing it with the job description..."):
                    result = api("POST", endpoint, body={"job_description": job_description.strip()})
                st.session_state["resume_match_result"] = result
                st.session_state["resume_match_result_name"] = resume_name
            except ApiError as err:
                st.error(f"⚠️ Could not analyze this resume: {err}")

    result = st.session_state.get("resume_match_result")
    current_name = selected.get("name")
    if result and st.session_state.get("resume_match_result_name") == current_name:
        st.divider()
        st.subheader("Your results")
        source = result.get("source", "unknown")
        if source == "demo":
            st.info("Demo mode is using keyword comparison, not Gemini AI. Treat this score as a rough indicator.")
        score = result.get("match_score", 0)
        try:
            score = max(0, min(100, int(score)))
        except (TypeError, ValueError):
            score = 0
        score_col, summary_col = st.columns([1, 3])
        score_col.metric("Resume match score", f"{score}%")
        score_col.progress(score / 100)
        with summary_col:
            st.markdown("**AI summary**")
            st.write(result.get("summary") or "No summary was returned.")

        left, right = st.columns(2)
        with left:
            st.markdown("#### ✅ Matching skills")
            matching = result.get("matching_skills") or []
            if matching:
                for skill in matching:
                    st.markdown(f"- {skill}")
            else:
                st.write("No matching skills were identified in the resume text.")
        with right:
            st.markdown("#### 🎯 Skills to review")
            missing = result.get("missing_skills") or []
            if missing:
                for skill in missing:
                    st.markdown(f"- {skill}")
            else:
                st.success("No missing skills were identified by this comparison.")

        st.markdown("#### 💪 Resume strengths")
        strengths = result.get("strengths") or []
        if strengths:
            for strength in strengths:
                st.markdown(f"- {strength}")
        else:
            st.caption("No specific strengths were returned.")

        st.markdown("#### 🚀 Suggestions to improve")
        suggestions = result.get("suggestions") or []
        if suggestions:
            for suggestion in suggestions:
                st.markdown(f"- {suggestion}")
        else:
            st.caption("No suggestions were returned.")

        st.caption("Important: a skill not mentioned in your resume may still be one you have. Add it only if it accurately reflects your experience.")


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
PAGES = {
    "📊 Dashboard": page_dashboard,
    "📁 Applications": page_applications,
    "➕ Add application": page_add,
    "📄 My Resumes": page_resumes,
    "🤖 Resume Matching": page_resume_matching,
    "⏰ Follow-ups": page_followups,
    "🎤 Interview prep": page_interview,
    "📈 Analytics": page_analytics,
}



def page_auth() -> None:
    """Sign-in, account creation, and password recovery screens."""
    st.markdown("""
    <div style="max-width:760px;margin:3rem auto 1rem auto;text-align:center;">
      <div style="font-size:3rem;">🧭</div>
      <h1 style="font-size:2.4rem!important;">CareerTrack AI</h1>
      <p style="font-size:1.05rem;">Your career search, organized in one place.</p>
    </div>
    """, unsafe_allow_html=True)
    left, center, right = st.columns([1, 1.15, 1])
    with center:
        mode = st.radio("Account", ["Sign in", "Create account", "Forgot password"], horizontal=True, label_visibility="collapsed")
        if mode == "Forgot password":
            st.subheader("Reset your password")
            st.caption("We'll send a recovery email if the account exists.")
            with st.form("forgot_password_form"):
                email = st.text_input("Email address", placeholder="you@example.com")
                submitted = st.form_submit_button("Send recovery email", type="primary", use_container_width=True)
            if submitted:
                if not email.strip():
                    st.error("Enter your email address.")
                else:
                    try:
                        result = api("POST", "/api/auth/forgot-password", body={"email": email.strip()})
                        st.success(result.get("message", "Check your email for recovery instructions."))
                    except ApiError as err:
                        st.error(str(err))
            return

        title = "Welcome back" if mode == "Sign in" else "Create your account"
        st.subheader(title)
        st.caption("Use your email and password to keep your applications private.")
        with st.form("account_form", clear_on_submit=False):
            email = st.text_input("Email address", placeholder="you@example.com")
            password = st.text_input("Password", type="password", placeholder="At least 8 characters")
            if mode == "Create account":
                confirm = st.text_input("Confirm password", type="password")
            else:
                confirm = password
            submitted = st.form_submit_button("Sign in" if mode == "Sign in" else "Create account", type="primary", use_container_width=True)
        if submitted:
            email = email.strip()
            if not email or not password:
                st.error("Enter your email address and password.")
            elif len(password) < 8:
                st.error("Password must contain at least 8 characters.")
            elif mode == "Create account" and password != confirm:
                st.error("The passwords do not match.")
            else:
                try:
                    if mode == "Sign in":
                        result = api("POST", "/api/auth/login", body={"email": email, "password": password})
                        st.session_state["access_token"] = result["access_token"]
                        st.session_state["refresh_token"] = result.get("refresh_token")
                        st.session_state["account_email"] = result.get("email", email)
                        st.session_state["user_id"] = result.get("user_id")
                        st.session_state.pop("iq", None)
                        st.success("Signed in successfully.")
                        st.rerun()
                    else:
                        result = api("POST", "/api/auth/signup", body={"email": email, "password": password})
                        if result.get("session_created") and result.get("access_token"):
                            st.session_state["access_token"] = result["access_token"]
                            st.session_state["refresh_token"] = result.get("refresh_token")
                            st.session_state["account_email"] = result.get("email", email)
                            st.session_state["user_id"] = result.get("user_id")
                            st.success("Account created.")
                            st.rerun()
                        else:
                            st.success("Account created. Check your email to verify it, then sign in.")
                except ApiError as err:
                    st.error(str(err))


def render_account_sidebar() -> None:
    """Show signed-in account details and logout action."""
    with st.sidebar:
        st.markdown("---")
        st.caption("SIGNED IN AS")
        st.write(st.session_state.get("account_email", "Account"))
        if st.button("Log out", use_container_width=True):
            for key in ("access_token", "refresh_token", "account_email", "user_id", "iq", "draft", "flash"):
                st.session_state.pop(key, None)
            st.rerun()


def main() -> None:
    if not st.session_state.get("access_token"):
        page_auth()
        return

    st.sidebar.title("⌕ CareerTrack AI")
    st.sidebar.caption("YOUR CAREER, ORGANIZED")
    render_account_sidebar()
    choice = st.sidebar.radio("Go to", list(PAGES), label_visibility="collapsed")
    try:
        info = requests.get(f"{BACKEND_URL}/health", timeout=REQUEST_TIMEOUT).json()
        if info.get("mode") == "demo":
            st.sidebar.warning("Demo mode: sample local database")
        st.sidebar.caption(f"AI: {info.get('ai', '?')} · DB: {info.get('database', '?')}")
    except Exception:
        st.sidebar.error("Backend not reachable")
    show_flash() if choice in ("📊 Dashboard", "⏰ Follow-ups", "🎤 Interview prep", "📈 Analytics") else None
    PAGES[choice]()

main()
