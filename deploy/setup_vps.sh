#!/usr/bin/env bash
# One-time setup for running B-Commie natively on a VPS (no Docker).
#
# Usage (as a sudo-capable user, from inside the extracted project folder):
#   chmod +x deploy/setup_vps.sh
#   ./deploy/setup_vps.sh
#
# What this does:
#   1. Creates a dedicated, unprivileged system user "bcommie" (skipped if it
#      already exists) — the bot process should never run as root.
#   2. Copies the current project directory into /home/bcommie/b-commie-v2.
#   3. Creates a Python venv there and installs the project.
#   4. Installs and enables the systemd service (deploy/bcommie.service).
#
# You still need to create/edit .env yourself before (or right after)
# running this script — see .env.example.
set -euo pipefail

PROJECT_NAME="b-commie-v2"
SERVICE_USER="bcommie"
DEST="/home/${SERVICE_USER}/${PROJECT_NAME}"

if ! command -v python3.13 >/dev/null 2>&1; then
    echo "python3.13 not found. Install it first, e.g.:"
    echo "  sudo apt update && sudo apt install -y python3.13 python3.13-venv"
    exit 1
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    echo "==> Creating system user '$SERVICE_USER'"
    sudo useradd --system --create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

echo "==> Copying project to $DEST"
sudo mkdir -p "$DEST"
sudo rsync -a --exclude ".venv" --exclude "__pycache__" ./ "$DEST/"
sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$DEST"

if [ ! -f "$DEST/.env" ]; then
    echo "==> No .env found in $DEST — copying .env.example (EDIT IT before starting the service!)"
    sudo -u "$SERVICE_USER" cp "$DEST/.env.example" "$DEST/.env"
fi

echo "==> Creating virtualenv and installing dependencies"
sudo -u "$SERVICE_USER" python3.13 -m venv "$DEST/.venv"
sudo -u "$SERVICE_USER" "$DEST/.venv/bin/pip" install --upgrade pip
sudo -u "$SERVICE_USER" "$DEST/.venv/bin/pip" install -e "$DEST"

echo "==> Installing systemd service"
sudo cp "$DEST/deploy/bcommie.service" /etc/systemd/system/bcommie.service
sudo systemctl daemon-reload

echo
echo "Setup complete. Next steps:"
echo "  1. Edit $DEST/.env with your TOKEN, OWNER_IDS, MONGO_URI, POSTGRES_DSN"
echo "  2. Apply the PostgreSQL schema once (see README.md, 'Migrations')"
echo "  3. sudo systemctl enable --now bcommie"
echo "  4. sudo journalctl -u bcommie -f     # watch it start up"
