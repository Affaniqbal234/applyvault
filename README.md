<p align="center">
  <img src="assets/logo.png" width="120" alt="ApplyVault" />
</p>

<h1 align="center">ApplyVault</h1>

<p align="center">A job application tracker built to stop losing track of where you applied.</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-blue" alt="Python"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.115-green" alt="FastAPI"></a>
  <a href="https://github.com/yourusername/applyvault"><img src="https://img.shields.io/badge/github-repo-blue?logo=github" alt="GitHub"></a>
  <a href="https://github.com/yourusername/applyvault/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green" alt="License"></a>
</p>

<br/>

> **Live demo:** [applyvault.up.railway.app](https://applyvault.up.railway.app) — replace with your actual URL after deploying

![dashboard](assets/screenshot.png)

---

## Stack

- Backend: FastAPI, async SQLAlchemy, PostgreSQL
- Auth: JWT (PyJWT), bcrypt
- Frontend: vanilla HTML/CSS/JS
- Tests: pytest, httpx

## Features

- Register and log in with JWT sessions
- Track applications — company, role, status, date applied, notes, job posting link
- Update status as things progress (Applied, Interview, Offer, Rejected, Withdrawn)
- Search by company or role, filter by status
- Dashboard with live counts per status

---

## Running locally

Requires Python 3.10+ and PostgreSQL.

**1. Clone the repo**
```bash
git clone https://github.com/yourusername/applyvault.git
cd applyvault
```

**2. Create and activate a virtual environment**
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

**3. Install dependencies**
```bash
cd backend
pip install -r requirements.txt
```

**4. Set up environment variables**

From the `applyvault/` root folder:
```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Open `.env` and fill in your values:
```
DATABASE_URL=postgresql+asyncpg://postgres:yourpassword@localhost:5432/applyvault
JWT_SECRET=some-long-random-string
FRONTEND_ORIGIN=http://localhost:5500
```

> `postgres` is the default PostgreSQL username. The password is what you set when installing PostgreSQL. Create the database first with `createdb applyvault` or through pgAdmin.

**5. Start the API**
```bash
cd backend
uvicorn main:app --reload
```

**6. Serve the frontend**

In a second terminal:
```bash
cd frontend
python -m http.server 5500
```

Then open `http://localhost:5500/index.html` in your browser.

> If you're using VS Code, right-click `index.html` and choose "Open with Live Server" instead.

---

## Tests

Tests use SQLite so no Postgres setup needed.

```bash
cd backend
pytest tests/ -v
```

---

## What I'd add with more time

- Email nudges for applications sitting in "Applied" for 2+ weeks
- CSV export
- Dark/light theme toggle
