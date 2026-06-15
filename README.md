<p align="center">
  <img src="assets/logo.svg" width="110" alt="ApplyVault" />
</p>

<h1 align="center">ApplyVault</h1>

<p align="center">A job application tracker built to stop losing track of where you applied.</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-3776ab?logo=python&logoColor=white" alt="Python"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <img src="https://img.shields.io/badge/JavaScript-ES6+-f7df1e?logo=javascript&logoColor=black" alt="JavaScript">
  <img src="https://img.shields.io/badge/HTML5-orange?logo=html5&logoColor=white" alt="HTML5">
  <img src="https://img.shields.io/badge/CSS3-blue?logo=css3&logoColor=white" alt="CSS3">
  <a href="https://github.com/Affaniqbal234/applyvault"><img src="https://img.shields.io/badge/github-repo-181717?logo=github" alt="GitHub"></a>
  <a href="https://github.com/Affaniqbal234/applyvault/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green" alt="License"></a>
</p>

<br/>

> **Live demo:** coming soon — deploying to Render

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
git clone https://github.com/Affaniqbal234/applyvault.git
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

> `postgres` is the default PostgreSQL username — created automatically when PostgreSQL is installed. The password is what you set during installation. Create the database first with `createdb applyvault` or through pgAdmin.

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

> If you're using VS Code, right-click `index.html` → "Open with Live Server" instead.

---

## Tests

Tests use SQLite so no Postgres setup needed.

```bash
cd backend
pytest tests/ -v
```

---

## What I'd add with more time

- Deploy with a live URL
- Email nudges for applications sitting in "Applied" for 2+ weeks
- CSV export
- Dark/light theme toggle
