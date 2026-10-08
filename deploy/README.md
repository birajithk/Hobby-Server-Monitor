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

### Collector automatic recovery test

Status: PASSED

Verification date: 2026-10-08

The independent TinyFlux collector was tested for
automatic recovery after unexpected process failure.

The collector runs under the systemd service:

hobby-server-monitor-collector.service

Its restart policy is:

- Restart=on-failure
- RestartSec=5

#### Test procedure

1. Confirmed that the collector was running.
2. Recorded its main process ID and restart count.
3. Recorded the test start time.
4. Terminated the collector's main process using SIGKILL.
5. Allowed systemd to restart the failed service.
6. Verified that the service returned to active status.
7. Verified that the main PID changed and restart count increased.
8. Checked systemd journal logs for recovery events.
9. Queried the production TinyFlux database for measurements
   created after the crash test began.
10. Verified that recent measurements were present.
11. Confirmed the Falcon API remained available.

#### Failure simulation

sudo systemctl kill \
  --kill-who=main \
  --signal=SIGKILL \
  hobby-server-monitor-collector

#### Results

PASS — systemd restarted the collector automatically.

PASS — Collector returned to active status.

PASS — Collector started with a new main process ID.

PASS — systemd restart counter increased.

PASS — Collector resumed writing measurements to TinyFlux.

PASS — Recent TinyFlux measurement timestamps were verified.

PASS — Falcon API remained operational.

#### Engineering conclusion

The independent metrics collector can recover from an
unexpected process termination without requiring manual
intervention or a restart of the Falcon API.

This satisfies process-level collector restart verification.

The test does not establish host-reboot recovery or recovery
from every possible LXD failure. Those remain separate
verification requirements.

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

### Host reboot recovery verification

Status: PASSED

Verification date: 2026-10-08

The complete Hobby Server Monitor deployment was
tested for automatic recovery following an Ubuntu
host reboot.

#### Test procedure

1. Verified Falcon, collector and Nginx were enabled.
2. Recorded the system boot ID and startup time.
3. Recorded pre-reboot SQLite and TinyFlux state.
4. Rebooted the Ubuntu host.
5. Did not manually start any application services.
6. Verified the new system boot ID.
7. Confirmed systemd initialized the application database.
8. Confirmed Falcon started automatically.
9. Confirmed the independent collector started automatically.
10. Confirmed Nginx started automatically.
11. Verified direct and reverse-proxied API health.
12. Verified the static Astro dashboard.
13. Confirmed SQLite records persisted.
14. Confirmed TinyFlux retained historical data and
    resumed collecting new measurements.

#### Results

PASS — Falcon started after host reboot.

PASS — Collector started after host reboot.

PASS — Nginx started after host reboot.

PASS — Database initialization completed successfully.

PASS — API health checks succeeded.

PASS — Static Astro dashboard was accessible.

PASS — SQLite data persisted across reboot.

PASS — TinyFlux measurements persisted and new
measurements were collected.

#### Engineering conclusion

The deployed application recovers automatically
after an operating-system reboot without requiring
manual startup commands.

The collector operates independently of the API
and frontend.

This verifies host-level restart and persistence
behavior on the tested Ubuntu environment.

Authenticated browser access through HTTPS
remains a separate production verification task.

### Local HTTPS and Google OAuth verification

Verification date: 2026-10-08

Environment:

- Ubuntu 24.04
- Nginx with local HTTPS on port 8443
- mkcert locally trusted development certificate
- systemd-managed Falcon API
- Production SQLite database
- Secure session cookies

#### HTTPS verification

Status: PASSED

The local Nginx HTTPS endpoint was configured
using a certificate generated by mkcert for
localhost and 127.0.0.1.

The certificate is stored outside the Git repository.

Verified file permissions:

- TLS directory: root:root, 0700
- Certificate: root:root, 0644
- Private key: root:root, 0600

The following checks passed:

