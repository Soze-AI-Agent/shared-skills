#!/usr/bin/env bash
# Read-only Linux host recon. No sudo, no mutations. Safe to run anywhere.
# Usage: bash host-review.sh
set -u
sec() { printf '\n=== %s ===\n' "$1"; }

sec "HOST / UPTIME / LOAD"
uname -srm; uptime

sec "MEMORY / SWAP"
free -h; swapon --show 2>/dev/null || true

sec "FILESYSTEM (space + inodes)"
df -hT -x tmpfs -x devtmpfs 2>/dev/null; echo; df -i / | tail -1

sec "TOP CPU"
ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -10

sec "TOP MEMORY"
ps -eo pid,comm,%mem,%cpu --sort=-%mem | head -10

sec "FAILED UNITS"
systemctl --failed --no-pager 2>/dev/null | head -15
systemctl --user --failed --no-pager 2>/dev/null | head -15

sec "RESTART-LOOPING UNITS (NRestarts != 0)"
for scope in system user; do
  args=(); [ "$scope" = user ] && args=(--user)
  systemctl "${args[@]}" list-units --type=service --all --no-legend --plain 2>/dev/null \
    | awk '{print $1}' | while read -r u; do
        n=$(systemctl "${args[@]}" show "$u" -p NRestarts --value 2>/dev/null)
        [ -n "${n:-}" ] && [ "$n" != "0" ] && printf '  %-7s %-44s NRestarts=%s\n' "$scope" "$u" "$n"
      done
done
echo "  (no output = no unit has restarted since boot)"

sec "LISTENING SOCKETS"
ss -tulnH 2>/dev/null | awk '{print $1, $5}' | sort -u
sec "EXPOSED ON 0.0.0.0 / * / [::]"
ss -tlnH 2>/dev/null | awk '$4 ~ /(0\.0\.0\.0|\*|\[::\]):/ {print "  "$4}'

sec "ZOMBIES"
ps -eo stat,pid,comm | awk '$1 ~ /Z/'; echo "  (end)"

sec "KERNEL ERRORS THIS BOOT (deduped)"
journalctl -k -p err -b --no-pager 2>/dev/null | sed 's/^\S* \S* //' | sort | uniq -c | sort -rn | head -12
sec "KERNEL LOG SPAM (last 30s, top lines)"
journalctl -k --since "30 sec ago" --no-pager 2>/dev/null | sed 's/^\S* \S* //' | sort | uniq -c | sort -rn | head -5

sec "JOURNAL SIZE"
journalctl --disk-usage 2>/dev/null

sec "DOCKER"
docker system df 2>/dev/null || echo "  no docker / no permission"
docker ps --format '  {{.Names}}: {{.Status}}' 2>/dev/null || true

sec "PACKAGES"
echo -n "  upgradable: "; apt-get -s upgrade 2>/dev/null | grep -c '^Inst'
echo -n "  security-tagged: "; apt list --upgradable 2>/dev/null | grep -c security
ls /var/run/reboot-required >/dev/null 2>&1 && echo "  REBOOT REQUIRED" || echo "  no reboot required"

sec "SERVICES OF INTEREST"
for u in ssh sshd ufw fail2ban unattended-upgrades; do
  printf '  %-22s %s\n' "$u" "$(systemctl is-active "$u" 2>/dev/null || echo n/a)"
done

sec "SSH EFFECTIVE AUTH"
sudo -n sshd -T 2>/dev/null | grep -E '^(passwordauthentication|permitrootlogin|pubkeyauthentication)' \
  || grep -hsE '^[[:space:]]*(PasswordAuthentication|PermitRootLogin|PubkeyAuthentication)' \
       /etc/ssh/sshd_config /etc/ssh/sshd_config.d/*.conf 2>/dev/null \
  || echo "  unreadable without sudo"

sec "KNOBS"
echo -n "  swappiness: "; sysctl -n vm.swappiness 2>/dev/null
cat /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null | sed 's/^/  THP: /'
for d in /sys/block/sd*; do [ -r "$d/queue/scheduler" ] && echo "  $(basename "$d") scheduler: $(cat "$d/queue/scheduler")"; done

sec "BIG USER DIRS (top 10)"
du -sh "$HOME"/* 2>/dev/null | sort -h | tail -10

sec "DONE"
