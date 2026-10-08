# Hobby Server Monitor — Implementation TODO

Repository: https://github.com/birajithk/Hobby-Server-Monitor

Soft deadline: October 7, 2026
Hard deadline: October 9, 2026

Priority:
- P0: Required functionality, security and correctness.
- P1: Verification, deployment and documentation.
- P2: Optional enhancements and bonuses.

A task is complete only when its implementation has been verified. Checkmarks below reflect the merged source, existing test coverage, and the manual checks reported during development. An unchecked task is **not yet verified as complete**, even where part of the backend already exists. This checklist is not a claim that all end-to-end or deployment tests have passed.

## Immediate next milestone — Complete the Admin dashboard (P0)

- [x] Add a read-only, Admin-authorized endpoint to get one managed container's saved RAM, CPU, CPU allowance, disk and storage-pool limits for form prefill.
- [x] Implement the Admin resource-limit editing form with exact existing API fields and current values.
- [x] Show per-user remaining quotas and per-host remaining allocation budget while editing; preserve backend validation and prevent unsupported disk shrinkage.
- [x] Test real RAM/CPU/allowance/disk-increase changes on a disposable managed LXD container; verify LXD values, SQLite state, metrics, and error handling on drift or quota failure.
- [x] Add an Admin host-allocation overview showing total, reserved, allocated and allocatable RAM/CPU and per-verified-pool disk budgets.
- [x] Show managed/unmanaged counts and allocation blockers; explain when new allocations are disabled and provide a manual refresh.
- [x] Verify the non-root Container User terminal identity in newly created `hsm-test-02` (not only the previously provisioned `hsm-quota-01`). If missing, implement a safe provisioning flow before treating new-container terminal support as complete.
- [x] Verify the Admin and Container User UI on desktop and mobile and the actual API access restrictions.

## Phase 0 — Project Foundation

- [x] Create the GitHub repository from the supplied template.
- [x] Choose native Ubuntu as the development environment.
- [x] Confirm Python, Node.js, npm and Git versions.
- [x] Install LXD 5.21 LTS.
- [x] Initialize LXD.
- [x] Configure development-account LXD access.
- [x] Verify the default LXD profile and network.
- [x] Create the feat/project-foundation branch.
- [x] Merge the project-foundation implementation into `main` and push the merged changes.
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
- [x] Decide whether the default LXD profile needs changing; the application currently creates containers with explicit root-disk and NIC devices, avoiding inherited profile devices.
- [x] Verify LXD networking.
- [x] Discover supported Ubuntu image aliases.
- [x] Create an unprivileged development container.
- [x] Verify its network connectivity.
- [x] Verify CPU, memory and disk configuration.
- [x] Test start, stop, restart, freeze and unfreeze.
- [x] Test managed-container deletion and allocation release.
- [x] Verify lifecycle operations are restricted to managed containers.
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
- [x] Implement user-revocation session invalidation.
- [x] Add Admin-authorized reactivation of revoked Container Users with audit entries; require Google sign-in again.
- [x] Ensure reactivation does not automatically restore old container-access grants.
- [x] Show a generic access-denied message in the Astro login page for rejected Google logins.
- [x] Implement CSRF protection.
- [x] Implement centralized authentication middleware.
- [x] Implement centralized permission checks in authentication middleware and authorization helpers.
- [x] Enforce service-layer Admin and container-access authorization (including privileged write operations).
- [x] Test unauthorized and unauthenticated requests.
- [x] Prevent removal of the last active Admin.
- [x] Implement reusable container-level authorization for read-only APIs.
- [x] Verify that container authorization precedes individual LXD retrieval.

## Phase 4 — LXD Integration (P0)

- [x] Implement read-only container listing for the default LXD project.
- [x] Display unmanaged containers in the Admin's read-only API response.
- [x] Return controlled errors for LXD failures in read-only container APIs.
- [x] Implement the pylxd client connection.
- [x] Verify local Unix socket access.
- [ ] Define the dedicated Falcon service-account requirements.
- [x] Implement LXD availability and error handling.
- [x] Implement host CPU and memory discovery.
- [x] Implement available storage-pool discovery.
- [x] Implement network and profile discovery.
- [x] Implement the Admin-only read-only host information API.
- [x] Test host discovery, authorization and LXD failure handling.
- [ ] Implement validated image/alias discovery if needed for the required creation UI; the currently approved image is intentionally restricted to Ubuntu 24.04.
- [x] Implement container listing.
- [x] Implement container state and metadata retrieval.
- [x] Implement stable application identifiers.
- [x] Implement external-container discovery.
- [x] Implement unmanaged-container read-only behavior.
- [x] Implement explicit container adoption.
- [x] Implement validated container creation.
- [x] Enforce restrictive container security configuration.
- [x] Implement start, stop, restart, freeze and unfreeze.
- [x] Implement resource-limit updates.
- [x] Verify resource-limit updates against real LXD containers.
- [x] Reject resource updates when LXD and application accounting have drifted.
- [x] Prevent disk-limit reduction in the initial resource-update policy.
- [ ] Implement container renaming only if required and safely supported; otherwise explicitly document this as deferred.
- [x] Implement deletion with appropriate cleanup.
- [x] Implement audit records for sensitive operations.
- [ ] Implement appropriate LXD operation timeouts.
- [ ] Test failures and unexpected LXD responses.

