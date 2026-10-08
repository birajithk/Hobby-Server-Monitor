# Astro Dashboard — Hobby Server Monitor

This directory contains the **Astro** frontend for Hobby Server Monitor. It provides a browser interface for managing and monitoring an on-premises LXD server through the **Falcon backend**.

The dashboard uses client-side JavaScript and same-origin `/api` and `/auth` endpoints. The browser **does not connect directly to LXD**.

## Features

- Google sign-in and authenticated navigation.
- Container listing, details, current/historical metrics, and an Export CSV download for supported history ranges.
- Container User resource quota overview.
- Restricted, non-interactive container command terminal.
- Admin host information and allocated-resource overview.
- Admin user management, invitations, quotas, and access assignments.
- Admin container creation, explicit adoption of eligible unmanaged LXD containers, lifecycle actions, resource-limit updates, and ownership management.
- Responsive layouts and visibility-aware dashboard polling.

Admins can use **Manage containers → Adopt external** to select an
unmanaged container and active owner; the Falcon backend performs
security, host-capacity and quota checks before adoption.
On **Container Details**, **Export CSV** downloads only the
selected, authorized container's historical metric range.

## Requirements

- Node.js **22.12 or newer**, with npm (as required by this project's Astro version).
- A configured Falcon backend to serve API and authentication requests.
- Google OAuth credentials configured for the URL used during development or deployment.

## Install dependencies

From the repository root:

```bash
cd dashboard
npm ci
```

**Run `npm` in `dashboard/`, not `backend/`**. The frontend's `package.json` is located here.

## Run the development server

From `dashboard/`:

```bash
npm run dev
```

Visit **http://localhost:4321**.

The Astro development configuration proxies `/api` and `/auth` to the Falcon backend on `127.0.0.1:8000`. For local OAuth development, configure the callback URI in `backend/.env` and Google Cloud as:

```dotenv
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:4321/auth/google/callback
COOKIE_SECURE=false
```

Run a **development** Falcon server only if port `8000` is available. If Hobby Server Monitor is already installed under systemd, its Falcon service may already occupy that port; do not start a second Gunicorn instance on the same port.

## Build for production

From `dashboard/`:

```bash
npm ci
npm run build
```

Astro generates static assets in `dist/`. In the deployed setup, **Nginx serves those static files** and reverse-proxies `/api` and `/auth` to the Falcon backend. No continuously running production Astro or Node.js server is required.

On the verified localhost HTTPS deployment, open **https://localhost:8443/**. That endpoint uses a locally trusted development certificate; publicly accessible deployment requires appropriate hostname and certificate configuration.

See `../deploy/README.md` for deployment and recovery instructions.

## Security model

- Same-origin API requests include the application's session cookie.
- State-changing requests supply the CSRF token expected by Falcon.
- Admin-only navigation is hidden from ordinary users, but **UI visibility is not an authorization mechanism**.
- Falcon performs the actual role, session, and container-access checks.
- The dashboard never receives direct access to the local LXD administration socket.

## Useful commands

| Command | Purpose |
| --- | --- |
| `npm ci` | Install dependencies from the lockfile |
| `npm run dev` | Run the local Astro development server |
| `npm run build` | Generate static production files in `dist/` |
| `npm run preview` | Preview the generated static build locally |

## Related documentation

- [`../README.md`](../README.md) — project setup, features, and API reference.
- [`../backend/README.md`](../backend/README.md) — Falcon backend setup and testing.
- [`../deploy/README.md`](../deploy/README.md) — Nginx, systemd, HTTPS, and service recovery.
- [`../REPORT.md`](../REPORT.md) — design choices and measured resource usage.