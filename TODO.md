
# Hobby Server Monitor — Implementation TODO

Repository: https://github.com/birajithk/Hobby-Server-Monitor

Soft deadline: October 7, 2026
Hard deadline: October 9, 2026

Priority:
- P0: Required functionality, security and correctness.
- P1: Verification, deployment and documentation.
- P2: Optional enhancements and bonuses.

A task is complete only when its implementation has been verified.

## Phase 0 — Project Foundation

- [x] Create the GitHub repository from the supplied template.
- [x] Choose native Ubuntu as the development environment.
- [x] Confirm Python, Node.js, npm and Git versions.
- [x] Install LXD 5.21 LTS.
- [x] Initialize LXD.
- [x] Configure development-account LXD access.
- [x] Verify the default LXD profile and network.
- [x] Create the feat/project-foundation branch.
- [x] Configure .gitignore to exclude .env and generated data.
- [x] Create docs/PROJECT_SPEC.md.
- [x] Create docs/DECISIONS.md.
- [x] Create TODO.md.
- [x] Arrange at least 25 GB of available host disk space.
- [x] Verify the new files and make the foundation commit.

## Phase 1 — LXD Development Environment (P0)

- [x] Inspect available storage drivers.
- [x] Create a quota-capable LXD storage pool.
- [x] Verify that container disk limits are enforced.
- [ ] Configure the default profile to use the chosen pool.
- [x] Verify LXD networking.
- [x] Discover supported Ubuntu image aliases.
- [x] Create an unprivileged development container.
- [x] Verify its network connectivity.
- [x] Verify CPU, memory and disk configuration.
- [x] Test start, stop, restart, freeze and unfreeze.
- [x] Test real LXD command execution.
- [x] Verify cleanup and container deletion.
- [x] Record installation and configuration commands for README.md.

## Phase 2 — Falcon Backend Foundation (P0)

- [x] Define the backend package structure.
- [x] Configure the Python virtual environment.
- [x] Select and pin required dependencies.
- [x] Implement centralized application configuration.
- [x] Implement environment-variable validation.
- [x] Initialize the Falcon application.
- [x] Implement a health endpoint.
- [x] Add consistent API error responses.
- [x] Add structured application logging.
- [x] Implement SQLite connection management.
- [x] Configure SQLite foreign keys.
- [x] Define database schema and indexes.
- [x] Implement database initialization and migrations.
- [x] Add the TinyFlux connection and storage configuration.
- [x] Define separate service and repository layers.
- [x] Add backend test infrastructure.

## Phase 3 — Authentication and Authorization (P0)

- [x] Create Google OAuth credentials.
- [x] Configure OAuth redirect URIs.
- [x] Implement login initiation.
- [x] Implement OAuth state and PKCE.
- [x] Implement OAuth callback and identity validation.
- [x] Verify Google's stable user identifier and email status.
- [x] Implement bootstrap Admin creation.
- [x] Require invitations for ordinary users.
- [x] Implement secure server-side sessions.
- [x] Configure HttpOnly, SameSite and environment-appropriate Secure cookies.
- [x] Implement session expiration.
- [x] Implement logout and session invalidation.
- [ ] Implement user-revocation session invalidation.
- [x] Implement CSRF protection.
- [x] Implement centralized authentication middleware.
- [ ] Implement centralized permission rules.
- [ ] Implement service-layer authorization.
- [x] Test unauthorized and unauthenticated requests.
- [ ] Prevent removal of the last active Admin.
- [x] Implement reusable container-level authorization for read-only APIs.
- [x] Verify that container authorization precedes individual LXD retrieval.

## Phase 4 — LXD Integration (P0)

- [x] Implement read-only container listing for the default LXD project.
- [x] Display unmanaged containers in the Admin's read-only API response.
- [x] Return controlled errors for LXD failures in read-only container APIs.
- [ ] Implement the pylxd client connection.
- [ ] Verify local Unix socket access.
- [ ] Define the dedicated Falcon service-account requirements.
- [ ] Implement LXD availability and error handling.
- [x] Implement host CPU and memory discovery.
- [x] Implement available storage-pool discovery.
- [x] Implement network and profile discovery.
- [x] Implement the Admin-only read-only host information API.
- [x] Test host discovery, authorization and LXD failure handling.
- [ ] Implement image and alias discovery.
- [ ] Implement container listing.
- [ ] Implement container state and metadata retrieval.
- [ ] Implement stable application identifiers.
- [ ] Implement external-container discovery.
- [ ] Implement unmanaged-container read-only behavior.
- [ ] Implement explicit container adoption.
- [ ] Implement validated container creation.
- [ ] Enforce restrictive container security configuration.
- [ ] Implement start, stop, restart, freeze and unfreeze.
- [ ] Implement resource-limit updates.
- [ ] Implement container renaming where supported.
- [ ] Implement deletion with appropriate cleanup.
- [ ] Implement audit records for sensitive operations.
- [ ] Implement appropriate LXD operation timeouts.
- [ ] Test failures and unexpected LXD responses.

