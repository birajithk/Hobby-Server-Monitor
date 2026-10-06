
# Hobby Server Monitor — Project Specification

## 1. Project Information

- Role: Software Engineer Intern
- Organization: RoboticGen
- Contact: dev@roboticgen.co
- Repository: https://github.com/birajithk/Hobby-Server-Monitor
- Soft deadline: October 7, 2026
- Hard deadline: October 9, 2026
- Target operating system: Ubuntu 24.04.4 LTS
- Development machine: Native Ubuntu
- Deployment: Single on-premises Linux server

The project transforms an existing Linux machine into an on-premises testing server using LXD. A browser-accessible dashboard must provide container management, resource monitoring, user management, quota enforcement and terminal access.

## 2. Primary Constraints

### Resource efficiency

The application runs on the server it monitors. CPU, memory, storage and network overhead must be minimized and measured.

### Security

The application has access to privileged container-management functionality. Authentication, authorization, validation and container isolation must be implemented correctly.

### Engineering judgment

Architectural decisions must be justified. The implementation must be understandable, maintainable and defensible during a 30–45-minute technical interview.

## 3. Required Technology

| Layer | Technology |
|---|---|
| Backend | Falcon |
| Dashboard | Astro |
| Container management | LXD 5.x through pylxd |
| Application database | SQLite (sqlite3) |
| Time-series database | TinyFlux |
| Authentication | Google OAuth 2.0 |
| Development OS | Native Ubuntu |
| Deployment | On-premises Linux |

Prerequisites:

- Python 3.10+
- Node.js 18+
- LXD 5.x, installed and initialized
- A Google Cloud project with OAuth 2.0 credentials

Technology substitutions require justification in the final report. Familiarity with a heavyweight framework is not sufficient justification.

## 4. User Roles

### Admin

The Admin can:

- View all containers and their metrics.
- Create, update and delete containers.
- Start, stop, restart and freeze containers.
- Change container resource limits.
- Manage users and roles.
- Invite and revoke users.
- Assign and revoke container access.
- Set resource quotas.
- View host-level and per-user resource accounting.
- Access the terminal of every managed container.
- Discover externally created containers.

### Container User

A Container User can:

- View only explicitly assigned containers.
- View current and historical metrics for assigned containers.
- Access the terminal of assigned containers.
- View their own resource quota and allocation.

Container Users cannot manage container lifecycles, create containers, change resource limits or manage other users.

Requests for unassigned containers must return HTTP 403.

## 5. Authentication

- Users must authenticate using Google OAuth 2.0.
- The initial Admin must be created through a documented bootstrap mechanism.
- Users who have not been invited must not gain application access merely by authenticating with Google.
- Sessions must be managed securely.
- Logout and user revocation must invalidate access.
- All protected API operations must enforce authentication and authorization.

## 6. Admin Dashboard

The Admin dashboard must display all containers on the host.

Required or expected metrics include:

- CPU utilization percentage.
- RAM usage, allocation and utilization percentage.
- Disk usage, allocation and utilization percentage.
- Network RX and TX cumulative bytes and transfer rates.
- Container state: Running, Stopped, Frozen or Error.
- Uptime.
- Process count.
- Image and operating-system version.
- IPv4 address.

The dashboard should distinguish essential information from secondary details and provide useful loading, empty, stale and error states.

## 7. Container Creation

The Admin must be able to create containers through an interactive form.

The form must support:

- Validated container name.
- Base image or Ubuntu version.
- RAM allocation.
- CPU core allocation.
- CPU allowance percentage.
- Disk allocation.
- Network selection.
- Storage pool selection.
- Ephemeral mode.
- Autostart on boot.
- Optional description.

Container names must follow applicable LXD naming requirements, using lowercase alphanumeric characters and hyphens.

Image aliases, networks, bridges, profiles and storage pools must be discovered at runtime where applicable.

Resource bounds must be calculated using actual host capacity and the relevant user's remaining quota.

The API must independently validate every submitted value, regardless of frontend validation.

Additional pylxd-supported configuration options may be included when they provide a clear benefit. Their purpose must be documented.

## 8. Container Management

The Admin must be able to:

- Start and stop containers.
- Restart containers.
- Freeze and unfreeze containers.
- Modify supported resource limits, including on running containers where LXD permits it.
- Delete containers after a confirmation step.

Destructive operations and resource-limit changes must produce audit records.

## 9. User Management

The Admin must be able to:

- Invite users by Google account email.
- Assign containers to users.
- Revoke container access.
- Change user roles.
- Revoke users.
- Set and modify per-user quotas.

Each user's quota must include maximum RAM, CPU cores and disk allocation.

The application must enforce quotas through the API rather than relying exclusively on frontend controls.

## 10. Resource Accounting

The dashboard must show:

- Total allocated RAM against host capacity.
- Total allocated CPU against host capacity.
- Total allocated disk against available storage.
- Per-user allocations against their quotas.
- Per-container historical consumption.

