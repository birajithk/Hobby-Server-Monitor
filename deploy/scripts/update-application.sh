#!/usr/bin/env bash
# Hobby Server Monitor: guarded, code-only application update.
# Existing host only. NEVER copies environment files, DBs, or TinyFlux data.
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage: sudo bash deploy/scripts/update-application.sh [--check|--apply]
  --check   Read-only preflight and change summary (default).
  --apply   Stage new backend/static assets, stop API + collector briefly,
            deploy, restart, health check; automatically restore old files
            if installation or health verification fails.

Build dashboard/dist as an ordinary user before running this script.
This is a CODE-ONLY updater: dependency changes and any app/db changes
require a separately reviewed migration/dependency deployment procedure.
It does not change systemd units, Nginx, secrets, SQLite, TinyFlux or LXD.
EOF
}

if (( $# > 1 )); then usage >&2; exit 2; fi
mode="${1:---check}"
case "$mode" in
  --check|--apply) ;;
  --help|-h) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac
if (( EUID != 0 )); then
  echo 'ERROR: Use sudo to inspect protected production paths.' >&2
  exit 1
fi

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
installed_backend=/opt/hobby-server-monitor/backend
installed_app="$installed_backend/app"
static_parent=/srv/hobby-server-monitor
installed_www="$static_parent/www"
installed_environment=/etc/hobby-server-monitor/hsm.env
state_dir=/var/lib/hobby-server-monitor
api_unit=hobby-server-monitor-api
collector_unit=hobby-server-monitor-collector

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '%s\n' "$*"; }

for program in systemctl cmp diff curl find tar chmod chown mktemp mv rm stat; do
  command -v "$program" >/dev/null 2>&1 || fail "Missing command: $program"
done

for path in "$repo_root/backend/app" "$repo_root/dashboard/dist" \
            "$installed_app" "$installed_www" \
            "$state_dir" "$installed_backend/.venv"; do
  [[ -d "$path" && ! -L "$path" ]] || fail "Expected real directory: $path"
done
for path in "$repo_root/backend/requirements.txt" \
            "$installed_backend/requirements.txt" \
            "$repo_root/dashboard/dist/index.html" \
            "$installed_environment"; do
  [[ -f "$path" && ! -L "$path" ]] || fail "Expected regular file: $path"
done
[[ -x "$installed_backend/.venv/bin/python" && \
   -x "$installed_backend/.venv/bin/gunicorn" ]] || fail 'Installed virtualenv not ready.'
[[ "$(stat -c '%a:%U:%G' "$installed_environment")" == '600:root:root' ]] ||
  fail 'Protected environment must remain root:root mode 0600.'
[[ -f "$state_dir/app.db" && -f "$state_dir/metrics.csv" ]] ||
  fail 'Expected production SQLite or TinyFlux file missing.'

# A production upgrade of SQL schemas/dependencies requires a backup and
# explicit migration plan. Refuse instead of trying it implicitly.
if ! cmp -s "$repo_root/backend/requirements.txt" \
            "$installed_backend/requirements.txt"; then
  fail 'requirements.txt differs from deployed version. Do not use this updater.'
fi
if ! diff -qr --exclude='__pycache__' --exclude='*.pyc' \
             "$repo_root/backend/app/db" "$installed_app/db" >/dev/null; then
  fail 'backend/app/db differs from deployed version. Review migrations separately.'
fi

if [[ -n "$(find "$repo_root/backend/app" "$repo_root/dashboard/dist" \
  \( -type l -o -name '.env' -o -name '*.pem' -o -name '*.key' \) -print -quit)" ]]; then
  fail 'Source app/static tree contains a symlink or sensitive-looking file.'
fi
for unit in "$api_unit" "$collector_unit" nginx; do
  systemctl is-active --quiet "$unit" || fail "$unit is not active."
done
if ! curl -fsS --max-time 5 http://127.0.0.1:8000/api/health >/dev/null; then
  fail 'Current local Falcon API is unhealthy.'
fi
if ! curl -fsS --max-time 5 http://127.0.0.1:8080/ >/dev/null; then
  fail 'Current Nginx static frontend is unhealthy.'
fi

if diff -qr --exclude='__pycache__' --exclude='*.pyc' \
          "$repo_root/backend/app" "$installed_app" >/dev/null; then
  info 'UNCHANGED: Falcon backend app tree.'
else
  info 'UPDATE: Falcon backend app tree.'
fi
if diff -qr "$repo_root/dashboard/dist" "$installed_www" >/dev/null; then
  info 'UNCHANGED: Static Astro build.'
