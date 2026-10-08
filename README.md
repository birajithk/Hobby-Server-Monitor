# Hobby Server Monitor

A lightweight, browser-based management and monitoring system for an on-premises Linux server using LXD containers.

Built for the RoboticGen Software Engineer Intern task.

## 1. Project Overview

Hobby Server Monitor lets an administrator manage LXD containers, users, resource quotas, terminal access, and historical resource usage from a browser.

The application runs on the same Linux machine it monitors, so resource efficiency and security are central design requirements.

### Technology stack

| Component | Technology |
| --- | --- |
| Backend API | Falcon (Python) |
| Container management | LXD through pylxd |
| Dashboard | Astro with client-side JavaScript |
| Application database | SQLite |
| Time-series metrics | TinyFlux |
| Backend server | Gunicorn |
| Process supervision | systemd |
| Static frontend and reverse proxy | Nginx |
| Authentication | Google OAuth 2.0 |

The project targets Ubuntu with LXD 5.x. It uses Python 3.10+ and Node.js 22.12+ for the current Astro frontend.

## 2. Features

### Admin

An Admin can:

- View all LXD containers and their resource metrics.
- Inspect host CPU, memory, storage and network information.
- Create managed containers with validated resource limits.
- Start, stop, restart, freeze and unfreeze containers.
- Update supported RAM, CPU and disk limits.
- Delete managed containers after confirmation.
- Invite, revoke, reactivate and manage users.
- Assign and revoke container access.
- Transfer managed-container ownership.
- Configure per-user resource quotas.
- View allocated resources against host capacity.
- Explicitly adopt eligible externally created containers.
- Execute commands inside authorized containers.
- View historical container metrics.

### Container User

A Container User can:

- View containers explicitly assigned to them.
- See their own resource quota and allocation.
- View current and historical metrics.
- Execute permitted commands inside accessible containers.

A Container User cannot create or manage containers through Admin endpoints.

## 3. Architecture

```text
                    Browser
                       |
                       v
                  Nginx / Astro
                       |
                 /api and /auth
                       |
                       v
                 Falcon Backend
                       |
           +-----------+-----------+
           |                       |
           v                       v
     Authentication          Application
     Authorization           Services
           |                       |
           v                       v
         SQLite             pylxd / LXD
                                   |
                                   v
                              Containers


              Independent systemd Service
                       |
                       v
                Metrics Collector
                       |
                 LXD Statistics
                       |
                       v
                     TinyFlux
                       |
                       v
              Historical Metrics API
```

The browser does not connect directly to LXD.

Falcon validates the authenticated user, their role, container access and resource limits before performing privileged operations.

The metrics collector is an independent process. It continues collecting when no browser is connected or when the Falcon API is restarted.

## 4. Repository Structure

```text
Hobby-Server-Monitor/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── auth/
│   │   ├── db/
│   │   ├── metrics/
│   │   ├── services/
│   │   ├── collector.py
│   │   ├── config.py
│   │   └── main.py
│   ├── tests/
│   └── requirements.txt
├── dashboard/
│   ├── src/
│   │   ├── components/
│   │   ├── lib/
│   │   └── pages/
│   ├── astro.config.mjs
│   └── package.json
├── deploy/
│   ├── nginx/
│   ├── systemd/
│   ├── scripts/
│   ├── hsm.env.example
│   └── README.md
├── docs/
│   ├── DECISIONS.md
│   └── PROJECT_SPEC.md
├── .env.example
├── README.md
├── REPORT.md
└── TODO.md
```

## 5. Development Setup

These instructions use native Ubuntu. WSL2 may also be used when LXD is configured correctly.

### 5.1 Install prerequisites

```bash
sudo apt update

sudo apt install -y \
  git \
  python3 \
  python3-venv \
  python3-pip \
  curl
```

Install Node.js 22.12 or newer and npm using an appropriate supported installation method.

