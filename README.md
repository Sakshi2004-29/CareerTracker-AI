# 🧭 CareerTrack AI

An AI-powered job application manager. Save applications, track their status, get follow-up reminders with
AI-drafted emails, extract details from pasted job descriptions, and generate interview questions.

| Layer      | Technology                                   | Hosted on                 |
|------------|----------------------------------------------|---------------------------|
| Frontend   | Streamlit                                    | Streamlit Community Cloud |
| Backend    | FastAPI + Pydantic                           | Render                    |
| Database   | Supabase PostgreSQL                          | Supabase                  |
| GenAI      | Google Gemini (`google-genai` official SDK)  | Called from the backend   |

```
Browser ──> Streamlit (frontend/app.py) ──HTTP + X-API-Key──> FastAPI (backend/main.py) ──> Supabase PostgreSQL
                                                                         └────────────────> Gemini API
```
The Streamlit app never sees your Supabase or Gemini keys. Only the backend has them.

## Features

- Dashboard: total applications, interviews, offers, rejections, follow-ups due
- Add / view / edit / delete applications (company, title, description, URL, dates, status, notes, resume version)
- AI extraction of company, role, skills, location, experience and more from a pasted job description
- Status tracking: Saved, Applied, Assessment, Interview, Offer, Rejected, Withdrawn (every change is logged in the history)
- Follow-up assistant: overdue / today / upcoming list and AI-drafted emails (**never sent automatically**)
- Interview preparation: role-specific questions from the job description
- Analytics: status breakdown, applications per month, response/interview/offer rates, resume-version performance
- Search and filter by company, role, status and date range
- Validation, loading spinners, and clear success/error messages everywhere

## Project structure

```
CareerTrack-AI/
├── frontend/
│   ├── app.py                       # Streamlit UI (6 pages)
│   ├── requirements.txt
│   └── .streamlit/
│       ├── config.toml
│       └── secrets.toml.example     # BACKEND_URL / BACKEND_API_KEY
├── backend/
│   ├── main.py                      # FastAPI app and all endpoints
│   ├── database.py                  # ALL database access (Supabase + demo SQLite)
│   ├── ai_service.py                # ALL Gemini calls (+ demo templates)
│   ├── models.py                    # Pydantic request/response models
│   ├── config.py                    # environment variables and startup checks
│   ├── demo.py, seed_demo.py        # demo data loader
│   ├── sample_data.json             # fictional sample applications
│   ├── tests/test_api.py            # smoke tests
│   ├── requirements.txt, requirements-dev.txt, pytest.ini
│   └── .env.example
├── supabase/
│   ├── schema.sql                   # tables, indexes, trigger, row level security
│   └── seed.sql                     # optional demo rows for Supabase
├── render.yaml                      # Render deployment blueprint
├── .gitignore
└── README.md
```

---

## Part 1 - Try it in 5 minutes (no accounts, no keys)

**Demo mode** stores data in a local SQLite file and answers AI requests with simple built-in templates.
It is for learning and testing; production uses Supabase and Gemini.

Prerequisite: **Python 3.11 or 3.12** from <https://www.python.org/downloads/> (tick "Add python.exe to PATH").
Check it in PowerShell: `py --version`

### 1. Open the project and create a virtual environment

```powershell
cd path\to\CareerTrack-AI
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell says "running scripts is disabled", run this once and retry:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Your prompt now starts with `(.venv)`. Activate it again in every new terminal.

### 2. Install dependencies (one environment for both parts)

```powershell
python -m pip install --upgrade pip
pip install -r backend\requirements.txt -r frontend\requirements.txt
```

### 3. Create the backend settings file

```powershell
Copy-Item backend\.env.example backend\.env
```

The example file already has `DEMO_MODE=true`, so no editing is needed for the demo.

### 4. Start the backend (terminal 1)

```powershell
cd backend
uvicorn main:app --reload --port 8000
```

Open <http://localhost:8000/docs> to see the interactive API documentation, and <http://localhost:8000/health> for status.

### 5. Start the frontend (terminal 2)

Open a **new** PowerShell window:

```powershell
cd path\to\CareerTrack-AI
.\.venv\Scripts\Activate.ps1
cd frontend
streamlit run app.py
```

The app opens at <http://localhost:8501>. On an empty dashboard, click **Load demo data** to get 8 fictional applications
(or run `python seed_demo.py` inside `backend`).

### 6. Run the automated tests (optional)

```powershell
cd backend
pip install -r requirements-dev.txt
pytest
```

---

## Part 2 - Real setup: Supabase + Gemini

### A. Create the Supabase project and database

1. Sign up at <https://supabase.com> and click **New project**.
2. Choose an organization, a project name (e.g. `careertrack-ai`), a strong **database password** (save it in a password manager), and the region closest to you. Click **Create new project** and wait about two minutes.
3. Open **SQL Editor** (left menu) -> **New query**.
4. Open `supabase/schema.sql` from this project, copy everything, paste it into the editor and click **Run**. You should see "Success. No rows returned".
5. Open **Table Editor**: you should see `job_applications` and `application_history`.
6. (Optional) Run `supabase/seed.sql` the same way to add demo rows.
7. Collect the two values the backend needs:
   - **Project URL**: Project Settings -> **Data API** (looks like `https://abcdxyz.supabase.co`).
   - **Secret key**: Project Settings -> **API Keys**. Use the **secret** key (or the legacy **service_role** key). Do **not** use the `anon` / publishable key: the tables are locked by Row Level Security, so it can read nothing.

