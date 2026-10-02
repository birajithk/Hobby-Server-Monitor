
# Hobby Server Monitor — Architecture and Design Decisions

Status: Initial design approved
Date: October 2, 2026

This document records the decisions agreed upon before implementation. Any changes made during development must be documented with their rationale.

## 1. Development Environment

- Native Ubuntu 24.04.4 LTS.
- Python 3.12.3.
- Node.js 22.23.0.
- npm 10.9.8.
- Git 2.43.0.
- LXD 5.21.8 LTS.

The development repository is located at:

~/Documents/RoboticGen/Hobby-Server-Monitor

The initial implementation targets a single Linux host.

## 2. Technology Stack

- Falcon: HTTP API and backend.
- Astro: Browser dashboard.
- pylxd: LXD integration.
- SQLite: Application state and administrative records.
- TinyFlux: Time-series metrics.
- Google OAuth 2.0: User authentication.
- systemd: Deployment and service recovery.

All five preferred application technologies are retained.

Rationale: The chosen stack is relatively lightweight, matches the assignment and avoids unnecessary infrastructure.

We will not introduce a heavyweight application framework or a separate database server without a demonstrated need.

## 3. Application Architecture

The application consists of:

1. Astro dashboard.
2. Falcon API.
3. Authentication and authorization services.
4. Container, user and quota services.
5. A narrowly defined pylxd integration layer.
6. SQLite database.
7. Independent metrics collector.
8. TinyFlux database.
9. LXD daemon.

The collector is a separate process, not a background task tied to a browser request or the web-server lifecycle.

The browser never receives direct LXD access.

The Falcon API and collector must not expose arbitrary LXD administration to users.

## 4. Authentication

Use Google OAuth 2.0 with a secure authorization flow, including state validation and PKCE.

Verify Google's returned identity and verified-email status.

Use Google's stable account identifier to bind an existing user record to their Google identity.

The first Admin is identified through BOOTSTRAP_ADMIN_EMAIL.

Do not use a first-user-to-sign-in-wins policy.

Ordinary users must be invited by an Admin before they are allowed to use the application.

A user whose account has been revoked must not regain access merely by signing in to Google.

## 5. Session Management

Use opaque, cryptographically random session identifiers stored server-side in SQLite.

The browser receives a session cookie.

Cookie security:

- HttpOnly enabled.
- SameSite protection.
- Secure enabled when using HTTPS.
- Restrictive cookie scope.
- No session tokens exposed in frontend JavaScript.

Initial session lifetime: 24 hours, configurable.

Logout invalidates the server-side session and clears the cookie.

Revoking a user invalidates their active sessions.

Role changes must take effect on subsequent requests.

State-changing requests must be protected against CSRF.

Production access must use HTTPS. Local HTTP development is permitted only with appropriately documented development settings.

## 6. Authorization

Use centralized authentication middleware in Falcon.

Use service-layer authorization for operation-specific and container-specific permissions.

Apply a deny-by-default policy.

The API must enforce permissions regardless of frontend visibility.

An Admin can manage containers, users, quotas and assignments.

A Container User can view metrics and execute commands only in assigned containers.

Container Users cannot create, delete, restart, stop, freeze or modify containers.

Unauthorized access to an existing, unassigned container must return HTTP 403.

Avoid exposing unnecessary information about resources through errors.

The final authorization decision is always made by the Falcon backend.

## 7. Container Ownership

Every application-managed container has one owner.

Each managed container also has an immutable application identifier, independent of its mutable LXD name.

The owner is responsible for the container's resource allocation.

Multiple users may have access assignments for a container.

Access assignment does not imply ownership.

The owner must have an appropriate access assignment.

Revoking an ordinary user's access does not change ownership or quota accounting.

## 8. Ownership Transfer and User Removal

Ownership transfers are Admin-only operations.

The new owner's remaining quota must be sufficient for the container's allocations.

The transfer must update ownership and resource accounting atomically.

A user who owns containers cannot be deleted until their containers have been transferred or deleted.

An Admin cannot remove or demote the last active Admin.

Deleting a container removes active assignments while preserving the appropriate audit history.

## 9. Resource Quotas

Quotas measure allocated limits rather than instantaneous usage.

Each user has a maximum allocation for:

- RAM.
- CPU cores.
- Disk storage.

