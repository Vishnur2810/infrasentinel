#!/usr/bin/env bash
# Run InfraSentinel as an always-on service (starts at boot, restarts if it stops).
#   sudo bash deploy/install-service.sh            install and start
#   sudo bash deploy/install-service.sh --remove   stop and remove
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="${SUDO_USER:-$(whoami)}"
UNIT=/etc/systemd/system/infrasentinel.service
if [ "$1" = "--remove" ]; then
  systemctl disable --now infrasentinel 2>/dev/null || true; rm -f "$UNIT"; systemctl daemon-reload; echo "Removed."; exit 0
fi
[ "$(id -u)" = 0 ] || { echo "Run with sudo:  sudo bash deploy/install-service.sh"; exit 1; }
sed -e "s#__DIR__#$DIR#g" -e "s#__USER__#$USER_NAME#g" "$DIR/deploy/infrasentinel.service" > "$UNIT"
systemctl daemon-reload
systemctl enable --now infrasentinel
echo "InfraSentinel is running as a service: http://127.0.0.1:8765"
echo "Logs:  journalctl -u infrasentinel -f      Stop:  sudo systemctl stop infrasentinel"
echo "Note: laptops still stop serving while asleep. For 24/7 use, run this on an always-on PC, a server or a small cloud VM."