Verify:

```bash
python3 --version
node --version
npm --version
```

### 5.2 Install and initialize LXD

Follow the official installation instructions:

https://documentation.ubuntu.com/lxd/

For Ubuntu with snap support:

```bash
sudo snap install lxd --channel=5.21/stable
```

If LXD is already installed, do not reinstall it.

For a minimal development configuration:

```bash
sudo lxd init --minimal
```

Verify:

```bash
lxc version
lxc info
lxc storage list
lxc network list
```

Container creation requires an appropriate storage pool and usable network.

If those do not exist, configure them using the LXD initialization procedure before creating containers.

The application uses LXD's default project.

**Security warning:** Membership in the local `lxd` group provides extensive privileges and may effectively allow host-level control. Only trusted administrators or the designated backend service account should receive this permission.

### 5.3 Obtain the project

```bash
git clone https://github.com/birajithk/Hobby-Server-Monitor.git

cd Hobby-Server-Monitor
```

Use the verified submission branch or `main` when the final implementation has been merged.

### 5.4 Create the backend environment

```bash
cd backend

python3 -m venv .venv

source .venv/bin/activate

python -m pip install -r requirements.txt

cd ..
```

### 5.5 Configure environment variables

From the repository root:

```bash
cp .env.example backend/.env
```

Generate a session secret:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Edit `backend/.env`:

```bash
nano backend/.env
```

Configure:

- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_REDIRECT_URI`
- `SESSION_SECRET`
- `BOOTSTRAP_ADMIN_EMAIL`
- `COOKIE_SECURE`

For the Astro development server, use:

```dotenv
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:4321/auth/google/callback
COOKIE_SECURE=false
```

Do not commit `backend/.env`.

The Falcon backend loads `backend/.env` through `backend/app/config.py`. Relative SQLite and TinyFlux paths are interpreted relative to the process working directory.

### 5.6 Configure Google OAuth

1. Open https://console.cloud.google.com/
2. Create or select a Google Cloud project.
3. Configure the Google Auth Platform consent screen.
4. Create an OAuth 2.0 client of type **Web application**.
5. Add the redirect URI:

```text
http://localhost:4321/auth/google/callback
```

6. Copy the client ID and client secret into `backend/.env`.
7. If the OAuth application is in Testing mode, add the intended Google account as a test user.
8. Set `BOOTSTRAP_ADMIN_EMAIL` to the Google email address intended for the first Admin.

The configured email is the only account permitted to perform the initial Admin bootstrap when no active Admin exists.

Other users must be invited by an Admin.

### 5.7 Initialize SQLite

From the `backend/` directory:

```bash
cd backend

source .venv/bin/activate

python -m app.db.init_db
```

The initializer creates the database if necessary and applies supported schema migrations.

It can also be run against an already initialized database.

### 5.8 Start the Falcon backend

Development only: Start Gunicorn manually only when the systemd-managed Falcon service is not already occupying port 8000. On an installed production deployment, the Falcon backend starts automatically through hobby-server-monitor-api.service. Do not run a second Gunicorn instance on the same port.

Terminal 1:

```bash
cd backend

source .venv/bin/activate

gunicorn \
  --bind 127.0.0.1:8000 \
  --workers 1 \
  app.main:app
```

Verify:

```bash
curl --fail http://127.0.0.1:8000/api/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "hobby-server-monitor-api"
}
```

### 5.9 Start the independent metrics collector

Terminal 2:

```bash
cd backend

source .venv/bin/activate

python -m app.collector
```

The collector polls LXD every 10 seconds by default.

To execute a single collection cycle:

```bash
python -m app.collector --once
```

The collector runs independently of the dashboard.

### 5.10 Start Astro

Terminal 3:

```bash
cd dashboard

npm ci