For example, a container with a 2 GiB RAM limit consumes 2 GiB of its owner's RAM quota even when its actual usage is lower.

Stopped containers continue to count against their owner's allocated quota.

Shared access does not duplicate quota accounting.

When an allocation exceeds the remaining quota, reject the operation and return an informative error.

The same checks apply to container creation, resource increases, adoption and ownership transfers.

## 10. Host Resource Accounting

Use a conservative allocation policy.

Managed container allocations must not exceed the configured host resource budget.

Reserve sufficient resources for Ubuntu, LXD and the monitoring application.

The budget and applicable bounds must be derived from actual host capacity, existing allocations and documented reserve settings.

CPU core allocation and CPU allowance percentage are distinct.

Disk allocation must also account for the selected storage pool's available capacity.

Actual usage and allocated limits must be displayed separately.

Quota-sensitive operations must be serialized or otherwise protected against concurrent requests that would bypass resource accounting.

## 11. External Containers

Discover containers created outside the application by querying LXD.

Unknown containers are marked as unmanaged.

Admins may initially view their state and available metrics.

Unmanaged containers are read-only through the application.

Adoption requires explicit Admin action.

During adoption:

- Assign an owner.
- Establish resource limits.
- Validate the owner's quota.
- Validate host capacity.
- Establish the intended access assignments.

Failed adoption must leave the external container unchanged.

Unmanaged containers must be considered when calculating actual host resource availability.

A managed container deleted outside the application must not leave active, misleading assignments or allocations indefinitely.

## 12. Container Configuration and Security

Create managed containers as unprivileged Linux containers.

Use restrictive configurations wherever supported, including:

- security.privileged=false.
- security.nesting=false.
- Isolated UID/GID mappings where supported and provisioned correctly.
- Appropriate process-count limits.
- Explicit CPU, RAM and disk limits.

Do not expose arbitrary low-level LXD configuration through the API.

Do not allow arbitrary host filesystem mounts, LXD socket mounts or dangerous device passthrough through the container creation form.

Discover usable images, networks, profiles and storage pools at runtime.

Validate every submitted configuration value on the server.

Configuration changes must preserve restrictive security defaults.

## 13. LXD Privilege Boundary

Use pylxd through the local LXD Unix socket.

Run Falcon under a dedicated Linux service account rather than directly as root.

For the initial implementation, the trusted backend uses a narrowly defined LXD service layer.

The API exposes only approved container-management operations.

Authentication, authorization and validation must be completed before privileged operations.

Important residual risk:

A process with unrestricted access to the LXD administrative socket has extensive control over instances and can effectively gain host-level privileges.

A dedicated Linux service account does not remove this risk.

The entire Falcon process must therefore be treated as a highly privileged security component.

A separately isolated privileged LXD broker is a potential future improvement and is not part of the initial architecture.

The threat model must explicitly acknowledge this limitation.

## 14. Terminal Design

Implement real, non-interactive command execution through pylxd.

The initial terminal accepts a command and returns:

- Exit code.
- Standard output.
- Standard error.

A persistent interactive shell and WebSocket terminal are deferred.

Admins may execute commands in all managed containers.

Container Users may execute commands only in assigned containers.

Admin terminal execution uses the intended administrative identity inside the container.

Container User execution must use a provisioned non-root account without unrestricted sudo access.

The existence and permissions of that account must be verified before enabling terminal access.

The terminal must not execute user commands on the Linux host.

Initial safeguards:

- Configurable command-length limit.
- Initial execution timeout of 30 seconds.
- Bounded output size.
- Bounded simultaneous execution.
- No command execution in stopped containers.
- Audit records for execution metadata.

Execution cancellation must be verified; an HTTP timeout alone is insufficient.

Commands may contain shell instructions because this is real terminal functionality. Security depends on authorization, the in-container execution identity and container isolation.

## 15. Metrics Collection

Run the collector independently of the Falcon web server and Astro dashboard.

Poll all containers every 10 seconds.

Store metrics in TinyFlux.

Do not create an independent collector for each browser session.

If LXD is unavailable:

- Record the collection failure.
- Avoid writing fabricated zero measurements.
- Preserve available historical data.
- Continue subsequent polling attempts.
- Resume collection when LXD recovers.

Network rates are calculated from successive cumulative counters.