- Nginx configuration syntax validation.
- Nginx reload without configuration failure.
- HTTPS Falcon health request returned HTTP 200.
- HTTPS static Astro dashboard returned HTTP 200.
- curl verified the trusted certificate without
  disabling TLS certificate validation.

The development certificate is trusted locally,
not by arbitrary remote computers.

This configuration is only accessible through
the loopback interface and is not a publicly
accessible production HTTPS deployment.

#### Google OAuth configuration

Status: PASSED

The Google Cloud OAuth client was configured with
the exact authorized redirect URI:

https://localhost:8443/auth/google/callback

The protected production environment was updated
to use the same callback URI.

The following configuration checks passed:

- Google OAuth client ID present.
- Google OAuth client secret present.
- Redirect URI matched the HTTPS callback.
- Bootstrap Admin email configured.
- Secure session cookies enabled.
- Session secret met the minimum length requirement.

Actual credentials and secrets remain outside
the Git repository.

#### Production Admin bootstrap

Status: PASSED

The deployed SQLite database was initially
created without application users.

After configuring Google OAuth and completing
the Admin bootstrap workflow, the database
contained:

- Active Admin accounts: 1

The following database verification passed:

PASS: Production Admin account exists.

The Falcon API remained active and returned
a healthy response through the HTTPS endpoint.

#### Security and deployment decisions

The bootstrap Admin is identified using the
explicit BOOTSTRAP_ADMIN_EMAIL environment variable.

Users without an invitation must not gain access
merely by authenticating with Google.

The application's authorization decisions remain
inside the Falcon backend rather than Nginx.

Nginx handles TLS termination and reverse proxying,
not application-level role authorization.

#### Remaining verification

- Confirm an uninvited Google account is denied
  access on the deployed instance.
- Verify authenticated remote-browser operation
  using a deployment hostname and trusted TLS
  certificate, if a suitable hostname is available.
- Complete final browser-level authorization and
  error-state testing.

The locally trusted HTTPS configuration is not
equivalent to an externally accessible production
TLS deployment.

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

The Ubuntu development host has verified localhost HTTPS browser
access, independent collector persistence, service recovery after
SIGKILL/reboot, and short-window CPU/RAM measurements in REPORT.md.
On 2026-10-08, the code-only updater completed and the installed
systemd units, Nginx, Falcon API, protected environment permissions,
SQLite and TinyFlux were checked; the collector's metrics were fresh.

The following remain unverified or incomplete:

- Remote HTTPS access using a publicly trusted site certificate.
- Fully independent clean-host provisioning and README walkthrough.
- Long-duration metric-storage growth and large-scale load behavior.
- A controlled LXD daemon outage/recovery benchmark and additional
  hostile-input/privilege-boundary testing.

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
resource measurements are documented in REPORT.md.

## 13. Guarded Updates on an Existing Host

`deploy/scripts/install-systemd-units.sh` checks the installed
Falcon, collector and database initialization unit definitions.
`--check` is read-only. `--apply` backs up modified units, installs
the new versions and runs `systemctl daemon-reload`, but does not
restart services or touch LXD, the database or protected credentials.
Both modes were tested on 2026-10-08, with all units unchanged.

`deploy/scripts/update-application.sh` updates Falcon application
code and static Astro files on an already-provisioned host. It
rejects changed Python requirements and database schema/migration
code: those require a separately reviewed upgrade. It stages and
checks new files before briefly restarting the API and collector;
previous application files are retained as rollback copies. It
never copies secrets, SQLite, TinyFlux, systemd units or LXD config.

From the repository root, after building Astro as the normal user:

```bash
cd dashboard && npm ci && npm run build && cd ..
sudo bash deploy/scripts/install-systemd-units.sh --check
sudo bash deploy/scripts/update-application.sh --check
# Review any reported differences before using --apply.
sudo bash deploy/scripts/update-application.sh --apply
sudo bash deploy/scripts/check-deployment.sh
sudo bash deploy/scripts/verify-reboot.sh
```

The existing-host updater and browser login/metrics should be
rechecked following code changes. The scripts do not provide an
end-to-end tested clean-host installation or public TLS setup.