npm run dev
```

Open:

http://localhost:4321

The development server proxies `/api` and `/auth` requests to Falcon on port `8000`.

Sign in using the configured bootstrap Admin Google account.

## 6. Browser Usage

### Admin workflow

1. Sign in with Google.
2. Open the Admin dashboard.
3. Review host allocation and LXD container status.
4. Invite a Container User and configure their resource quota.
5. Create a managed container and select its owner.
6. Choose an approved Ubuntu image, storage pool and network.
7. Configure RAM, CPU, CPU allowance and disk.
8. Assign access to authorized users.
9. Inspect live metrics or historical charts.
10. Use the terminal for authorized container operations.

Container creation currently approves Ubuntu 24.04 as its image alias.

Storage pools and networks are validated against available LXD resources. Containers are created without inheriting arbitrary default-profile devices.

### Container User workflow

1. Sign in using an invited Google account.
2. View only explicitly assigned containers.
3. Inspect the user's resource quota.
4. Open an authorized container.
5. View its metrics or execute commands with the available restricted terminal.

An unassigned managed container must not become accessible merely by requesting its API identifier.

## 7. Authentication and Authorization

The application uses Google OAuth 2.0 for identity verification.

Google OAuth state and PKCE protect the authorization flow.

Falcon issues an application-controlled server-side session after the Google identity is verified and authorized.

Session cookies use `HttpOnly` and `SameSite=Lax`. The `Secure` flag is enabled for HTTPS deployments.

Sessions are stored in SQLite. Logging out revokes the server-side session.

Authentication middleware denies access by default unless an endpoint explicitly declares itself public.

Admin-only operations are enforced by role checks.

Container-specific operations also check the user's assignment or administrative privileges in the service layer.

State-changing requests require the application's `X-CSRF-Token` header.

## 8. Quota and Container Ownership Model

Each managed container has one owner.

The owner's allocated RAM, CPU cores and disk contribute to that user's quota.

For example, a container allocated 2 GiB of RAM consumes 2 GiB of its owner's quota even if it is currently using less memory.

Stopped containers still consume their configured allocations.

Additional access assignments do not consume the assigned user's quota.

Container creation, resource updates and ownership transfers validate quotas and applicable host capacity limits.

Externally created LXD containers are discovered for Admin visibility, but they are not automatically treated as application-managed containers.

Eligible external containers require explicit Admin adoption before being incorporated into application ownership and quota accounting.

## 9. Historical Metrics

The collector polls LXD independently every 10 seconds.

It stores raw observations in TinyFlux.

### Measurements

| TinyFlux measurement | Purpose |
| --- | --- |
| `container_raw` | Raw observations |
| `container_5m` | Aggregated five-minute observations |

### Raw tags

Raw metric tags include:

- `project`
- `lxd_name`
- `lxd_uuid`
- `managed`
- `container_id`
- `status`
- `state_available`
- `ipv4`
- `image_os`
- `image_version`

### Raw fields

Depending on container state and metric availability, fields include:

- `status_code`
- `cpu_usage_ns`
- `cpu_percent`
- `memory_usage_bytes`
- `memory_total_bytes`
- `disk_usage_bytes`
- `disk_total_bytes`
- `rx_bytes`
- `tx_bytes`
- `rx_bytes_per_second`
- `tx_bytes_per_second`
- `packets_rx`
- `packets_tx`
- `processes`
- `pid`
- `uptime_seconds`

Some values may be absent when a container is stopped or LXD cannot return its runtime state.

### Retention

The default raw-metric retention period is 24 hours.

Five-minute aggregates are retained for 30 days.

Retention cleanup runs when the collector starts and periodically during collection.

Historical API ranges are:

| Range | Chart resolution |
| --- | --- |
| 1 hour | 10 seconds |
| 6 hours | 60 seconds |
| 24 hours | 5 minutes |
| 7 days | 30 minutes |
| 30 days | 2 hours |

The API returns chart-ready data rather than transmitting every raw sample for long-duration charts.

## 10. SQLite Data Model

The application uses SQLite with schema version 2.

| Table | Purpose |
| --- | --- |
| `users` | Google identity, role, status and resource quotas |
| `containers` | Managed container identity, owner and allocated limits |
| `container_access` | Additional user-to-container assignments |
| `sessions` | Hashed session tokens, CSRF hashes and expiration |
| `audit_logs` | Administrative and security-relevant action records |
| `oauth_flows` | Short-lived OAuth state, PKCE and nonce tracking |

Important relationships:

- `containers.owner_id` references `users.id`.
- `container_access` references both containers and users.
- Deleting a container cascades its additional access assignments.
- A container owner cannot be deleted while ownership dependencies remain.
- Audit records can retain an email snapshot after an actor is removed.

Exact definitions are in:

- `backend/app/db/schema.sql`
- `backend/app/db/migrations/002_auth.sql`

Database initialization is implemented in:

`backend/app/db/init_db.py`

## 11. API Reference

All paths below are relative to the Falcon API.

`Public` means no application session is required. Other endpoints require an authenticated session.

For state-changing requests, send a valid session cookie and `X-CSRF-Token`.

### Authentication

| Method | Endpoint | Permission | Description |
| --- | --- | --- | --- |
| GET | `/api/health` | Public | Backend health |
| GET | `/auth/google/login` | Public | Start Google login |
| GET | `/auth/google/callback` | Public | Complete OAuth flow |
| GET | `/api/me` | Authenticated | Current user and CSRF token |
| POST | `/auth/logout` | Authenticated | Revoke current session |

Example `/api/me` response structure:

```json
{
  "user": {
    "id": "<user-id>",
    "email": "admin@example.com",
    "name": "Example Admin",
    "role": "admin"
  },
  "csrf_token": "<csrf-token>"
}
```

### Users and resource quotas

| Method | Endpoint | Permission | Description |
| --- | --- | --- | --- |
| POST | `/api/admin/invitations` | Admin | Invite Container User |
| GET | `/api/admin/users` | Admin | List users |
| GET | `/api/admin/users/{user_id}` | Admin | Get user details |
| DELETE | `/api/admin/users/{user_id}` | Admin | Delete eligible user |
| PATCH | `/api/admin/users/{user_id}/role` | Admin | Change role |
| POST | `/api/admin/users/{user_id}/revoke` | Admin | Revoke user |
| POST | `/api/admin/users/{user_id}/reactivate` | Admin | Reactivate Container User |
| PUT | `/api/admin/users/{user_id}/quota` | Admin | Update quota |
| GET | `/api/me/quota` | Authenticated | Own quota and allocations |

Example invitation request:

```json
{
  "email": "user@example.com",
  "quota_ram_bytes": 2147483648,
  "quota_cpu_cores": 2,
  "quota_disk_bytes": 10737418240
}
```

A successful invitation returns HTTP 201 with the user's ID, email, role, invitation status and configured quotas.

### Containers

| Method | Endpoint | Permission | Description |
| --- | --- | --- | --- |
| GET | `/api/containers` | Authenticated | List visible containers |
| GET | `/api/containers/{container_id}` | Assigned user or Admin | Container details |
| POST | `/api/admin/containers` | Admin | Create managed container |
| POST | `/api/admin/containers/adopt` | Admin | Adopt eligible external container |
| POST | `/api/admin/containers/{container_id}/actions` | Admin | Lifecycle action |
| DELETE | `/api/admin/containers/{container_id}` | Admin | Delete managed container |
| GET | `/api/admin/containers/{container_id}/resources` | Admin | Read saved resource limits |
| PATCH | `/api/admin/containers/{container_id}/resources` | Admin | Update resource limits |

Example container creation request:

```json
{
  "name": "demo-container",
  "owner_id": "<existing-user-id>",
  "image_alias": "24.04",
  "ram_limit_bytes": 1073741824,
  "cpu_limit_cores": 2,
  "cpu_allowance_percent": 100,
  "disk_limit_bytes": 10737418240,
  "storage_pool": "<available-pool>",
  "network_name": "<available-network>",
  "ephemeral": false,
  "autostart": false,
  "description": "Testing container"
}
```

Container creation validates every field and returns HTTP 201 on success.

Lifecycle action request:

```json
{
  "action": "restart"
}
```

The endpoint also supports the implemented start, stop, freeze and unfreeze actions.

Resource update request:

```json
{
  "ram_limit_bytes": 2147483648,
  "cpu_limit_cores": 2,
  "cpu_allowance_percent": 100,
  "disk_limit_bytes": 10737418240
}
```

Managed disk shrinking is deliberately rejected.

### Access assignments

| Method | Endpoint | Permission | Description |
| --- | --- | --- | --- |
| GET | `/api/admin/containers/{container_id}/access` | Admin | List assignments |
| POST | `/api/admin/containers/{container_id}/access/{user_id}` | Admin | Assign access |
| DELETE | `/api/admin/containers/{container_id}/access/{user_id}` | Admin | Revoke access |
| POST | `/api/admin/containers/{container_id}/transfer-owner` | Admin | Transfer ownership |

### Metrics and terminal

| Method | Endpoint | Permission | Description |
| --- | --- | --- | --- |
| GET | `/api/containers/{container_id}/metrics/latest` | Assigned user or Admin | Latest observation |
| GET | `/api/containers/{container_id}/metrics/history?range=1h` | Assigned user or Admin | Historical observations |
| POST | `/api/containers/{container_id}/exec` | Assigned user or Admin | Execute container command |

Example terminal request:

```json
{
  "command": "whoami"
}
```

The response includes execution results, duration and the container execution identity.

The terminal is non-interactive. It is not unrestricted host shell access.

### Host and accounting

| Method | Endpoint | Permission | Description |
| --- | --- | --- | --- |
| GET | `/api/admin/host` | Admin | LXD host information |
| GET | `/api/admin/allocations` | Admin | Host allocation overview |

### Error handling

Common responses include:

- `400 Bad Request` — malformed or invalid input.
- `401 Unauthorized` — missing or expired session.
- `403 Forbidden` — insufficient role or container access.
- `404 Not Found` — missing application resource.
- `409 Conflict` — an incompatible state or quota conflict.
- `503 Service Unavailable` — required backend or LXD information unavailable.

Specific response fields and failure conditions are defined by the Falcon resources and service implementations under `backend/app/`.

## 12. Environment Variables

| Variable | Purpose |
| --- | --- |
| `GOOGLE_OAUTH_CLIENT_ID` | Google OAuth client identifier |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google OAuth client secret |
| `GOOGLE_OAUTH_REDIRECT_URI` | Exact OAuth callback URI |
| `SESSION_SECRET` | Key used for session-token hashing and CSRF derivation |
| `SESSION_LIFETIME_SECONDS` | Application session expiration |
| `COOKIE_SECURE` | Require HTTPS for session cookies |
| `BOOTSTRAP_ADMIN_EMAIL` | Explicit initial Admin identity |
| `SQLITE_DB_PATH` | SQLite database location |
| `TINYFLUX_DB_PATH` | TinyFlux storage location |
| `HOST_RAM_RESERVE_BYTES` | Host RAM kept unavailable for container allocation |
| `HOST_CPU_RESERVE_THREADS` | Reserved logical CPU threads |
| `HOST_DISK_RESERVE_BYTES` | Reserved host storage capacity |
| `VERIFIED_DISK_QUOTA_POOLS` | Comma-separated pools approved for disk quota enforcement |
| `METRICS_INTERVAL_SECONDS` | Collector polling interval |
| `METRICS_RAW_RETENTION_HOURS` | Raw metrics retention |
| `TERMINAL_CONTAINER_USER` | Restricted in-container execution account |
| `TERMINAL_MAX_COMMAND_LENGTH` | Maximum submitted command length |
| `TERMINAL_MAX_OUTPUT_BYTES` | Maximum output bytes per captured stream |
| `TERMINAL_TIMEOUT_SECONDS` | Maximum command execution duration |
| `TERMINAL_MAX_CONCURRENT_EXECS` | Maximum simultaneous container exec operations |

The default values and development settings are provided in `.env.example`.

The production template is `deploy/hsm.env.example`.

Production configuration uses absolute database paths and a root-owned environment file with permission `0600`.

## 13. Production Deployment

The tested deployment uses:

- Dedicated Linux service account: `hsm`.
- Source installation: `/opt/hobby-server-monitor/backend`.
- Persistent state: `/var/lib/hobby-server-monitor`.
- Protected configuration: `/etc/hobby-server-monitor/hsm.env`.
- Static Astro files: `/srv/hobby-server-monitor/www`.
- Falcon systemd service: `hobby-server-monitor-api`.
- Collector systemd service: `hobby-server-monitor-collector`.
- Database initializer: `hobby-server-monitor-db-init`.
- Nginx for HTTPS and same-origin API routing.

See [deploy/README.md](deploy/README.md) for the deployment architecture, paths, service configuration, tested restart behavior and verification evidence.

### Rebuilding Astro

```bash
cd dashboard

