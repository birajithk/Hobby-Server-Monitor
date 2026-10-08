# Hobby Server Monitor — Deployment

## 1. Overview

Hobby Server Monitor is deployed on a single Ubuntu
Linux host using LXD for container management.

The deployment uses:

- Nginx to serve the static Astro dashboard and
  reverse-proxy requests to Falcon.
- Gunicorn to run the Falcon backend.
- systemd to supervise application processes.
- An independent Python metrics collector.
- SQLite for application state.
- TinyFlux for historical container metrics.

The application is designed to remain lightweight
because it runs on the same host it monitors.

## 2. Deployment Architecture

Browser
    |
    v
Nginx
    |
    +-- Static Astro dashboard
    |
    +-- /api/  --> Falcon / Gunicorn
    |
    +-- /auth/ --> Falcon / Gunicorn

Falcon
    |
    +-- SQLite
    +-- LXD

Independent Collector
    |
    +-- LXD
    +-- TinyFlux
    +-- SQLite (managed-container lookup)

The collector runs independently of Falcon and
does not depend on open dashboard sessions.

## 3. Production File Locations

Application backend:
  /opt/hobby-server-monitor/backend

Production virtual environment:
  /opt/hobby-server-monitor/backend/.venv

Production configuration:
  /etc/hobby-server-monitor/hsm.env

Application SQLite database:
  /var/lib/hobby-server-monitor/app.db

TinyFlux metrics database:
  /var/lib/hobby-server-monitor/metrics.csv

Static Astro files:
  /srv/hobby-server-monitor/www

systemd units:
  /etc/systemd/system/

Nginx site configuration:
  /etc/nginx/sites-available/hobby-server-monitor

## 4. Linux Service Account

A dedicated Linux service account named hsm is
used for the Falcon API and metrics collector.

The account:

- Has no interactive login shell.
- Owns the persistent application data directory.
- Has membership in the lxd group.
- Runs application services without using root
  as the process user.

The local LXD administrative socket is owned
by root:lxd with permissions 660 on the tested host.

Security limitation:

Membership in the lxd group provides extensive
privileged access to LXD and can effectively
provide host-level control.

The dedicated account does not eliminate this
privilege risk.

Falcon therefore remains a trusted and sensitive
component. Authentication, authorization, CSRF
protection and input validation remain essential.

A separately isolated LXD broker is not included
in the current architecture.

## 5. systemd Services

Three units are provided.

### Database initialization

hobby-server-monitor-db-init.service

This is a oneshot service.

It executes the existing application database
initialization and migration logic.

It completes before the long-running application
services start.

### Falcon API

hobby-server-monitor-api.service

Runs one Gunicorn worker bound to:

127.0.0.1:8000

The service uses:

- Restart=on-failure
- RestartSec=5
- TimeoutStopSec=30
- A protected application environment
- A dedicated service account
- Restricted filesystem write access

The API is not directly exposed on a public
network interface.

One worker is an initial resource-conscious
choice. Performance and responsiveness still
need to be measured under load.

### Metrics collector

hobby-server-monitor-collector.service

Executes:

python -m app.collector

The collector operates independently from
the API and frontend.

It polls LXD according to the configured
METRICS_INTERVAL_SECONDS value.

The deployment default is 10 seconds.

Collector failures during an individual
collection cycle are logged. The existing
collector loop attempts future cycles.

systemd is also configured to restart the
collector process if it exits with a failure.

## 6. Frontend Deployment

Astro is compiled into static HTML, JavaScript
and CSS.

Build command:

cd dashboard
npm ci
npm run build

The generated dist directory is copied to:

/srv/hobby-server-monitor/www

Nginx serves these static assets directly.

No Astro development server is required
in production.

This removes a continuously running Node.js
development process from the deployment.

## 7. Nginx Configuration

The local verification configuration binds to:

127.0.0.1:8080

Routes:

/       -> Astro static files
/api/   -> Falcon
/auth/  -> Falcon

The local HTTP configuration is intended only
for deployment verification.

Production access from other machines requires
HTTPS with a trusted certificate and a matching
Google OAuth redirect URI.

The HTTPS configuration template must not be
enabled with placeholder certificate paths.

COOKIE_SECURE=true is required for the
production HTTPS configuration.

## 8. Production Configuration

Production environment variables are stored in:

/etc/hobby-server-monitor/hsm.env

The production file is owned by root with
permissions 0600.

It contains OAuth configuration, the session
secret, persistent database paths, quotas,
collector settings and terminal limits.

Real credentials must never be committed
to Git.

The committed deploy/hsm.env.example file
contains placeholders only.

## 9. Deployment Verification

Verification date: 2026-10-08

Environment:

- Ubuntu 24.04 development host
- Local LXD 5.x installation
- Falcon API
- Astro static dashboard
- Nginx
- systemd
- SQLite
- TinyFlux

### Completed smoke tests

PASS — Required Ubuntu packages installed.

PASS — LXD socket permissions verified.

PASS — Dedicated hsm account created.

PASS — Production application directories created.

PASS — Production backend dependencies installed.

PASS — Falcon, pylxd and TinyFlux imports verified.

PASS — Astro static build completed successfully.

PASS — Seven Astro pages generated.

PASS — Production database initialization succeeded.

PASS — Independent collector service started.

PASS — Nginx configuration syntax verification passed.

PASS — Falcon service became active after resolving
a development-server port conflict.

PASS — Direct Falcon health endpoint returned HTTP 200.

PASS — Nginx-proxied Falcon health endpoint returned
HTTP 200.

PASS — Nginx returned HTTP 200 for the static dashboard.

PASS — Falcon, collector and Nginx services reported
active status.

### Falcon automatic recovery test

Status: PASSED

The Falcon Gunicorn master process was deliberately
terminated using SIGKILL through systemd.

Test command:

sudo systemctl kill \
  --kill-who=main \
  --signal=SIGKILL \
  hobby-server-monitor-api

After the configured restart delay, systemd
successfully restarted the Falcon service.

Verification included:

- Service returned to active status.
- A new Gunicorn master process was started.
- The systemd restart counter increased.
- The Nginx-proxied API health endpoint succeeded.

This confirms automatic Falcon service recovery
after an unexpected master-process termination.

The test was performed on the local deployment
and reported as passed on 2026-10-08.

### Issue encountered during deployment

The first attempt to start the Falcon systemd
service failed because an earlier manually started
Gunicorn development server was still occupying
TCP port 8000.

Resolution:

1. Stop the old development Gunicorn process.
2. Restart the systemd-managed Falcon service.
3. Confirm the service is active.
4. Verify the Falcon health endpoint.

The systemd-managed service then started successfully.

### Session secret handling

A session secret was inadvertently displayed
in terminal output during deployment.

The secret was subsequently rotated in the
protected production environment file.

The Falcon service was restarted after rotation.

No secret values are recorded in this document.

## 10. Operational Commands

Check API status:

sudo systemctl status hobby-server-monitor-api

Check collector status:

sudo systemctl status hobby-server-monitor-collector

Check API logs:

sudo journalctl -u hobby-server-monitor-api \
  -n 50 --no-pager

Check collector logs:

sudo journalctl -u hobby-server-monitor-collector \
  -n 50 --no-pager

Check direct API health:

curl --fail http://127.0.0.1:8000/api/health

Check reverse-proxy API health:

curl --fail http://127.0.0.1:8080/api/health

Check static frontend:

curl --fail -I http://127.0.0.1:8080/

## 11. Remaining Deployment Verification

The following checks remain open until tested:

- Automatic collector process recovery after
  an unexpected process failure.
- Full verification of collector independence
  while Falcon is stopped.
- Service recovery following a host reboot.
- Authenticated Google OAuth login through
  production HTTPS.
- End-to-end browser verification through Nginx.
- Actual CPU and RAM benchmark measurements.
- Long-duration metric storage growth measurements.
- Additional service failure and permission tests.

These must not be reported as passed without
actual verification.

## 12. Deployment Design Decisions

systemd was selected because it integrates with
Ubuntu, supports automatic restart policies,
provides service dependencies and centralizes
process logs through journald.

Nginx was selected to serve the compiled Astro
application efficiently and provide a single
reverse-proxy entry point.

A single Gunicorn worker was selected initially
to limit idle memory usage.

The collector was deployed as an independent
systemd service so metric collection does not
depend on the browser or API lifecycle.

Persistent application data was separated from
application source code to support upgrades
without replacing the SQLite or TinyFlux files.

Alternative approaches, limitations and
resource measurements will be discussed in
the final REPORT.md.
