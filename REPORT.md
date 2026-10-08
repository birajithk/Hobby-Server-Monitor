# Final Report — Hobby Server Monitor

Software Engineer Intern Task — RoboticGen

Repository: https://github.com/birajithk/Hobby-Server-Monitor

Report date: October 8, 2026

## Project Summary

Hobby Server Monitor is a single-host, on-premises LXD container
management and monitoring application.

It provides a browser dashboard, Google authentication, role-based
authorization, container management, resource quotas, historical
monitoring, user management and container command execution.

The implementation uses a Falcon backend, an Astro frontend,
pylxd, SQLite, TinyFlux, Gunicorn, Nginx and systemd.

The main engineering priorities were security, correctness and
resource efficiency. This report distinguishes implemented features
from actual verification results and outstanding limitations.

## Time Spent

The following values must be completed using the developer's own
approximate working-time estimates before submission.

| Area | Approximate time |
| --- | ---: |
| Backend (API, authentication, authorization) | 15 hours |
| Dashboard (Astro frontend) | 11 hours |
| LXD integration and container operations | 12 hours |
| Background collector and TinyFlux | 7 hours |
| Testing, debugging and deployment | 15 hours |
| Documentation and final report | 5 hours |
| **Total** | **65 hours** |

These values are approximate active development hours, not elapsed
calendar time.

## Key Decisions

### 1. Explicit Admin bootstrap and Google OAuth

**Choice:** Google OAuth verifies identity. The first Admin is
authorized only when the verified Google email matches the configured
BOOTSTRAP_ADMIN_EMAIL and no active Admin already exists.

Subsequent Container Users require invitations.

**Alternatives considered:** Allow the first visitor to become Admin;
implement passwords directly in the application.

**Rationale:** The first-visitor approach is vulnerable to accidental
or malicious privilege assignment. A custom password system would
require additional credential storage, recovery and security work.

**Tradeoff:** Google OAuth requires external Google availability,
correct redirect-URI configuration and managed client credentials.

### 2. Server-side sessions and deny-by-default authorization

**Choice:** Use SQLite-backed sessions with hashed session tokens,
expiration, revocation and CSRF protection.

Falcon middleware authenticates protected requests and enforces
declared Admin-only requirements. Service-layer checks enforce
operation-specific and container-specific permissions.

**Alternatives considered:** Stateless client-managed tokens;
authorization implemented only through hidden dashboard controls.

**Rationale:** Server-side sessions can be revoked. Authorization in
the Falcon backend prevents users from bypassing UI restrictions by
calling an API endpoint directly.

**Tradeoff:** The database must be available for authenticated
requests, and session state requires maintenance.

### 3. Allocated-resource quotas rather than usage-based quotas

**Choice:** User quotas account for the configured RAM, CPU and disk
limits assigned to owned containers, including stopped containers.

Shared access does not duplicate ownership allocation.

**Alternative considered:** Charge users only for instantaneous
CPU, memory and disk usage.

**Rationale:** Actual usage fluctuates, making instantaneous quotas
unsuitable for reserving capacity and avoiding over-allocation.

**Tradeoff:** Reserved capacity can remain unused. A stopped
container still consumes its owner's allocation budget.

Changes are checked against user quotas and applicable host
resource limits before being applied.

### 4. Application container IDs and explicit external adoption

**Choice:** Track application-managed containers using stable
application identifiers with ownership and access records in SQLite.

LXD containers created outside the application are discoverable but
are not silently adopted into its ownership and quota model.

An Admin can explicitly adopt eligible external containers.

**Alternatives considered:** Treat the LXD name as the only identity;
automatically manage every discovered LXD container.

**Rationale:** Names can change and external containers may have
configurations or owners unknown to the application. Automatic
management would create authorization and accounting risks.

**Tradeoff:** Adoption requires validation and an explicit Admin
action. The system currently targets the default LXD project.

### 5. Privileged LXD access through a controlled Falcon service

**Choice:** The Falcon backend accesses the local LXD administrative
socket through pylxd, running under a dedicated Linux service account.

The browser cannot reach the LXD socket directly. The application
exposes a constrained set of authorized LXD operations.

**Alternatives considered:** Give ordinary users LXD socket access;
use a separate isolated privileged operations broker.

