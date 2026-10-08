# Hobby Server Monitor — Security Threat Model

Status: implementation-informed design review; not a penetration-test certificate
Reviewed against: `backend/app/main.py`, authentication middleware, authorization services, LXD integration, deployment unit files, and `REPORT.md`
Date: October 8, 2026

## 1. Scope and assumptions

The system is a **single-host** Ubuntu/LXD management dashboard. It serves an Astro static frontend using Nginx, proxies `/api` and `/auth` to the Falcon backend, persists application state in SQLite, and runs a separate LXD metrics collector that writes to TinyFlux. The backend and collector run as service account `hsm` with access to the local LXD administrative socket through group membership.

Assumptions: the Ubuntu host and the package supply chain are administered by a trusted operator; Google performs OAuth identity verification; container users are not given access to the host LXD socket; and the system is deployed only on appropriately configured trusted hardware. These are **assumptions**, not validated guarantees. The browser, request bodies, OAuth parameters, in-container commands, and externally created LXD containers are untrusted inputs.

Excluded: multihost orchestration, hostile kernel escape testing, public Internet penetration testing, and secure isolation between different users intentionally sharing the same container.

## 2. Assets and impact

| Asset | Importance | Consequence of compromise |
| --- | --- | --- |
| Local LXD administrative socket | Critical | Potential host-equivalent privilege and container compromise |
| OAuth client secret and `SESSION_SECRET` | High | Account/session compromise or identity-flow abuse |
| SQLite users, assignments, quotas, sessions and audit logs | High | Authorization bypass, false ownership and loss of accountability |
| LXD containers and stored data | High | Data loss, arbitrary code execution and resource exhaustion |
| TinyFlux measurements | Medium | Incorrect monitoring, lost history, disk consumption |
| Browser sessions and CSRF tokens | High | Unauthorized privileged API requests |
| Nginx/TLS private key | High | Impersonation of the deployed HTTPS service |

## 3. Data flow and trust boundaries

```text
Untrusted browser
   |
   | HTTPS, session cookies, X-CSRF-Token
   v
Nginx (static Astro files and /api,/auth proxy)
   |
   | local HTTP 127.0.0.1:8000
   v
Falcon authentication middleware and authorization services
   |                         |
   | SQLite                 | pylxd Unix socket [CRITICAL boundary]
   v                         v
Users/sessions/audit       LXD daemon -> containers

Independent systemd collector -> LXD daemon -> TinyFlux
Google OAuth identity provider -> Falcon OAuth callback
```

The main privilege transition is **from Falcon application decisions to host-privileged LXD administration**. The frontend hiding a button is not authorization. The collector also has highly privileged LXD access and deserves the same protection as Falcon.

## 4. Threats, defenses and remaining risk

| ID | Threat / STRIDE class | Implemented or documented controls | Residual risk and evidence |
| --- | --- | --- | --- |
| T1 | Spoofing: attacker claims Admin identity | Google OAuth with state/PKCE; verified identity; explicit `BOOTSTRAP_ADMIN_EMAIL`; invitation requirement; server-side session | Real end-to-end rejection of an uninvited Google account on the deployed HTTPS endpoint remains **unverified**; backend unit tests exist |
| T2 | Tampering: ordinary user calls Admin endpoint directly | Deny-by-default Falcon authentication; `required_role` on sensitive resources; `require_admin` in service methods; user/container ownership checks | Every new route needs regression tests; UI hiding is not a defense |
| T3 | Tampering: CSRF on state changes | Per-session CSRF token required in `X-CSRF-Token` for unsafe methods; HttpOnly/SameSite session cookie | Browser/XSS compromise remains possible if frontend dependencies or injected content are compromised |
| T4 | Elevation of privilege: Falcon/collector compromise reaches LXD socket | Dedicated `hsm` account, restricted API operations, Nginx loopback proxy, systemd hardening and input validation | **Critical residual risk:** unrestricted local LXD administrative access can effectively confer host-root control; account separation does not eliminate this. No separate privileged broker exists |
| T5 | Elevation of privilege: container command leads to host access | Container-specific access checks; running-container requirement; non-root identity for Container Users; no host shell; bounded command length, timeout, output and concurrency | Admin deliberately runs root in authorized containers; untrusted workloads and container escapes remain risks |
| T6 | Tampering: externally created container inserted into managed quota accounting | Admin-only explicit adoption; verify owner, quota, security and LXD state; immutable application IDs | External LXD drift, manual renaming and misconfiguration remain operational risks; full fault-injection coverage incomplete |
| T7 | Denial of service: infinite exec output, long commands, request amplification | Configurable terminal limits; cross-process concurrency locks; collector polling independent of active tabs; service restart policies | No extended high-concurrency or large-fleet benchmark; LXD itself remains a shared resource |
| T8 | Tampering: quotas bypassed by concurrent operations or external edits | SQLite transactions, allocation lock, quota validation, LXD pre-update state comparison, disk shrink rejected | Concurrent adversarial allocations and all LXD failure paths not exhaustively tested |
| T9 | Information disclosure: credentials in Git, logs or HTTP | `.env` ignored, root-owned production env (`0600`), secure HTTPS cookies, protected TLS key, token hashes in database, terminal audit excludes raw command/output | Git-history and third-party logs require final audit; prior accidentally displayed session secret was rotated |
| T10 | Repudiation: privileged actions without audit | SQLite audit events for user changes, container changes, and command-execution metadata | Audit table integrity depends on DB/host security; no external append-only audit sink |
| T11 | Monitoring integrity/availability: LXD outage, stale metrics | Collector logs errors and retries future cycles; raw and five-minute TinyFlux storage; systemd recovery; API errors | Full real-LXD outage/recovery measurement not completed; long-duration file growth unmeasured |
| T12 | Network interception / HTTPS misconfiguration | Nginx HTTPS locally tested using mkcert, `COOKIE_SECURE=true`, strict protected environment and TLS key permissions | Local mkcert certificates are not a substitute for a publicly trusted certificate and real deployment hostname |