## Phase 5 — User Management and Quotas (P0)

- [ ] Implement user invitations.
- [ ] Implement user listing and details.
- [ ] Implement role changes.
- [ ] Implement user revocation.
- [ ] Implement resource-quota configuration.
- [ ] Implement single-owner container records.
- [ ] Implement multiple access assignments.
- [ ] Implement access assignment and revocation.
- [ ] Implement ownership transfers.
- [ ] Enforce quota checks during ownership transfers.
- [ ] Prevent deleting users who still own containers.
- [x] Count stopped containers against allocations.
- [ ] Implement host-resource budget calculations.
- [ ] Account for external containers when determining availability.
- [ ] Implement RAM quota validation.
- [ ] Implement CPU core quota validation.
- [ ] Implement disk quota validation.
- [ ] Distinguish CPU core allocation from CPU allowance.
- [ ] Reject allocations exceeding host capacity.
- [ ] Reject allocations exceeding user quotas.
- [ ] Protect quota-sensitive operations against concurrency.
- [ ] Implement host-level resource-accounting endpoints.
- [x] Implement per-user quota and allocation endpoints.
- [ ] Test quota bypass attempts.
- [ ] Test ownership and assignment permissions.
- [x] Implement reusable transactional user-quota validation.
- [x] Implement a read-only host allocation summary for the default LXD project.
- [x] Implement conservative host-budget validation that rejects unmanaged containers and unverified storage pools.

## Phase 6 — Independent Metrics Collector (P0)

- [ ] Create the standalone collector entry point.
- [ ] Configure 10-second polling.
- [ ] Collect metrics without depending on the UI.
- [ ] Collect container CPU statistics.
- [ ] Collect memory usage.
- [ ] Collect disk usage where supported.
- [ ] Collect network RX/TX counters.
- [ ] Calculate network rates.
- [ ] Collect process count.
- [ ] Collect container state and uptime.
- [ ] Store supported metadata.
- [ ] Define TinyFlux measurement, tag and field structure.
- [ ] Persist measurements in TinyFlux.
- [ ] Handle stopped containers.
- [ ] Handle LXD unavailability.
- [ ] Handle missing metrics and counter resets.
- [ ] Resume collection after failures.
- [ ] Implement latest-metrics queries.
- [ ] Implement historical-metrics queries.
- [ ] Enforce authorization on metric endpoints.
- [ ] Implement time-range selection.
- [ ] Implement server-side chart aggregation.
- [ ] Retain raw samples for 24 hours.
- [ ] Maintain five-minute aggregates for 30 days.
- [ ] Implement retention and cleanup.
- [ ] Verify that stored data survives service restarts.
- [ ] Verify that browser count does not change collection frequency.

## Phase 7 — Container Terminal (P0)

- [ ] Implement the terminal API.
- [ ] Validate terminal requests.
- [ ] Enforce container-specific permissions.
- [ ] Use actual pylxd execution.
- [ ] Establish the Admin execution identity.
- [ ] Provision and verify the non-root Container User identity.
- [ ] Prevent unrestricted sudo for Container Users.
- [ ] Implement command-length limits.
- [ ] Implement output-size limits.
- [ ] Implement bounded execution concurrency.
- [ ] Implement execution timeouts.
- [ ] Verify process termination and cancellation.
- [ ] Reject execution on stopped containers.
- [ ] Return exit code, stdout and stderr.
- [ ] Implement terminal audit metadata.
- [ ] Test attempts to access unassigned containers.
- [ ] Test the container-to-host security boundary.

## Phase 8 — Astro Dashboard (P0)

- [ ] Initialize Astro.
- [ ] Configure API access.
- [ ] Implement the shared page layout.
- [ ] Implement the Google login page.
- [ ] Implement authenticated navigation.
- [ ] Implement logout.
- [ ] Implement role-specific navigation.
- [ ] Implement the Admin overview.
- [ ] Implement the Container User overview.
- [ ] Implement the container list and status indicators.
- [ ] Display current CPU, RAM and disk metrics.
- [ ] Display network RX/TX data.
- [ ] Display container metadata and uptime.
- [ ] Implement the container detail page.
- [ ] Implement historical charts.
- [ ] Implement time-range selection.
- [ ] Implement dashboard polling.
- [ ] Suspend or reduce unnecessary background-tab polling.
- [ ] Implement container creation.
- [ ] Load image, network, profile and storage options dynamically.
- [ ] Derive form bounds from available quotas and host capacity.
- [ ] Implement RAM, CPU and disk controls.
- [ ] Implement CPU allowance configuration.
- [ ] Implement ephemeral and autostart options.
- [ ] Implement container lifecycle controls.
- [ ] Implement resource-limit updates.
- [ ] Implement deletion confirmation.
- [ ] Implement user invitations.
- [ ] Implement user listing and role management.
- [ ] Implement quota management.
- [ ] Implement container assignments.
- [ ] Implement ownership transfers.
- [ ] Display user allocations against quotas.
- [ ] Display host allocation summaries.
- [ ] Implement the command terminal interface.
- [ ] Display command output and exit status.
- [ ] Handle loading, empty and error states.
- [ ] Display stale metrics and LXD-unavailable states.
- [ ] Verify responsive layouts.
- [ ] Verify that role restrictions are enforced by the API.