> ⚠️ The secret key has full access to your database. It goes **only** into the backend's environment variables. Never paste it into the frontend, GitHub, screenshots or chats.

Supabase's dashboard layout changes from time to time; if a menu name differs, look for "API keys" in the project settings.

### B. Get a Gemini API key

1. Go to <https://aistudio.google.com/apikey> and sign in with a Google account.
2. Click **Create API key** (create or pick a Google Cloud project when asked) and copy the key.
3. The free tier has rate limits. If you see a "rate-limited" message in the app, wait a minute and retry.

The model name is configurable (`GEMINI_MODEL`, default `gemini-2.5-flash`) because Google retires old models.
If you ever see "model was not found", pick a current model from <https://ai.google.dev/gemini-api/docs/models>.

### C. Configure environment variables safely

Edit `backend\.env` (it is git-ignored):

```powershell
notepad backend\.env
```

```ini
ENVIRONMENT=development
DEMO_MODE=false
SUPABASE_URL=https://YOUR-PROJECT.supabase.co
SUPABASE_SERVICE_KEY=paste-the-secret-key-here
GEMINI_API_KEY=paste-your-gemini-key-here
GEMINI_MODEL=gemini-2.5-flash
BACKEND_API_KEY=
FRONTEND_ORIGIN=
APP_TIMEZONE=Asia/Kolkata
```

Rules for secrets:
- Only edit `.env`, never `.env.example` (which is committed and must stay empty of real values).
- `.gitignore` already excludes `.env` and `secrets.toml`. Before every commit run `git status` and make sure neither file is listed.
- If a key ever leaks, delete/rotate it in the Supabase or Google dashboard immediately.

To use a backend API key locally (recommended practice run), set the same random value in both places:

```powershell
# generate a random key
[guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
```
Put it in `backend\.env` as `BACKEND_API_KEY=...`, and in `frontend\.streamlit\secrets.toml`
(copy `secrets.toml.example` to `secrets.toml` first) as `BACKEND_API_KEY = "..."`.

### D. Run with the real services

Same commands as Part 1 steps 4 and 5. `http://localhost:8000/health` should now show `"database":"supabase"` and `"ai":"gemini"`.
If a setting is missing, the backend stops at startup and tells you exactly which one.

---

## Part 3 - Deployment

Deploy in this order: GitHub -> Render (backend) -> Streamlit Cloud (frontend) -> finish Render settings.

### 1. Push the project to GitHub

```powershell
cd path\to\CareerTrack-AI
git init
git add .
git status          # CHECK: .env and secrets.toml must NOT appear in this list
git commit -m "CareerTrack AI"
git branch -M main
git remote add origin https://github.com/YOUR-USER/CareerTrack-AI.git
git push -u origin main
```
(Create the empty repository on github.com first. A private repository works with both Render and Streamlit Cloud.)

### 2. Deploy the backend on Render

1. <https://render.com> -> **New** -> **Blueprint** -> connect the GitHub repo. Render reads `render.yaml`.
2. When prompted, enter the values marked as secret: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GEMINI_API_KEY`. Leave `FRONTEND_ORIGIN` empty for now.
3. Deploy. Wait for "Live", then open `https://YOUR-SERVICE.onrender.com/health`: you should see `{"status":"ok", ...}`.
4. In the Render dashboard -> your service -> **Environment**, copy the generated **`BACKEND_API_KEY`** value (you need it in step 3).