**Rationale:** Ordinary users must not receive unrestricted host
container-management privileges. A service layer makes input
validation, permission checks and auditing possible.

**Critical residual risk:** Access to the unrestricted local LXD
administrative socket is effectively host-root-equivalent.
Running Falcon as a non-root service account does not remove that
risk if the account can use the LXD administrative socket.

A separately isolated and restricted operations broker would
provide a stronger future privilege boundary.

### 6. Restricted non-interactive terminal

**Choice:** Provide real, non-interactive command execution inside
authorized running containers.

Container Users execute through a provisioned non-root container
identity. The application validates container access and restricts
command length, timeout, output size and simultaneous execution.

Admin execution may use root inside the selected container.

Execution intent and metadata are audited without storing raw
command content or full output by default.

**Alternative considered:** A persistent interactive WebSocket/PTY
terminal.

**Rationale:** Non-interactive execution supports useful commands
with less complexity and a smaller interactive attack surface.

**Tradeoff:** Full-screen applications, persistent shells and
interactive terminal programs are not supported. Container shell
commands remain inherently sensitive and depend on isolation and
authorization being correct.

### 7. Independent TinyFlux metrics collector

**Choice:** Poll LXD every 10 seconds using an independent collector
process, store raw observations in TinyFlux and build five-minute
aggregates for longer chart ranges.

Raw metrics are configured for 24-hour retention, with five-minute
aggregates retained for 30 days.

**Alternatives considered:** Fetch metrics on every dashboard
request; run one collector per connected browser; store all
measurements indefinitely without downsampling.

**Rationale:** A shared collector avoids duplicating LXD queries for
each browser tab and continues collecting when nobody is connected.

Downsampling reduces the number of points returned for longer charts.

**Tradeoff:** TinyFlux is file-based and must be carefully managed
for concurrency, retention, crash recovery and storage growth.
Long-duration retention-size measurements remain outstanding.

### 8. Visibility-aware HTTP dashboard polling

**Choice:** Use ordinary HTTP polling for the dashboard and pause
unnecessary updates when a page becomes hidden.

**Alternatives considered:** Permanent high-frequency polling;
WebSockets or server-sent events for every metric.

**Rationale:** HTTP polling is simpler for a small single-host tool
and does not require permanent streaming connections.

**Tradeoff:** Updates are periodic rather than instantaneous.
Background-tab throttling also means that three tabs on one desktop
do not necessarily represent three independently active clients.

### 9. systemd and static Astro production deployment

**Choice:** Use systemd for database initialization, Falcon and the
independent collector, with one Gunicorn worker initially.

Build Astro to static assets and serve them through Nginx.

Nginx proxies /api and /auth to Falcon on localhost.

**Alternatives considered:** Keep development servers running;
use a larger container-orchestration platform; combine the metrics
collector with the web process.

**Rationale:** systemd provides startup ordering, automatic restart
and journald logs using facilities already available on Ubuntu.
Static Astro avoids a continuously running production Node.js
frontend process.

**Tradeoff:** Installation and updates require OS-level service
configuration. The measured single-worker configuration has not
been load-tested for high numbers of concurrent users.

## Issues Encountered and Solutions

### 1. Falcon port conflict during deployment

The first systemd-managed Gunicorn startup failed because an older
development Gunicorn instance still occupied port 8000.

**Resolution:** Stopped the old development process and restarted
the systemd-managed Falcon service. The API then started successfully.

**Lesson:** Check existing listeners when moving from development
processes to production service management.

### 2. Collector import and working-directory problems

An early manual collector run encountered a Python import error due
to the execution/import context.

**Resolution:** Standardized the collector module entry point and
working-directory conventions so it runs as:

python -m app.collector

The production systemd unit explicitly sets its working directory.

### 3. OAuth redirect URI mismatch

The localhost HTTPS integration configuration initially failed its
redirect URI check because the protected production environment did
not contain the expected callback URI.

**Resolution:** Updated only the OAuth redirect URI to the locally
configured HTTPS callback, verified all required production
configuration checks and restarted Falcon.

The local HTTPS health check passed, and the deployed SQLite
database subsequently contained one active Admin account.

### 4. Local TLS certificate permission verification

