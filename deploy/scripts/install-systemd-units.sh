#!/usr/bin/env bash
# Hobby Server Monitor: install/reconcile systemd unit definitions on an
# already-provisioned host. Does not start/stop/restart services or touch data.
set -Eeuo pipefail

usage() {
  printf 'Usage: sudo bash %s [--check|--apply]\n' "$0"
  printf '  --check  Validate prerequisites and show proposed changes (default).\n'
  printf '  --apply  Back up changed units, install, and daemon-reload only.\n'
}

if (( $# > 1 )); then usage >&2; exit 2; fi
mode="${1:---check}"
case "$mode" in
  --check|--apply) ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac
if (( EUID != 0 )); then
  printf 'ERROR: Run with sudo; protected files must be checked as root.\n' >&2
  exit 1
fi

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
source_dir="$repo_root/deploy/systemd"
target_dir=/etc/systemd/system
backup_parent=/var/backups/hobby-server-monitor/systemd
units=(
  hobby-server-monitor-db-init.service
  hobby-server-monitor-api.service
  hobby-server-monitor-collector.service
)

for command_name in systemctl systemd-analyze cmp install stat id getent; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'ERROR: Required command missing: %s\n' "$command_name" >&2
    exit 1
  fi
done
for unit in "${units[@]}"; do
  if [[ ! -f "$source_dir/$unit" || -L "$source_dir/$unit" ]]; then
    printf 'ERROR: Missing or symlinked unit source: %s\n' "$source_dir/$unit" >&2
    exit 1
  fi
done

# This tool deliberately does not create the highly privileged hsm identity.
# LXD socket membership is effectively host-level control.
if ! id hsm >/dev/null 2>&1 || ! getent group lxd >/dev/null; then
  printf 'ERROR: Existing hsm account and lxd group required.\n' >&2
  exit 1
fi
if ! id -nG hsm | tr ' ' '\n' | grep -qx lxd; then
  printf 'ERROR: hsm is not a member of the privileged lxd group.\n' >&2
  exit 1
fi
if [[ ! -x /opt/hobby-server-monitor/backend/.venv/bin/python ||
      ! -x /opt/hobby-server-monitor/backend/.venv/bin/gunicorn ||
      ! -d /var/lib/hobby-server-monitor ||
      ! -f /etc/hobby-server-monitor/hsm.env ]]; then
  printf 'ERROR: Existing application, virtualenv, state directory, or environment missing.\n' >&2
  exit 1
fi
config_mode="$(stat -c '%a:%U:%G' /etc/hobby-server-monitor/hsm.env)"
if [[ "$config_mode" != '600:root:root' ]]; then
  printf 'ERROR: Production environment should be root:root 0600.\n' >&2
  exit 1
fi

printf 'Checking all three systemd unit definitions...\n'
source_files=()
for unit in "${units[@]}"; do source_files+=("$source_dir/$unit"); done
systemd-analyze verify "${source_files[@]}"

changes=()
for unit in "${units[@]}"; do
  if [[ -f "$target_dir/$unit" ]] && cmp -s "$source_dir/$unit" "$target_dir/$unit"; then
    printf 'UNCHANGED: %s\n' "$unit"
  else
    printf 'CHANGE:    %s\n' "$unit"
    changes+=("$unit")
  fi
done
if [[ "$mode" == '--check' ]]; then
  printf 'CHECK ONLY: %d unit(s) would change; no files or services modified.\n' "${#changes[@]}"
  exit 0
fi
if (( ${#changes[@]} == 0 )); then
  printf 'PASS: All unit files already match; no daemon-reload necessary.\n'
  exit 0
fi

backup_dir="$backup_parent/$(date -u +%Y%m%dT%H%M%SZ)-$$"
install -d -o root -g root -m 0700 "$backup_dir"
installed=()
rollback() {
  local result="$?"
  trap - ERR
  set +e
  printf 'ERROR: Unit installation failed; restoring prior definitions.\n' >&2
  for unit in "${installed[@]}"; do
    if [[ -f "$backup_dir/$unit" ]]; then
      install -o root -g root -m 0644 "$backup_dir/$unit" "$target_dir/$unit"
    else
      rm -f -- "$target_dir/$unit"
    fi
  done
  systemctl daemon-reload
  exit "$result"
}
trap rollback ERR
for unit in "${changes[@]}"; do
  if [[ -f "$target_dir/$unit" ]]; then
    install -o root -g root -m 0600 "$target_dir/$unit" "$backup_dir/$unit"
  fi
  installed+=("$unit")
  install -o root -g root -m 0644 "$source_dir/$unit" "$target_dir/$unit"
done
systemctl daemon-reload
trap - ERR
printf 'PASS: %d unit(s) installed and systemd reloaded.\n' "${#changes[@]}"
printf 'Backups (when a previous unit existed): %s\n' "$backup_dir"
printf 'No service was started, stopped, restarted or enabled.\n'
printf 'Unit file changes take effect for a service when it next starts.\n'
