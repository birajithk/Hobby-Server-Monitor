#!/usr/bin/env bash
# Safe, read-only deployment preflight. Run on an Ubuntu host that is already deployed.
set -euo pipefail

fail=0
pass() { printf 'PASS: %s\n' "$1"; }
warn() { printf 'WARN: %s\n' "$1"; }
check_service() {
  local unit="$1"
  if systemctl is-active --quiet "$unit"; then pass "$unit is active";
  else warn "$unit is not active"; fail=1; fi
}

printf 'Hobby Server Monitor — read-only deployment check\n'
for cmd in systemctl curl nginx lxc; do
  if command -v "$cmd" >/dev/null 2>&1; then pass "$cmd command found";
  else warn "$cmd command unavailable"; fail=1; fi
done

for unit in hobby-server-monitor-api hobby-server-monitor-collector nginx; do
  check_service "$unit"
done

if curl --fail --silent --show-error --max-time 5 \
    http://127.0.0.1:8000/api/health >/dev/null; then
  pass 'Local Falcon API health'
else
  warn 'Local Falcon API health failed'; fail=1
fi

if curl --fail --silent --show-error --max-time 5 \
    https://localhost:8443/api/health >/dev/null; then
  pass 'Local HTTPS API health and TLS trust'
else
  warn 'Local HTTPS API health failed (may not be installed on other hosts)'
fi

for path in /var/lib/hobby-server-monitor/app.db /var/lib/hobby-server-monitor/metrics.csv; do
  if sudo test -f "$path"; then pass "Persistent state present: $path";
  else warn "Missing state file: $path"; fail=1; fi
done

if sudo test -f /etc/hobby-server-monitor/hsm.env; then
  mode=$(sudo stat -c '%a' /etc/hobby-server-monitor/hsm.env)
  if [[ "$mode" == '600' ]]; then pass 'Production environment permissions 0600';
  else warn "Production environment permissions are $mode; expected 600"; fail=1; fi
else
  warn 'Production environment missing'; fail=1
fi

printf '\nNo secrets were displayed and no services were modified.\n'
exit "$fail"
