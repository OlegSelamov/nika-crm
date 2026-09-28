#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/ubuntu/nika-crm"
UNIT_SRC="$APP_DIR/deploy/nika-capital-monitor.service"
UNIT_DST="/etc/systemd/system/nika-capital-monitor.service"

cd "$APP_DIR"
git pull

sudo cp "$UNIT_SRC" "$UNIT_DST"
sudo systemctl daemon-reload
sudo systemctl enable --now nika-capital-monitor
sudo systemctl restart nika-crm

echo
echo "Nika Capital Monitor:"
sudo systemctl --no-pager --full status nika-capital-monitor | sed -n '1,12p'