A wildcard-based stat command failed even though the certificate
and key existed.

**Cause:** The TLS directory was root-only. The normal user's shell
could not expand the wildcard before sudo executed.

**Resolution:** Checked the two explicit certificate paths.

Verified permissions:

- TLS directory: root:root 0700
- Certificate: root:root 0644
- Private key: root:root 0600

Nginx configuration testing and HTTPS health checks passed.

### 5. Session secret exposure during local deployment

A production session secret was inadvertently displayed in terminal
output during deployment work.

**Resolution:** Rotated the secret in the protected production
environment file and restarted Falcon.

No secret values are included in this report.

This incident reinforced the importance of avoiding commands that
print credentials, even during local troubleshooting.

A separate Git-history credential audit remains necessary.

### 6. Resource-update safety and LXD configuration drift

Real LXD verification included disk-shrink rejection, quota
validation and detection of external configuration changes before
updating managed resource limits.

The Admin resource editing and host allocation milestones passed
the reported 12-item manual verification checklist.

**Resolution and design:** Compare expected managed configuration
with actual LXD state before sensitive updates. Reject unsupported
disk shrinking rather than claiming to provide a safe operation
that LXD and the application cannot guarantee.

### 7. Recovery testing revealed the importance of supervision

A deliberate SIGKILL of the Falcon master process and a separate
SIGKILL of the metrics collector were used to verify service
recovery policies.

After collector termination, systemd increased its restart count
from 0 to 1, started a new collector process and metric collection
resumed.

The TinyFlux verification found 21 new points following the test,
with the latest point approximately 5.36 seconds old.

The host reboot test also showed that Falcon, Nginx, database
initialization and the collector started without manual commands.

### 8. Fresh production database and development-state separation

The production deployment used a separate SQLite database from
local development.

After initial setup, the production database correctly had no
application users. Admin bootstrap subsequently created one
active Admin account.

This reinforced the need to distinguish development data from
production configuration and persistence.

## What You Learned

1. **Privilege boundaries require accurate threat modeling.**
   A dedicated service account is helpful, but LXD administrative
   socket access remains highly privileged.

2. **Backend checks are essential.**
   Hiding an Admin button does not authorize a user. Falcon must
   verify identity, role and container permissions on every
   protected operation.

3. **Allocated resources differ from live usage.**
   Host capacity, quotas and current metrics must be shown and
   validated as separate concepts.

4. **Independent background services simplify recovery.**
   Metric collection should not rely on an active browser or on
   the lifecycle of the web API process.

5. **Deployment tests reveal issues that development tests miss.**
   Port conflicts, environment variables, service permissions,
   secure cookies and restart ordering must be checked on an
   installed system.

6. **Performance claims need measured evidence.**
   The resource benchmark showed low short-duration service usage,
   but did not prove long-term stability or performance under
   heavier loads.

7. **Documentation must reflect real verification status.**
   Untested features and externally accessible HTTPS should not
   be described as fully verified merely because configuration
   templates are present.

## Bonus Features Implemented

### systemd-based deployment and automatic recovery

The repository includes separate systemd unit files for:

- Database initialization.
- Falcon/Gunicorn API.
- Independent metrics collector.

Recovery was tested after unexpected process termination and a
host reboot.

### Deployment verification tooling

The repository includes:

- deploy/scripts/verify-reboot.sh
- deploy/scripts/measure-resources.py

These provide repeatable service, persistence and resource checks.

### Automated and manual testing

The repository contains backend tests for application logic and
security-sensitive behavior.

Manual real-LXD acceptance checks were also performed, including
resource editing, quotas, drift handling, role restrictions and
collector recovery.

GitHub Actions CI is implemented in `.github/workflows/ci.yml`.
The workflow checks Falcon backend tests on Python 3.12, Ruff critical
lint, the Astro production build on Node 22, and repository/script
checks. The CSV-export feature commit `bb60cd69` passed CI on
2026-10-08. LXD-dependent unit tests use mocks in CI; real LXD
integration was verified separately on the Ubuntu development host.

### Additional administrative and monitoring functions

The implementation also provides explicit external-container
adoption, ownership transfer, access management and host allocation
overviews.

These are useful extensions around the required container
management workflow; they are not substitutes for baseline tests.