npm ci
npm run build
```

Install the build into the configured Nginx static directory using the deployment procedure.

### Service commands

```bash
sudo systemctl status hobby-server-monitor-api
sudo systemctl status hobby-server-monitor-collector
sudo systemctl status nginx
```

Logs:

```bash
sudo journalctl -u hobby-server-monitor-api -n 50 --no-pager
sudo journalctl -u hobby-server-monitor-collector -n 50 --no-pager
```

Test HTTPS health:

```bash
curl --fail https://localhost:8443/api/health
```

The localhost HTTPS configuration uses a locally trusted mkcert certificate and is intended for testing on the same machine.

Remote deployment requires an appropriate hostname and trusted HTTPS certificate.

### Deployment verification

The following were verified on Ubuntu:

- Static Astro deployment through Nginx.
- Falcon and collector startup through systemd.
- Independent collector execution.
- Automatic Falcon recovery after process termination.
- Automatic collector recovery after process termination.
- Automatic service startup after a host reboot.
- SQLite and TinyFlux persistence.
- Locally trusted HTTPS API and frontend access.
- Production Admin bootstrap.
- Resource benchmarking.

Verification details are maintained in `deploy/README.md` and `REPORT.md`.

## 14. Security Model

### Main trust boundaries

1. The browser is an untrusted client.
2. The Falcon backend enforces authentication and authorization.
3. The Falcon service accesses the privileged local LXD socket.
4. LXD performs actual container operations.
5. Managed containers remain separate from the host application.

### Controls

- Google OAuth identity verification.
- Explicit Admin bootstrap email.
- Invitation-based access for ordinary users.
- Server-side sessions with revocation and expiration.
- CSRF protection for state-changing requests.
- Admin role checks and container-level authorization.
- Strict server-side validation.
- Quota and host capacity validation.
- Restricted non-root container terminal identity.
- Command length, execution-time and output limits.
- Auditing of privileged operations.
- Secure handling of OAuth and session secrets.
- Reverse-proxy TLS for authenticated production access.

### Residual risks

Local LXD administrator access is highly privileged and can effectively provide host-level control.

Running Falcon under a separate Linux service account limits ordinary filesystem access but does not eliminate the risk associated with access to the LXD administrative socket.

The terminal provides real command execution inside containers. It is restricted to authorized containers and an in-container non-root identity, but it is not a complete sandbox against every possible container or kernel vulnerability.

See [docs/DECISIONS.md](docs/DECISIONS.md) for the architecture rationale.

## 15. Testing

Run backend tests:

```bash
cd backend