Handle counter resets and missing observations appropriately.

Use stable container identifiers in historical data rather than relying exclusively on mutable container names.

## 16. Metrics Retention

Initial retention policy:

- Raw samples: 24 hours.
- Five-minute aggregates: 30 days.
- Older measurements: deleted through scheduled maintenance.

Aggregation and retention must be implemented and tested.

Historical API requests should return a bounded number of points appropriate for the requested chart interval.

Do not transfer every raw sample for a 24-hour chart when a smaller aggregated dataset is sufficient.

## 17. Dashboard Updates

Use ordinary HTTP polling.

Initially refresh visible dashboard data at approximately 10-second intervals.

Reduce or suspend requests when the browser tab is hidden.

The collector continues independently when no browser is connected.

Do not introduce WebSockets merely for ordinary metric updates.

Display last-known values as stale when the collector or LXD is unavailable.

Provide explicit loading, empty, error and unavailable states.

## 18. Storage

SQLite stores:

- Users.
- Google identities.
- Invitations.
- Sessions.
- Container ownership and metadata.
- Container access assignments.
- Resource quotas.
- Audit events.
- Required application configuration and state.

TinyFlux stores timestamped container measurements.

The default LXD dir storage pool is not assumed to provide the required disk-quota guarantees.

Use a storage backend with verified per-container disk-limit support.

A suitable ZFS-backed LXD pool is the proposed development choice, subject to available disk space and verification.

Do not create a large loop-backed storage pool until sufficient host disk space is available.

## 19. Failure Handling

Use clear API errors and appropriate HTTP status codes.

Distinguish:

- Unauthenticated requests.
- Unauthorized requests.
- Invalid inputs.
- Quota violations.
- Missing resources.
- LXD unavailability.
- Internal failures.

Do not expose stack traces, session secrets, OAuth credentials or privileged configuration details to the browser.

Apply appropriate timeouts and bounded retries.

Do not blindly retry destructive or non-idempotent operations.

Prevent partially completed operations from leaving inconsistent accounting wherever possible.

## 20. Deployment

Use systemd to manage long-running application services.

The Falcon API and metrics collector must have independent service lifecycles.

Document startup ordering, restart behavior, service permissions, configuration and log inspection.

Verify recovery after a reboot and after an unexpected collector restart.

The browser frontend must not control whether the collector is running.

## 21. Resource Efficiency

Measure actual memory and CPU usage under multiple conditions:

- Idle API and collector.
- Active containers.
- One dashboard tab.
- Multiple dashboard tabs.
- No open dashboard tabs.
- Temporary LXD failure.

Record the measurement tools, commands, duration and machine configuration.

Publish only real measurements in REPORT.md.

## 22. Planned Bonuses

Priority bonuses:

1. Automated unit, integration and security tests.
2. GitHub Actions CI.
3. Reproducible and documented systemd deployment.
4. Documented threat model.

Optional bonus:

5. CSV export of authorized historical metrics.

Deferred:

- Interactive WebSocket terminal.
- Container snapshots.
- Automated alerting.
- Multihost management.
- Other enhancements that threaten baseline completeness.

## 23. Documentation and AI Usage

README.md must describe actual setup and implementation behavior.

REPORT.md must describe actual development work, measurements, problems, limitations and AI usage.

AI assistance must be disclosed transparently.

All generated or suggested code must be reviewed, understood and tested before submission.

## 24. Known Initial Limitations

The initial design does not provide a separately isolated LXD privilege broker.

The terminal is non-interactive.

The application targets a single host.

The system is not intended to provide strong isolation between mutually untrusted users sharing the same container.

These limitations must be revisited if the implementation or threat model changes.

## 25. Remaining Implementation Verification

The following must be verified during implementation:

- Exact pylxd APIs and version compatibility.
- Actual host-resource discovery.
- Disk quota enforcement on the selected storage driver.
- Safe CPU allowance configuration.
- Supported image aliases and profiles.
- Correct UID/GID mapping.
- Non-root terminal account provisioning.
- Command cancellation and cleanup.
- SQLite transaction and concurrency behavior.
- TinyFlux aggregation and deletion.
- Google OAuth redirect and session behavior.
- Service startup and recovery.

A design decision is not evidence of successful implementation. These items must be tested before being marked complete.
