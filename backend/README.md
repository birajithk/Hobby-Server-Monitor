# Falcon Backend — Hobby Server Monitor

This directory contains the Falcon backend for **Hobby Server Monitor**, an on-premises LXD container management and monitoring tool. It uses **Falcon (Python)** for its HTTP API, **pylxd** for LXD operations, **SQLite** for application data, and **TinyFlux** for time-series measurements.

## Responsibilities

- Google OAuth 2.0 login, server-side sessions, logout, and CSRF protection.
- Admin and Container User authorization, including container-level access checks.
- LXD container creation, adoption, lifecycle operations, and resource-limit updates.
- User invitations, roles, revocation/reactivation, ownership, and resource quotas.
- Restricted, non-interactive command execution inside authorized containers.
- Current and historical container-metrics APIs.

## Directory structure

| Path | Purpose |
| --- | --- |
| `app/api/` | Falcon API resources and endpoints |
| `app/auth/` | Google OAuth, identity, sessions, and authentication middleware |
| `app/db/` | SQLite schema, initialization, and migrations |
| `app/metrics/` | TinyFlux storage, aggregation, and metric collection |
| `app/services/` | Business rules, authorization, resource accounting, and LXD integration |
| `app/main.py` | Falcon application and route registration |
| `app/collector.py` | Independent metrics-collector entry point |
| `tests/` | Automated backend tests |
| `requirements.txt` | Python dependencies |

## Development setup

Run the following from the **repository root** to create the local configuration file:

```bash
cp .env.example backend/.env
```

Edit `backend/.env` to supply your **own** Google OAuth client ID and secret, callback URI, session secret, and bootstrap Admin email. The application loads `backend/.env` through `app/config.py`. Never commit the `.env` file or real secrets.

For the local Astro development server, the Google OAuth callback is:

```dotenv
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:4321/auth/google/callback
COOKIE_SECURE=false
```

Then install the backend dependencies:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m app.db.init_db
```

SQLite and TinyFlux use the configured paths; relative paths are resolved against the process working directory. Use a consistently configured working directory when starting backend processes.

## Start the Falcon API (development only)

**Do not start a second Gunicorn process when the deployed systemd service is already listening on port `8000`.** The installed deployment starts Falcon automatically through `hobby-server-monitor-api.service`. On that deployment, check its status instead:

```bash
sudo systemctl status hobby-server-monitor-api --no-pager
```

For a separate development run, ensure port `8000` is available. From `backend/` with its virtual environment activated:

```bash
gunicorn --bind 127.0.0.1:8000 --workers 1 app.main:app
```

Verify the API:

```bash
curl --fail http://127.0.0.1:8000/api/health
```

## Independent metrics collector

For a local development run, from `backend/` with the virtual environment activated:

```bash
python -m app.collector
```

For a single collection cycle:

```bash
python -m app.collector --once
```

**Do not launch a duplicate collector against the deployed metrics database.** The production collector runs under `hobby-server-monitor-collector.service` and continues independently of the dashboard and Falcon API.

```bash
sudo systemctl status hobby-server-monitor-collector --no-pager
```

## Run automated tests

From `backend/` with the virtual environment activated:

```bash
python -m unittest discover -s tests -v
```

## Security considerations

The browser must never access LXD directly. Falcon validates sessions, CSRF tokens, roles, container assignments, input and quotas before privileged actions. **Local LXD administrative socket access is highly privileged and can effectively provide host-level control**, even when Falcon runs under a dedicated non-root service account. See `../docs/DECISIONS.md` for this documented residual risk.

## Related documentation

- [`../README.md`](../README.md) — overall setup, API reference, and system architecture.
- [`../deploy/README.md`](../deploy/README.md) — systemd, Nginx, HTTPS, deployment, and recovery.
- [`../REPORT.md`](../REPORT.md) — measured resource usage, design tradeoffs, and limitations.