source .venv/bin/activate

python -m unittest discover -s tests -v
```

Build frontend:

```bash
cd dashboard

npm ci
npm run build
```

Deployment verification:

```bash
./deploy/scripts/verify-reboot.sh
```

Resource benchmarking:

```bash
sudo python3 deploy/scripts/measure-resources.py no-tabs 60
sudo python3 deploy/scripts/measure-resources.py one-tab 60
sudo python3 deploy/scripts/measure-resources.py three-tabs 60
```

Run deployment scripts from the repository root.

### Continuous integration and verified optional features

GitHub Actions (`.github/workflows/ci.yml`) runs Falcon tests on
Python 3.12, Ruff critical checks, an Astro build on Node.js 22,
and repository/shell-script checks. The CSV-export feature commit
`bb60cd69` passed the full CI workflow on 2026-10-08.
Mocked LXD-dependent unit tests supplement, but do not replace,
manual verification with real LXD on Ubuntu.

The Admin can explicitly adopt eligible unmanaged LXD containers and
assign ownership through **Manage containers → Adopt external**.
The Falcon endpoint enforces Admin access, quota/hardware limits,
and safe LXD configuration checks before recording ownership.

**Container Details → Export CSV** downloads authorized historical
TinyFlux chart data for the selected range. The server enforces the
same container access rules as JSON history; larger ranges may be
aggregated. CSV-formula injection is mitigated.

On an already-provisioned Ubuntu host, `deploy/scripts/install-systemd-units.sh`
checks/reconciles units, while `deploy/scripts/update-application.sh`
stages compatible code-only releases and retains rollback copies.
Both support `--check` before `--apply`; neither replaces a
fresh-host provisioning procedure. See `deploy/README.md`.

## 16. Measured Resource Footprint

Resource measurements were collected on Ubuntu 24.04.4 LTS with an Intel Core i9-11900H, 16 logical CPU threads, approximately 15.4 GiB RAM and three LXD containers.

Each scenario ran for approximately 60 seconds.

| Scenario | Combined average service RAM | Combined service CPU |
| --- | ---: | ---: |
| No browser tabs | 99.30 MiB | 0.318% |
| One dashboard tab | 100.24 MiB | 0.552% |
| Three dashboard tabs | 102.18 MiB | 0.496% |

The memory figures are sums of systemd control-group memory readings for Falcon, the metrics collector and Nginx.

CPU percentages use one logical CPU as 100%.

The complete measurement commands, per-service figures, storage growth and limitations are documented in [REPORT.md](REPORT.md).

## 17. Known Limitations

- Container creation currently restricts images to the approved Ubuntu 24.04 alias.
- Arbitrary inherited LXD profiles are deliberately not supported during managed-container creation.
- The implementation currently targets the LXD default project.
- Arbitrary container renaming is not implemented.
- Managed root-disk shrinking is rejected.
- The terminal is non-interactive rather than a full PTY shell.
- The deployment was verified using localhost HTTPS; externally accessible HTTPS hosting still requires site-specific configuration.
- Long-duration storage behavior has not been benchmarked for a full month.
- Resource benchmarks are short measurements from one development machine.
- LXD privilege separation remains a significant residual security consideration.
- A dedicated, separately isolated LXD operations broker is not implemented.

Additional outstanding work and unverified cases are tracked in `TODO.md`.

## 18. Documentation

- [Deployment and recovery evidence](deploy/README.md)
- [Architecture and design decisions](docs/DECISIONS.md)
- [Security threat model](docs/THREAT_MODEL.md)
- [Project specification](docs/PROJECT_SPEC.md)
- [Final report and resource benchmarks](REPORT.md)
- [Implementation and verification checklist](TODO.md)

Repository:

https://github.com/birajithk/Hobby-Server-Monitor