Manual alternative (without the Blueprint): New -> Web Service, **Root Directory** `backend`, **Build Command** `pip install -r requirements.txt`,
**Start Command** `uvicorn main:app --host 0.0.0.0 --port $PORT`, **Health Check Path** `/health`, and add the same environment variables as in `render.yaml`.

> Render's free plan pauses the service when idle: the first request afterwards can take ~50 seconds. The app waits up to 90 seconds.

### 3. Deploy the frontend on Streamlit Community Cloud

1. <https://share.streamlit.io> -> **Create app** -> pick your repo, branch `main`, and **Main file path** `frontend/app.py`.
2. Open **Advanced settings**: choose Python 3.12 and paste into **Secrets**:
   ```toml
   BACKEND_URL = "https://YOUR-SERVICE.onrender.com"
   BACKEND_API_KEY = "the-value-copied-from-render"
   ```
3. Optionally pick a custom app subdomain, then click **Deploy**. Dependencies come from `frontend/requirements.txt`.

### 4. Lock CORS to your frontend

In Render -> Environment set `FRONTEND_ORIGIN` to your Streamlit URL **without a trailing slash**
(e.g. `https://careertrack-ai.streamlit.app`). Render redeploys automatically. In production the backend allows only this origin.
(Streamlit calls the backend from its own server, so the app also works before this step; the setting protects against other websites calling your API from a browser.)

### 5. Final check

Open your Streamlit URL. The sidebar should show `AI: gemini · DB: supabase`. Add an application, extract a job description, and draft an email.

---

## API reference

All `/api/*` routes need the header `X-API-Key` when `BACKEND_API_KEY` is set. Interactive docs: `/docs`.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Status (public) |
| GET | `/api/applications` | List; filters: `company`, `role`, `status`, `date_from`, `date_to` |
| POST | `/api/applications` | Create |
| GET / PUT / DELETE | `/api/applications/{id}` | Read / partial update / delete |
| GET | `/api/applications/{id}/history` | Status history of one application |
| GET | `/api/history?limit=30` | Recent activity |
| GET | `/api/dashboard/stats` | Dashboard numbers |
| GET | `/api/followups?days=7` | Overdue, due today, upcoming |
| GET | `/api/analytics` | Rates, monthly counts, resume performance |
| POST | `/api/ai/extract-job` | Extract details from a job description |
| POST | `/api/ai/follow-up-email` | Draft a follow-up email (returns text only) |
| POST | `/api/ai/interview-questions` | Questions from an application or pasted description |
| POST | `/api/demo/seed` | Load sample data (only if `ALLOW_DEMO_SEED=true`) |

Definitions: *follow-ups due* = applications in Saved/Applied/Assessment/Interview with a follow-up date of today or earlier
(Offer, Rejected, Withdrawn count as closed). "Today" follows `APP_TIMEZONE`.

## Security notes

- Gemini and Supabase keys exist only in backend environment variables.
- Row Level Security is enabled with no policies, so the public Supabase keys cannot access the data.
- In production the backend refuses to start without `BACKEND_API_KEY`, and CORS allows only `FRONTEND_ORIGIN`.
- This version has **no user accounts**: everyone with access to your deployed app sees the same data. It is built as a personal tool. For multiple users, add Supabase Auth and a `user_id` column with per-user policies.
- Pasted job descriptions are treated as untrusted data in the AI prompts, but always review AI output before relying on it.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Cannot reach the backend` | Start the backend (Part 1 step 4), or check `BACKEND_URL`. On Render, wait ~50 s and retry. |
| `Missing or invalid API key` | `BACKEND_API_KEY` must be identical in backend env and frontend secrets. |
| `Database tables not found` | Run `supabase/schema.sql` in the Supabase SQL Editor. |
| `Supabase rejected the credentials` | Re-copy `SUPABASE_URL` and the secret key; no spaces or quotes. |
| `AI features are not configured` (503) | Set `GEMINI_API_KEY` on the backend. |
| `model ... was not found` | Set `GEMINI_MODEL` to a current Gemini model. |
| `Configuration problems:` on backend start | The message lists the missing variables. |
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` |
| `uvicorn is not recognized` | Activate the virtual environment first (`.\.venv\Scripts\Activate.ps1`). |
| Port 8000 already in use | Use `--port 8001` and set `BACKEND_URL` accordingly. |

## Ideas for next steps

Supabase Auth for multiple users, file upload for resumes, calendar (.ics) export of follow-ups, email templates per status.