## Phase 9 — Security and Correctness Testing (P0/P1)

- [ ] Test login and logout.
- [ ] Test uninvited Google accounts.
- [ ] Test bootstrap Admin behavior.
- [ ] Test session expiration and revocation.
- [ ] Test CSRF protection.
- [ ] Test Admin-only operations.
- [x] Test unassigned-container access.
- [ ] Test cross-user terminal access.
- [ ] Test invalid names and resource values.
- [ ] Test resource quota enforcement.
- [ ] Test concurrent allocation requests.
- [ ] Test container ownership transfers.
- [ ] Test unmanaged-container protections.
- [ ] Test dangerous LXD configuration attempts.
- [ ] Test command execution limits.
- [ ] Test error handling when LXD is unavailable.
- [ ] Test recovery after LXD becomes available.
- [ ] Test TinyFlux retention and historical queries.
- [ ] Test restart and persistence behavior.
- [ ] Review dependency and credential handling.
- [ ] Verify that no real secrets have been committed.
- [x] Test per-user allocation calculations and stopped-container accounting.
- [x] Test quota-validation helpers and conservative host-budget blocking.

## Phase 10 — Deployment (P1)

- [ ] Create the required service-account setup instructions.
- [ ] Configure the deployment environment.
- [ ] Add the Falcon systemd service.
- [ ] Add the independent collector systemd service.
- [ ] Configure Astro deployment.
- [ ] Configure appropriate startup ordering.
- [ ] Configure restart policies.
- [ ] Document service logging.
- [ ] Verify a fresh database initialization.
- [ ] Verify service recovery.
- [ ] Verify recovery after a host reboot.
- [ ] Verify that the application works without development servers.

## Phase 11 — Resource Benchmarking (P0)

- [ ] Record host hardware and OS information.
- [ ] Measure idle Falcon memory and CPU.
- [ ] Measure idle collector memory and CPU.
- [ ] Measure resource usage with active containers.
- [ ] Measure resource usage with one dashboard tab.
- [ ] Measure resource usage with multiple dashboard tabs.
- [ ] Measure resource usage with no dashboard tabs.
- [ ] Measure behavior when LXD is unavailable.
- [ ] Estimate and verify metric-storage growth.
- [ ] Record commands, duration and test conditions.
- [ ] Publish real results in REPORT.md.

## Phase 12 — Documentation (P1)

- [ ] Replace the template README with real setup instructions.
- [ ] Document LXD installation and initialization.
- [ ] Document Google OAuth configuration.
- [ ] Document backend and frontend installation.
- [ ] Document database initialization.
- [ ] Add the architecture diagram.
- [ ] Document the SQLite schema.
- [ ] Document the TinyFlux schema.
- [ ] Document all API endpoints and permissions.
- [ ] Document every environment variable.
- [ ] Document the LXD privilege decision.
- [ ] Document the security threat model.
- [ ] Document deployment and recovery.
- [ ] Complete REPORT.md.
- [ ] Record approximate time spent per area.
- [ ] Record actual problems and solutions.
- [ ] Record lessons learned.
- [ ] Document implemented bonuses.
- [ ] Document actual resource measurements.
- [ ] Document known limitations.
- [ ] Disclose AI tool usage.
- [ ] Verify README instructions on a clean environment.

## Phase 13 — Bonuses (P2)

- [ ] Add GitHub Actions CI for backend tests.
- [ ] Add frontend build verification to CI.
- [ ] Add automated linting and code checks.
- [ ] Add useful integration and security tests.
- [ ] Complete the detailed threat model.
- [ ] Provide reproducible systemd deployment scripts.
- [ ] Add authorized CSV metrics export if time permits.

Optional enhancements must not delay baseline security or functionality.

## Phase 14 — Final Review and Submission

- [ ] Review the complete implementation against PROJECT_SPEC.md.
- [ ] Update DECISIONS.md with any actual design changes.
- [ ] Verify that TODO.md reflects the real completion status.
- [ ] Confirm all baseline features work end to end.
- [ ] Confirm the collector runs independently.
- [ ] Confirm historical metrics survive a restart.
- [ ] Confirm resource measurements are published.
- [ ] Confirm all configuration variables are documented.
- [ ] Confirm no secrets are present in Git history.
- [ ] Review code for dead code and unnecessary dependencies.
- [ ] Ensure every submitted component can be explained.
- [ ] Verify the required submission instructions from the task email.
- [ ] Push the completed work to GitHub.
- [ ] Submit the repository link before October 9, 2026.
