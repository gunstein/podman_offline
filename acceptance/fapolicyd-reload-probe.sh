#!/usr/bin/env bash
# Backlog item 29: measure whether a user-unit restart right after a fapolicyd
# trust update is denied (203/EXEC, subj_trust=unknown).
#
# Run as the lab admin user (passwordless sudo) on the PROD VM after an
# acceptance run has left the product installed. It changes no policy: it
# trusts one inert text file under its own trust file, then removes it again.
#
#   bash acceptance/fapolicyd-reload-probe.sh [rounds] [unit]
#
# Each round adds or deletes the probe trust, runs fapolicyd-cli --update,
# waits 0, 2, 5, 10 or 15 seconds and restarts the unit (default the help
# service). The summary lists failed restarts per delay and every
# FANOTIFY/AVC denial since the probe started.
set -euo pipefail

rounds=${1:-10}
unit=${2:-myproduct-help.service}
[[ $rounds =~ ^[1-9][0-9]*$ ]] || { echo "rounds must be a positive integer" >&2; exit 2; }
[[ $unit =~ ^myproduct-[a-z0-9-]+\.service$ ]] || { echo "unit must be myproduct-<id>.service" >&2; exit 2; }
probe=/var/lib/myproduct-probe
trust_file=myproduct-probe
results=$(mktemp)
start_epoch=$(date +%s)
start_date=$(LC_ALL=C date -d "@$start_epoch" +%x)
start_time=$(date -d "@$start_epoch" +%H:%M:%S)

user_service() { sudo -n systemctl --user -M myproduct@ "$@"; }

cleanup() {
    sudo -n fapolicyd-cli --file delete "$probe/" --trust-file "$trust_file" >/dev/null 2>&1 || true
    sudo -n fapolicyd-cli --update >/dev/null 2>&1 || true
    sudo -n rm -rf -- "$probe"
    rm -f -- "$results"
}
trap cleanup EXIT

echo "== facts"
rpm -q fapolicyd
sudo -n fapolicyd-cli --list
sudo -n grep -Ev '^\s*(#|$)' /etc/fapolicyd/fapolicyd.conf
user_service is-active "$unit"

sudo -n install -d -m 755 "$probe"
printf 'inert probe file for backlog item 29\n' | sudo -n tee "$probe/probe.txt" >/dev/null
sudo -n chmod 644 "$probe/probe.txt"

echo "== probe: $rounds rounds, unit $unit"
for round in $(seq 1 "$rounds"); do
    for delay in 0 2 5 10 15; do
        # Alternate add and delete so every update really changes the database.
        dump=$(sudo -n fapolicyd-cli --dump-db)
        if grep -qF "$probe/probe.txt" <<< "$dump"; then
            action=delete
        else
            action=add
        fi
        sudo -n fapolicyd-cli --file "$action" "$probe/" --trust-file "$trust_file" >/dev/null 2>&1 || true
        updated=$(date +%s.%N)
        sudo -n fapolicyd-cli --update >/dev/null
        sleep "$delay"
        restarted=$(date +%s.%N)
        status=0
        user_service restart "$unit" || status=$?
        active=0
        user_service is-active --quiet "$unit" || active=$?
        result=$(user_service show -p Result --value "$unit")
        exec_status=$(user_service show -p ExecMainStatus --value "$unit")
        seconds=$(awk -v a="$restarted" -v b="$updated" 'BEGIN { printf "%.1f", a - b }')
        printf '%s %s %s %s %s %s %s %s\n' "$round" "$delay" "$action" "$seconds" \
            "$status" "$active" "$result" "$exec_status" | tee -a "$results"
        if [[ $active != 0 ]]; then
            # Leave the unit running for the next round; record that it was needed.
            echo "restarting $unit again after a failed restart"
            user_service restart "$unit" || true
        fi
    done
done

echo "== failed restarts per delay (round delay action seconds exit active result exec_status)"
for delay in 0 2 5 10 15; do
    total=$(awk -v d="$delay" '$2 == d' "$results" | wc -l)
    failed=$(awk -v d="$delay" '$2 == d && ($5 != 0 || $6 != 0)' "$results" | wc -l)
    echo "delay ${delay}s: $failed of $total failed"
done

echo "== fapolicyd journal since start"
sudo -n journalctl -u fapolicyd --since "@$start_epoch" --no-pager | tail -n 50

echo "== FANOTIFY/AVC since start"
sudo -n env LC_ALL=C ausearch --input-logs -m FANOTIFY,AVC,USER_AVC -ts "$start_date" "$start_time" -i </dev/null \
    | grep -E 'type=(FANOTIFY|AVC|USER_AVC|SYSCALL)' || echo "no FANOTIFY/AVC events"