## Phase 5 — User Management and Quotas (P0)

- [x] Implement user invitations.
- [x] Implement user listing and details.
- [x] Implement role changes.
- [x] Implement user revocation.
- [x] Implement Admin reactivation of revoked Container Users while retaining account and audit history.
- [x] Implement resource-quota configuration.
- [x] Enforce quota maxima from discovered total host RAM, logical CPU threads and the largest verified LXD storage-pool capacity (not current free resources).
- [x] Apply the same hardware-based quota maxima to invitations and quota edits.
- [x] Implement single-owner container records.
- [x] Implement multiple access assignments.
- [x] Implement access assignment and revocation.
- [x] Implement ownership transfers.
- [x] Enforce quota checks during ownership transfers.
- [x] Prevent deleting users who still own containers.
- [x] Count stopped containers against allocations.
- [x] Implement host-resource budget calculations.
- [x] Account for external containers when determining availability.
- [x] Implement RAM quota validation.
- [x] Implement CPU core quota validation.
- [x] Implement disk quota validation.
- [x] Distinguish CPU core allocation from CPU allowance.
- [x] Reject allocations exceeding host capacity.
- [x] Reject allocations exceeding user quotas.
- [x] Protect quota-sensitive operations against concurrency.
- [x] Serialize quota changes with allocation-sensitive container operations.
- [x] Serialize allocation-sensitive operations across Falcon workers.
- [x] Implement host-level resource-accounting endpoints.
- [x] Implement per-user quota and allocation endpoints.
- [x] Test quota bypass attempts.
- [x] Test ownership and assignment permissions.
- [x] Implement reusable transactional user-quota validation.
- [x] Implement a read-only host allocation summary for the default LXD project.
- [x] Implement conservative host-budget validation that rejects unmanaged containers and unverified storage pools.

## Phase 6 — Independent Metrics Collector (P0)

- [x] Create the standalone collector entry point.
- [x] Configure 10-second polling.
- [x] Collect metrics without depending on the UI.
- [x] Collect container CPU statistics.
- [x] Collect memory usage.
- [x] Collect disk usage where supported.
- [x] Collect network RX/TX counters.
- [x] Calculate network rates.
- [x] Collect process count.
- [x] Collect container state and uptime.
- [x] Store supported metadata.
- [x] Define TinyFlux measurement, tag and field structure.
- [x] Persist measurements in TinyFlux.
- [x] Handle stopped containers.
- [x] Handle LXD unavailability.
- [x] Handle missing metrics and counter resets.
- [x] Resume collection after failures.
- [x] Implement latest-metrics queries.
- [x] Implement historical-metrics queries.
- [x] Enforce authorization on metric endpoints.
- [x] Test metrics endpoint authorization and historical range selection.
- [x] Implement time-range selection.
- [x] Implement server-side chart aggregation.
- [x] Retain raw samples for 24 hours.
- [x] Maintain five-minute aggregates for 30 days.
- [x] Test five-minute metric aggregation.
- [x] Implement retention and cleanup.
- [x] Verify that stored data survives service restarts.
- [x] Verify that browser count does not change collection frequency.

## Phase 7 — Container Terminal (P0)

- [x] Implement the terminal API.
- [x] Validate terminal requests.
- [x] Enforce container-specific permissions.
- [x] Use actual pylxd execution.
- [x] Establish the Admin execution identity.
- [x] Provision and verify the restricted non-root terminal identity in newly created managed containers; creation provisions and validates `hsm-user` before the container is registered as successfully managed.
- [x] Verify/provision the restricted non-root terminal identity in each newly created managed container; creation currently starts LXD without a verified automatic identity-provisioning step.
- [x] Prevent unrestricted sudo for Container Users.
- [x] Implement command-length limits.
- [x] Implement output-size limits.
- [x] Implement bounded execution concurrency.
- [x] Implement execution timeouts.
- [x] Verify process termination and cancellation.
- [x] Reject execution on stopped containers.
- [x] Return exit code, stdout and stderr.
- [x] Implement terminal audit metadata.
- [x] Test attempts to access unassigned containers.
- [x] Test the container-to-host security boundary.

## Phase 8 — Astro Dashboard (P0)