### Existing-host update tooling, adoption UI and CSV export

Two guarded helpers were added for an **already-provisioned** Ubuntu
installation: `deploy/scripts/install-systemd-units.sh` reconciles the
three systemd units, and `deploy/scripts/update-application.sh` stages
code-only updates with rollback copies and service health checks.
They do not constitute a tested fresh-host provisioning installer.

The systemd unit installer was verified in check/apply mode with no
unit changes; after a code update, API, HTTPS, Nginx, SQLite and
TinyFlux checks passed, including fresh collector measurements.
These tests do not imply a publicly trusted remote TLS deployment.

The Astro Admin dashboard provides an explicit external-container
adoption page. This calls the Falcon Admin-only adoption endpoint;
that endpoint checks LXD security configuration, hardware/storage
budgets and an active owner's quotas without recreating the instance.
Real LXD browser adoption was reported successful.

Container Details includes a CSV export for the five historical chart
ranges (1h, 6h, 24h, 7d and 30d). Its Falcon endpoint reuses the
same container-access checks as historical JSON metrics. CSV cells
are protected against spreadsheet formula injection. The CSV follows
the charts' sampling/aggregation resolution, not a guaranteed dump
of every raw TinyFlux point. Unit/security tests and GitHub CI passed,
and a browser-downloaded 1h CSV was inspected (179 metric rows,
16 columns, chronological timestamps). At download time, its actual
available recorded history covered about 30 minutes.

Not implemented or not claimed as bonuses:

- Container snapshot management.
- Automated alerting.
- Interactive WebSocket terminal.
- Multi-host management.

## Resource Measurements

### 1. Benchmark Objective

The task requires the monitoring application to consume
minimal CPU and RAM because it runs on the same machine
it monitors.

Resource measurements were performed on the deployed
application rather than the development servers.

The benchmark covers:

- Falcon API running under Gunicorn.
- Independent TinyFlux metrics collector.
- Nginx serving the compiled Astro frontend.
- Browser usage with zero, one and three dashboard tabs.
- Short-term SQLite and TinyFlux storage growth.

### 2. Test Environment

Verification date: 2026-10-08

| Component | Specification |
| --- | --- |
| Operating system | Ubuntu 24.04.4 LTS |
| Architecture | x86_64 |
| Processor | Intel Core i9-11900H @ 2.50 GHz |
| Physical CPU cores | 8 |
| Logical CPU threads | 16 |
| Host RAM | 15,763.51 MiB |
| LXD version | 5.21.8 LTS |
| Containers present | 3 |
| Running containers | 1 |
| Stopped containers | 2 |
| Falcon server | Gunicorn, 1 worker |
| Metrics polling interval | 10 seconds |
| Frontend deployment | Static Astro through Nginx |

The operating system was running normal desktop
workloads during testing.

The measurements represent this development machine
and should not be interpreted as the minimum hardware
requirements for every deployment.

### 3. Measurement Methodology

The benchmarking script is located at:

deploy/scripts/measure-resources.py

The script reads resource counters from systemd
using the following properties:

- ActiveState
- MainPID
- MemoryCurrent
- CPUUsageNSec

It collects service memory measurements approximately
every five seconds.

Average CPU utilization is calculated from the
difference in CPUUsageNSec between the beginning
and end of each test.

CPU percentages are normalized so that 100%
corresponds to one fully utilized logical CPU.

Average RAM is calculated from sampled
MemoryCurrent values.

These are systemd control-group memory measurements
and may include memory accounted to the service
beyond its process-resident pages.

Three measurement scenarios were executed
sequentially, each lasting approximately 60 seconds.

Commands:

sudo python3 deploy/scripts/measure-resources.py no-tabs 60

sudo python3 deploy/scripts/measure-resources.py one-tab 60

sudo python3 deploy/scripts/measure-resources.py three-tabs 60

### 4. No Browser Tabs

Duration: 60.03 seconds

| Service | Average CPU | Average RAM | Peak sampled RAM |
| --- | ---: | ---: | ---: |
| Falcon API | 0.015% | 42.55 MiB | 42.74 MiB |
| Metrics collector | 0.303% | 38.36 MiB | 38.50 MiB |
| Nginx | 0.000% | 18.39 MiB | 18.39 MiB |