Resource allocation and actual consumption must be distinguishable.

Resource accounting must consider both user quotas and host capacity.

## 11. Terminal

Both roles must be able to execute real commands inside containers they are authorized to access.

The preferred implementation uses pylxd execution.

The terminal must:

- Accept commands from the browser.
- Execute commands in the authorized container.
- Display standard output, standard error and exit status.
- Enforce container-specific access permissions.
- Avoid exposing host command execution.
- Handle invalid, failed and long-running operations.

The security design must address the possibility of users attempting to escape a container or access the host.

## 12. Background Metrics Collection

An independent background process must:

- Poll metrics for every container every 10 seconds.
- Store samples in TinyFlux.
- Continue running without an open browser.
- Recover from temporary LXD failures.
- Avoid duplicating collection work for additional browser tabs.
- Apply a bounded data-retention policy.
- Preserve historical data across page refreshes and service restarts.

The application must support historical charts covering recent minutes and hours.

## 13. Required Engineering Decisions

The implementation and final report must address:

1. Session management and logout.
2. Centralized authorization and protection against missing checks.
3. Quota definitions and quota-exceeded behavior.
4. LXD privilege boundaries and their security implications.
5. Dashboard refresh strategy and idle overhead.
6. Time-series retention after one month.
7. Terminal functionality and associated security risks.
8. Container identity, renaming, deletion and assignments.
9. Historical chart aggregation and network transfer size.
10. LXD failures, unexpected responses and user-facing errors.
11. Initial Admin bootstrap security.
12. Deployment, startup and recovery after reboot.

Decisions must include their rationale, alternatives and relevant tradeoffs.

## 14. Minimum Functional Requirements

The application is not complete until a reviewer can:

- Sign in with Google and reach the correct role-specific dashboard.
- View every host container as an Admin.
- See current resource metrics.
- Create a container using a form with valid options.
- Change resource limits.
- Restart and delete containers.
- Invite users.
- Configure resource quotas.
- Assign containers to users.
- Sign in as a Container User and see only authorized containers.
- View historical container metrics.
- Execute a real command inside an authorized container.

The independent collector must work without the dashboard, and metric history must survive service restarts.

## 15. Non-negotiable Requirements

- The metrics collector must run independently of the UI.
- The application's resource footprint must be measured and reported.
- Every submitted line of code must be explainable and defensible.

Security and baseline correctness take priority over optional functionality.

## 16. Source Code Deliverables

The repository must contain:

- Backend source code.
- Frontend source code.
- Supporting scripts.
- Meaningful incremental Git commits.
- README.md.
- REPORT.md.
- .env.example with all required configuration variables.
- Backend dependency manifest.
- Frontend package.json.
- An automated database initialization or migration mechanism.

Secrets must not be exposed in the public repository.

## 17. README.md Requirements

The README must document:

- Installation from a clean Ubuntu or supported WSL environment.
- LXD installation and initialization.
- Google OAuth credential setup.
- Application configuration.
- Backend and frontend installation.
- Database initialization.
- Application startup.
- Architecture diagram and component responsibilities.
- SQLite schema.
- TinyFlux measurement, tag and field structure.
- API endpoints, methods, permissions and request/response formats.
- Security notes and the LXD privilege decision.
- Every required environment variable.

A reviewer should be able to start the application without undocumented steps.

## 18. REPORT.md Requirements

The final report must contain:

- Approximate time spent on each project area.
- Key architectural decisions and alternatives.
- Problems encountered and actual solutions.
- Initial mistakes and subsequent corrections.
- What was learned.
- Implemented bonus features.
- Measured idle CPU and RAM consumption.
- Measurement methods and test conditions.
- Known limitations and unfinished functionality.
- AI tools used and how their output was evaluated, accepted or corrected.

Measurements and completed-feature claims must reflect the actual implementation.

## 19. Evaluation Criteria

| Area | Weight |
|---|---:|
| Judgment and defense of decisions | 25% |
| Security and correctness | 20% |
| Functional completeness | 20% |
| Code quality | 10% |
| Documentation and report | 10% |
| Resource efficiency | 10% |
| User experience | 5% |

Bonus: Up to 10% for genuinely useful additional features, such as tests, CI, snapshots, alerting, exports, systemd deployment and threat-model work.

## 20. Submission

- Repository: https://github.com/birajithk/Hobby-Server-Monitor
- Soft deadline: October 7, 2026.
- Hard deadline: October 9, 2026.
- Submission contact: dev@roboticgen.co.

The current assignment requires submitting the repository link by replying to the task email before the hard deadline.

The initial repository template contains older August deadlines and an additional demo-recording instruction. The October assignment supplied directly is our working specification. Any differing requirement in the actual task email should be verified before submission.

## 21. Scope Control

Prioritize a coherent, secure and functional baseline.

If time is insufficient, deliberately defer optional features and document the reason.

Do not claim that unfinished, simulated or untested functionality is complete.
