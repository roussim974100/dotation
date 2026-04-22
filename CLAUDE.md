# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**"À Quai"** — Internal web application for managing employee/elected official resource allocation and return workflows (dotation/restitution) for French municipalities.

## Development Commands

```bash
# Setup (from project root)
python3 -m venv .venv
source .venv/bin/activate          # Linux
# .venv\Scripts\Activate.ps1      # Windows PowerShell
pip install -r backend/requirements.txt

# Run development server (http://localhost:5000)
export APP_SECRET_KEY="any-dev-key"
export SESSION_COOKIE_SECURE="0"
python3 backend/app.py

# Run tests
pytest backend/tests/ -v
pytest backend/tests/test_auth.py    # single file

# Syntax check (no linter configured)
python3 -m py_compile backend/app.py
python3 -m py_compile backend/auth.py backend/models/*.py backend/routes/*.py
```

## Architecture

**Stack**: Flask (Python 3.11+) + SQLite + Vanilla JS frontend served by Flask.

### Backend Structure

- `backend/app.py` — Flask app factory, blueprint registration, `init_db()` creates all SQLite tables on startup
- `backend/auth.py` — Login, bcrypt password hashing, `@login_required`/`@admin_required`/`@permission_required` decorators, CSRF token validation, rate limiting (10 attempts/10 min/IP)
- `backend/config.py` — Paths and environment variable handling
- `backend/database.py` — SQLite connection helpers, `ensure_column()` for non-destructive schema evolution
- `backend/routes/` — Flask blueprints: `pages.py` (auth + HTML serving), `forms.py` (dossier CRUD + PDF/Excel exports), `admin.py` (users, settings, logs, trash, catalogs), `signature.py` (public signature endpoints)
- `backend/models/` — Business logic: `forms.py` (dossier CRUD), `workflow.py` (status/validation), `settings.py` (branding/config), `catalog.py` (resource/service catalogs), `audit.py` (logging), `signature.py` (token links)
- `backend/pdf/` — PDF generation with fpdf2: `attribution.py` (dossier), `restitution.py` (return document)

### Frontend Structure

Static HTML pages served by Flask. JS is **not bundled** — each page loads its own script files directly.

- `frontend/js/app.js` (~3000 lines) — Main dossier form logic, API calls
- `frontend/js/storage.js` (~2500 lines) — Client-side form state via localStorage
- `frontend/js/admin.js` — Admin interface
- `frontend/js/ui.js` — Shared UI utilities
- `frontend/js/branding.js` — Logo/theme loading on every page

### Database

SQLite at `backend/dotation.db` (auto-created). Key tables:
- `dotation_forms` — Main dossier records with `payload_json` column for dynamic resource fields
- `dotation_items` — Per-resource rows for restitution tracking
- `app_logs` — App-wide audit trail (scope: security/admin/form)
- `audit_events` — Dossier-specific history
- `deleted_items` — Soft-delete trash
- `resource_catalog`, `service_catalog` — Admin-managed reference data
- `app_settings` — Key-value store for branding and configuration
- `signature_links` — One-time tokens for remote signing

Schema changes use `ensure_column()` (ALTER TABLE IF NOT EXISTS equivalent). No migration framework.

### Authentication & Permissions

Users and groups defined in `backend/users.json`. Groups have permission lists like `forms.read_list`, `forms.create`, `forms.export`, `forms.delete`, `users.manage`. Admin group has wildcard `"*"`. Users with `data_scope: "masked"` receive RGPD-masked beneficiary data.

Session cookie: `publier_session`, HttpOnly, SameSite=Lax. CSRF token required on all state-changing API calls.

### API Conventions

All API endpoints under `/api/*` return JSON. HTML pages served at root paths. Public (no-auth) endpoints: `/login`, `/signup`, `/api/csrf-token`, `/signature/<token>`, `/api/signature/<token>`.

Dossier types: `arrivee`, `changement_service`, `mise_a_jour`, `sortie`.

### Dynamic Resource Field Keys

Resource `fields{}` use **camelCase** keys (e.g. `numeroSerie`, `nomTelephone`, `conditionAttribution`). These keys are defined in `resource_catalog.field_schema_json` and stored as-is in `payload_json`.

**Warning:** `slugify_field_key()` in `utils.py` converts keys to lowercase (`numeroSerie` → `numeroserie`). It must only be used to **create** new keys from user labels, never to **look up** values in existing `fields{}` dicts. Any lookup after slugification must use a case-insensitive fallback (see `field_values_lower` pattern in `workflow.py`).

The backend (`collect_resource_validation_errors` in `workflow.py`) is the single source of truth for resource validation. The JS frontend provides inline UX feedback only.

## Key Environment Variables

| Variable | Purpose | Dev default |
|---|---|---|
| `APP_SECRET_KEY` | Flask session key | Auto-generated, saved to `backend/.app_secret_key` |
| `SESSION_COOKIE_SECURE` | Require HTTPS for cookies | `"0"` for localhost |

## Tests

`backend/tests/conftest.py` provides fixtures:
- `client` — unauthenticated
- `admin_client` — pre-authenticated admin
- `redac_client` — pre-authenticated redaction user

Each test gets an isolated temporary SQLite DB and `users.json`.

## Production Notes

Deployed as: `gunicorn` → `nginx` reverse proxy on Linux. SQLite must be on local disk (not network share — causes locking corruption). `SESSION_COOKIE_SECURE=1` required when behind HTTPS.

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current