Sum of average service memory: 99.30 MiB

Sum of average service CPU usage: 0.318%

SQLite net size change: 0 bytes

TinyFlux net size change: +7,199 bytes

The collector continued running with no browser tabs open. Metrics collection therefore did not
depend on an active dashboard session.

### 5. One Dashboard Tab

Duration: 60.01 seconds

| Service | Average CPU | Average RAM | Peak sampled RAM |
| --- | ---: | ---: | ---: |
| Falcon API | 0.101% | 42.95 MiB | 43.39 MiB |
| Metrics collector | 0.429% | 38.53 MiB | 38.62 MiB |
| Nginx | 0.022% | 18.76 MiB | 19.47 MiB |

Sum of average service memory: 100.24 MiB

Sum of average service CPU usage: 0.552%

SQLite net size change: 0 bytes

TinyFlux net size change: +8,439 bytes

### 6. Three Dashboard Tabs

Duration: 60.03 seconds

| Service | Average CPU | Average RAM | Peak sampled RAM |
| --- | ---: | ---: | ---: |
| Falcon API | 0.146% | 44.40 MiB | 45.27 MiB |
| Metrics collector | 0.331% | 38.69 MiB | 39.04 MiB |
| Nginx | 0.019% | 19.09 MiB | 19.91 MiB |

Sum of average service memory: 102.18 MiB

Sum of average service CPU usage: 0.496%

SQLite net size change: 0 bytes

TinyFlux net size change: +7,196 bytes

The collector remained a single independent
systemd service.

The dashboard uses visibility-aware polling,
which may reduce the activity of background tabs.

The test does not establish how the application
would behave with three independently active
clients on different machines.

### 7. Comparison

| Metric | No tabs | 1 tab | 3 tabs |
| --- | ---: | ---: | ---: |
| Combined average RAM (MiB) | 99.30 | 100.24 | 102.18 |
| Combined CPU (%) | 0.318 | 0.552 | 0.496 |
| TinyFlux growth (bytes) | 7,199 | 8,439 | 7,196 |

The difference between the no-tab and three-tab
measurements was 2.88 MiB of combined average
service memory.

The CPU measurements were low in all three tests.

However, the tests were short and sequential.
Normal host activity, garbage collection, file
caching and background processes can affect
individual readings.

No statistical confidence interval or repeated
trial analysis was performed.

### 8. Storage Growth

The observed TinyFlux file size changes were:

- No tabs: +7,199 bytes in approximately 60 seconds.
- One tab: +8,439 bytes in approximately 60 seconds.
- Three tabs: +7,196 bytes in approximately 60 seconds.

The collector monitored three LXD containers,
including stopped containers.

SQLite did not change in size during these
measurement windows.

The observed TinyFlux growth ranged from
approximately 7.2 KB to 8.4 KB per minute.

If this short-term growth continued without
retention or compaction, the corresponding
linear estimate would be roughly 10 to 12 MB
per day for the tested workload.

This is an illustrative extrapolation,
not a measured daily or monthly storage footprint.

The implementation also includes:

- A configurable raw-metric retention period.
- Periodic five-minute metric aggregation.
- Retention cleanup of older measurements.

Actual long-duration bounded-storage behavior
requires a separate verification test.

### 9. Resource Efficiency Assessment

The measured deployment used approximately
99 to 102 MiB of combined average service memory
across the three tested scenarios.

The independent collector averaged approximately
38 to 39 MiB of control-group memory.

The Falcon API averaged approximately
43 to 44 MiB.

The measured CPU footprint was low during
these short tests.

The static Astro frontend does not require
a continuously running production Node.js server.

The independent collector polls LXD once per
configured interval rather than creating
a separate collection process per browser tab.

These measurements support the decision to
use Falcon, Astro, systemd and an independent
TinyFlux collector for this single-host tool.

### 10. Measurement Limitations

The following were not established by these tests:

- Behavior on a much smaller host.
- Maximum supported number of containers.
- Sustained concurrent-user performance.
- Long-term memory stability.
- Actual 24-hour and 30-day storage size.
- CPU and RAM behavior during an LXD outage.
- Browser-side CPU and RAM consumption.
- Performance under heavy terminal execution
  or simultaneous container management actions.