- [x] Initialize Astro.
- [x] Configure API access.
- [x] Implement the shared page layout.
- [x] Implement the Google login page.
- [x] Implement authenticated navigation.
- [x] Implement logout.
- [x] Implement role-specific navigation.
- [x] Implement the Admin overview.
- [x] Implement the Container User overview with only assigned containers and permitted metrics.
- [x] Implement the container list and status indicators.
- [x] Display current CPU, RAM and disk metrics.
- [x] Display network RX/TX data.
- [x] Display container metadata and uptime.
- [x] Implement the container detail page.
- [x] Implement historical charts.
- [x] Implement time-range selection.
- [x] Implement dashboard polling.
- [x] Suspend or reduce unnecessary background-tab polling.
- [x] Implement container creation.
- [x] Populate LXD network and verified storage-pool choices dynamically for container creation.
- [ ] Support validated runtime image/profile choices beyond the deliberately fixed Ubuntu 24.04 image and explicit no-profile creation, or clearly document the limitation against the assignment brief.
- [x] Derive form bounds from available quotas and host capacity.
- [x] Implement RAM, CPU and disk controls.
- [x] Implement CPU allowance configuration.
- [x] Implement ephemeral and autostart options.
- [x] Display current allocatable disk for the selected verified storage pool in the top host-resource summary.
- [x] Implement container lifecycle controls.
- [x] Implement Admin resource-limit updates from the Astro dashboard (Falcon PATCH endpoint already exists).
- [x] Expose saved current resource limits through an authenticated Admin GET endpoint for form prefill.
- [x] Verify resource-limit edits made through the dashboard against real LXD containers, database allocations and metrics.
- [x] Reject resource updates when LXD and application accounting have drifted.
- [x] Prevent disk-limit reduction in the initial resource-update policy.
- [x] Implement deletion confirmation.
- [x] Implement the Astro Admin user-invitation form with hardware-based quota limits.
- [x] Implement user listing and role management.
- [x] Add a Reactivate button inside each revoked Container User card (no separate reactivation panel).
- [x] Implement quota management.
- [x] Implement container assignments.
- [x] Implement ownership transfers.
- [x] Display user allocations against quotas.
- [x] Display Admin host allocation summaries for RAM, CPU and disk pools, including reservations and remaining allocatable capacity.
- [x] Display unmanaged/missing-container blockers and a manual refresh in the host-allocation UI.
- [x] Implement the command terminal interface.
- [x] Display command output and exit status.
- [ ] Handle loading, empty and error states.
- [ ] Display stale metrics and LXD-unavailable states.
- [x] Verify responsive layouts.
- [x] Verify Admin-only API routes, non-Admin denial and assigned-container authorization through backend tests.
- [ ] Complete final browser-level checks of role-specific layout and missing/empty/error states.

## Phase 9 — Security and Correctness Testing (P0/P1)

- [x] Test login and logout.
- [x] Test uninvited Google accounts.
- [x] Test bootstrap Admin behavior.
- [x] Test session expiration and revocation in the backend authentication tests.
- [x] Test CSRF protection.
- [x] Test Admin-only operations.
- [x] Test unassigned-container access.
- [x] Test cross-user terminal access.
- [x] Test invalid names and resource values.
- [x] Test resource quota enforcement.
- [x] Verify real quota rejection before privileged LXD creation.
- [ ] Test concurrent allocation requests.
- [x] Test container ownership transfers.
- [x] Exercise the invitation, revoke and reactivate user lifecycle through the Admin dashboard (manual verification reported).
- [x] Test unmanaged-container protections.
- [ ] Test dangerous LXD configuration attempts.
- [x] Test command execution limits.
- [x] Test error handling when LXD is unavailable.
- [ ] Test recovery after LXD becomes available.
- [ ] Test TinyFlux retention and historical queries.
- [x] Test restart and persistence behavior.
- [ ] Review dependency and credential handling.
- [ ] Verify that no real secrets have been committed.
- [x] Test per-user allocation calculations and stopped-container accounting.
- [x] Test quota-validation helpers and conservative host-budget blocking.

## Phase 10 — Deployment (P1)

- [ ] Create complete service-account setup instructions in the repository documentation.
- [x] Configure the deployment environment and protected production directories.
- [x] Add the Falcon systemd service.
- [x] Add the independent collector systemd service.
- [x] Configure static Astro deployment through Nginx.
- [x] Configure systemd startup ordering and database initialization dependency.
- [ ] Fully verify automatic systemd restart policies for both Falcon and the independent collector.
- [ ] Document service logging and troubleshooting.
- [x] Verify a fresh database initialization.
- [ ] Complete service recovery verification, including unexpected collector failure.
- [ ] Verify recovery after a host reboot.
- [x] Verify that the application works without development servers.
- [ ] Verify authenticated browser access through production HTTPS.
- [x] Verify automatic Falcon service recovery after an unexpected SIGKILL; systemd restarted Gunicorn, the restart counter increased, and the Nginx-proxied API health check passed (2026-10-08).

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

- [ ] Replace the template internship-assignment README and backend/dashboard placeholders with real project setup and usage instructions.
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
- [x] Confirm the collector runs independently.
- [x] Confirm historical metrics survive a restart.
- [ ] Confirm resource measurements are published.
- [ ] Confirm all configuration variables are documented.
- [ ] Confirm no secrets are present in Git history.
- [ ] Review code for dead code and unnecessary dependencies.
- [ ] Ensure every submitted component can be explained.
- [ ] Verify the required submission instructions from the task email.
- [x] Push the working implementation and merge it into `main`.
- [ ] Push the **final** verified implementation, documentation and benchmark results to `main`.
- [ ] Submit the repository link before October 9, 2026.