else
  info 'UPDATE: Static Astro build.'
fi
info 'GUARD: Dependencies unchanged; app/db unchanged.'
info 'GUARD: Persistent state and protected environment are outside update targets.'

if [[ "$mode" == '--check' ]]; then
  info 'CHECK ONLY: no files, processes, services or databases modified.'
  exit 0
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
old_app="$installed_backend/.app-rollback-$stamp"
old_www="$static_parent/.www-rollback-$stamp"
failed_app="$installed_backend/.app-failed-$stamp"
failed_www="$static_parent/.www-failed-$stamp"
stage_backend=''
stage_web=''
services_stopped=0
app_saved=0
web_saved=0
completed=0

restore_on_exit() {
  local code="$?"
  if (( completed )); then return; fi
  set +e
  trap - EXIT
  printf 'ERROR: Update incomplete. Restoring previous application.\n' >&2
  if (( services_stopped )); then
    systemctl stop "$collector_unit" "$api_unit" >/dev/null 2>&1
  fi
  if (( web_saved )); then
    if [[ -e "$installed_www" ]]; then mv -- "$installed_www" "$failed_www"; fi
    mv -- "$old_www" "$installed_www" || printf 'CRITICAL: Restore frontend manually from %s\n' "$old_www" >&2
  fi
  if (( app_saved )); then
    if [[ -e "$installed_app" ]]; then mv -- "$installed_app" "$failed_app"; fi
    mv -- "$old_app" "$installed_app" || printf 'CRITICAL: Restore backend manually from %s\n' "$old_app" >&2
  fi
  if (( services_stopped )); then
    systemctl start "$api_unit" "$collector_unit" ||
      printf 'CRITICAL: Could not restart restored services; check journalctl.\n' >&2
  fi
  if [[ -n "$stage_backend" && -d "$stage_backend" ]]; then rm -rf -- "$stage_backend"; fi
  if [[ -n "$stage_web" && -d "$stage_web" ]]; then rm -rf -- "$stage_web"; fi
  printf 'Rollback attempted; inspect service status and stored backup directories.\n' >&2
  exit "$code"
}
trap restore_on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Stage on the same filesystem as each final target; never stage in /tmp.
stage_backend="$(mktemp -d "$installed_backend/.hsm-update-stage.XXXXXXXX")"
stage_web="$(mktemp -d "$static_parent/.hsm-update-stage.XXXXXXXX")"

# The repo is read-only source. Ignore local bytecode and caches.
tar -C "$repo_root/backend" \
  --exclude='__pycache__' --exclude='*.pyc' \
  -cf - app | tar -C "$stage_backend" -xf -
cp -a "$repo_root/dashboard/dist/." "$stage_web/"
chown -R root:root "$stage_backend/app" "$stage_web"
chmod -R u=rwX,go=rX "$stage_backend/app" "$stage_web"
PYTHONPYCACHEPREFIX="$stage_backend/.compile-cache" \
  "$installed_backend/.venv/bin/python" -m compileall -q "$stage_backend/app"
info 'STAGED: Backend and static Astro files; existing deployment still running.'

# The collector is stopped as its imported code is being updated too.
systemctl stop "$collector_unit" "$api_unit"
services_stopped=1
mv -- "$installed_app" "$old_app"
app_saved=1
mv -- "$stage_backend/app" "$installed_app"
mv -- "$installed_www" "$old_www"
web_saved=1
mv -- "$stage_web" "$installed_www"
stage_web=''

systemctl start "$api_unit" "$collector_unit"
for unit in "$api_unit" "$collector_unit" nginx; do
  systemctl is-active --quiet "$unit" || fail "Service did not recover: $unit"
done
curl -fsS --retry 6 --retry-connrefused --retry-delay 1 \
  --max-time 5 http://127.0.0.1:8000/api/health >/dev/null ||
  fail 'Falcon health check failed after update.'
curl -fsS --retry 6 --retry-connrefused --retry-delay 1 \
  --max-time 5 http://127.0.0.1:8080/ >/dev/null ||
  fail 'Astro Nginx health check failed after update.'

completed=1
trap - EXIT INT TERM
rm -rf -- "$stage_backend"
info 'PASS: Code-only update applied; services active and HTTP checks passed.'
info "Rollback copy of prior backend: $old_app"
info "Rollback copy of prior frontend: $old_www"
info 'No environment, SQLite, TinyFlux, systemd unit, TLS or LXD configuration changed.'
info 'Next: verify HTTPS browser login, Admin pages, and fresh collector metrics.'