These remain known measurement limitations
unless further tests are performed.

## Known Limitations

### 1. LXD privilege boundary

The Falcon service requires access to the privileged local LXD
administrative socket. This remains a significant security risk
if Falcon or the service account is compromised.

There is no separately isolated privileged LXD operations broker.

### 2. Single-host and default-project scope

The implementation targets a single Ubuntu server and the LXD
default project.

Multi-host orchestration and general multi-project management
are outside the current implementation.

### 3. Container image and configuration restrictions

Managed-container creation currently approves the Ubuntu 24.04
image alias.

Arbitrary inherited LXD profiles, unsafe device passthrough and
general host filesystem mounting are not supported through the
creation form.

Container renaming is not implemented.

Managed root-disk shrinking is rejected.

### 4. Terminal limitations

The terminal supports non-interactive execution rather than a
persistent interactive PTY.

Admin commands may run as root inside the selected container.

Container Users require an appropriate provisioned non-root
identity inside the container.

The system does not guarantee isolation between mutually
untrusted users who share access to the same container.

### 5. HTTPS and OAuth verification scope

Locally trusted HTTPS was tested using Nginx and mkcert at
https://localhost:8443.

The production database contained one active Admin after the
bootstrap workflow.

An externally accessible production hostname and publicly
trusted TLS certificate were not verified.

A separate end-to-end test using an uninvited Google account
is still outstanding.

### 6. Storage and resource benchmarking limitations

Three actual 60-second performance scenarios were recorded.

Full-day and 30-day retained TinyFlux storage sizes were not
measured.

The benchmark did not include many concurrent independent users,
large container fleets, or an extended resource-leak test.

A controlled production deployment test of LXD disappearing and
then becoming available again remains outstanding.

### 7. Operational and optional functionality

The current implementation does not include:

- Interactive WebSocket terminal sessions.
- Snapshot and snapshot-restore management.
- Automatic alerts.

The separate deployment instructions are tested on the development
Ubuntu machine, but a second completely fresh host installation
has not been independently verified.

## AI Tool Usage

ChatGPT was used as a development assistant during this project.

Assistance included:

- Interpreting the internship specification.
- Comparing architecture and security approaches.
- Explaining LXD, container privileges, quotas and TinyFlux.
- Proposing Falcon and Astro implementation approaches.
- Suggesting validation and error-handling logic.
- Designing test cases and acceptance checklists.
- Preparing Linux, systemd, Nginx and Git commands.
- Diagnosing reported terminal errors.
- Drafting and refining README, TODO, deployment and report text.

AI-generated material was not treated as proof that code was working.

The implementation was checked against actual repository files, tested using backend tests and real LXD operations, and verified through local deployment, restart tests, HTTPS health checks, database checks and resource measurements.

Examples of reviewed or corrected suggestions included:

- Replacing unsafe instructions about committing .env files.
- Correcting the local OAuth redirect URI.
- Correcting wildcard-based TLS permission verification.
- Resolving conflicts between development and production services.
- Recording security risks that cannot be removed merely by
  placing Falcon under a non-root service account.

The developer is responsible for explaining the final
implementation, reviewing its security properties and checking all submitted statements against the actual code.

## Final Verification and Submission Status

Verified evidence includes:

- Functional and security checks during development.
- Real LXD resource editing and quota acceptance checks.
- Independent TinyFlux collection and persistence.
- Falcon automatic restart after SIGKILL.
- Collector automatic restart after SIGKILL.
- Reboot recovery of systemd-managed services.
- Nginx HTTPS health and static frontend responses.
- Production bootstrap Admin in SQLite.
- Measured CPU, RAM and short-window storage growth.
- Successful GitHub Actions tests, critical lint, Astro build and repository checks through CSV-export commit `bb60cd69`.
- Guarded existing-host deployment updates, authenticated adoption UI and historical CSV download tested on the development host.

Outstanding verification and scope limitations are documented above and in TODO.md.

The final repository review must also check:

- Real secrets have not been committed.
- All README setup instructions are accurate.
- The report's development-hour estimates have been filled in.
- The final tested branch is merged into main.
- The repository link is submitted before October 9, 2026.