## 5. Critical privilege-boundary decision

Falcon and the collector do **not** run as Unix `root`, but their access to the privileged LXD Unix socket is still potentially **host-root-equivalent**. `NoNewPrivileges=true` and filesystem hardening improve process containment but do **not** remove the LXD socket's administrative authority. A compromise of either service is therefore high impact. Do not promise ordinary-user isolation merely because `hsm` is a separate Linux account.

A stronger later design would run the public Falcon API **without** LXD administrative socket access and delegate only allowlisted, typed operations to a carefully isolated local broker, with separate credentials, authorization auditing, and operational limits. This is **not implemented** and must not be checked off as complete.

## 6. Security validation matrix

| Check | Current evidence / status |
| --- | --- |
| Backend session authentication, expiration, revocation and CSRF | Automated backend unit tests exist; final local CI run required |
| Admin role and assigned-container authorization | Backend tests and previously reported manual acceptance tests |
| Quota accounting, resource drift, disk-shrink rejection | Reported 12-item real-LXD verification passed |
| Collector restart, Falcon restart and host reboot | Local deployment verification reported passed |
| Local HTTPS health, Google Admin bootstrap | Locally verified; SQLite contained one active Admin |
| Uninvited Google account on deployed HTTPS | **Pending** |
| Git history and credential disclosure review | **Pending until scanner and manual review** |
| Dangerous LXD operations / hostile containers | **Not exhaustively penetration tested** |
| Publicly trusted remote HTTPS deployment | **Not verified** |
| Long-duration metrics, LXD outage/recovery and load benchmarks | **Pending** |

## 7. Security operations and response

1. Protect `/etc/hobby-server-monitor/hsm.env`, TLS private keys, SQLite/TinyFlux data and host access controls; never print secrets to CI logs or share them in issue reports.
2. Treat the `hsm` account and LXD socket as highly privileged, and restrict membership in the `lxd` group.
3. Rotate and revoke a suspected exposed OAuth secret, session secret or TLS private key; invalidate affected sessions. Removing a credential from the current checkout does not erase Git history.
4. Review journal entries, database audit logs and service restarts following unexpected administrative behavior.
5. Backup SQLite and TinyFlux with correct permissions and perform restore tests on disposable systems.
6. Apply regular host/LXD and application dependency security updates after testing.
7. Run the automated test suite and manually verify Admin/Container User boundaries before enabling remote network exposure.

## 8. Overall conclusion

The design implements meaningful safeguards against unauthenticated API access, cross-user container access, CSRF, unsafe inputs and unlimited terminal operations. However, the highest-impact residual threat remains the **privileged LXD socket accessible to the Falcon backend and collector**. This threat must be disclosed, and the installation should not be treated as production-hardened against arbitrary hostile web input until the privilege boundary and outstanding security tests have been strengthened.
