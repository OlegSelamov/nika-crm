#!/usr/bin/env bash
# Repair ONLY the existing Smart Bridge test IPsec connection, if it is down.
# Run as root from nika-isna-vpn-watchdog.service, not from Flask/Android.
set -euo pipefail

CONNECTION='nika-smartbridge-test'
IPSEC='/usr/sbin/ipsec'
TIMEOUT='/usr/bin/timeout'
LOCK='/run/lock/nika-isna-vpn-watchdog.lock'

exec 9>"$LOCK"
/usr/bin/flock -n 9 || exit 0

if [[ ! -x "$IPSEC" ]]; then
  echo "Smart Bridge watchdog: /usr/sbin/ipsec is not installed" >&2
  exit 1
fi

# If strongSwan is unreachable, fail visibly rather than repeatedly
# initiating connections against a stopped daemon.
if ! status="$("$TIMEOUT" 12 "$IPSEC" statusall)"; then
  echo "Smart Bridge watchdog: cannot retrieve IPsec status" >&2
  exit 1
fi

# Match the *installed* CHILD_SA of this exact connection only.
# A configured connection line or merely established IKE_SA is insufficient.
if printf '%s\n' "$status" |
   /usr/bin/grep -Eq '^nika-smartbridge-test\{[0-9]+\}:[[:space:]]+INSTALLED, TUNNEL,'; then
  exit 0
fi

echo "Smart Bridge watchdog: CHILD_SA missing; initiating $CONNECTION"
"$TIMEOUT" 35 "$IPSEC" up "$CONNECTION"

# Verify after initiating; return failure to journal if connection did not
# become installed, so the next timer tick can retry.
if ! status="$("$TIMEOUT" 12 "$IPSEC" statusall)"; then
  echo "Smart Bridge watchdog: unable to check result" >&2
  exit 1
fi
if printf '%s\n' "$status" |
   /usr/bin/grep -Eq '^nika-smartbridge-test\{[0-9]+\}:[[:space:]]+INSTALLED, TUNNEL,'; then
  echo "Smart Bridge watchdog: tunnel restored"
  exit 0
fi

echo "Smart Bridge watchdog: tunnel not established" >&2
exit 1
