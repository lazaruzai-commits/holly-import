#!/bin/bash
# One-shot deploy for Holly Import at https://andyluciani.com/holly/
#
# Run AFTER cloning this repo to /var/www/holly:
#   sudo -u lazaruz git clone https://github.com/<owner>/holly-import.git /var/www/holly
#   sudo bash /var/www/holly/deploy/setup.sh
#
# What it does (idempotent):
#   - apt installs python3-venv
#   - creates a venv in $APP_DIR/.venv and installs requirements
#   - scaffolds .env from .env.example (you fill in keys at the end)
#   - drops a systemd unit `andyluciani-holly.service` running uvicorn on
#     127.0.0.1:$PORT as $APP_USER, with APP_ROOT_PATH=/holly
#   - inserts a `location /holly/ { ... }` block into your existing
#     /etc/nginx/sites-available/andyluciani.com (with backup)
#   - tests + reloads nginx
#
# What it does NOT do:
#   - touch your existing /, /kairos/, etc blocks
#   - issue or change TLS certs (your andyluciani.com cert covers /holly/)
#   - put your OpenRouter / Telegram keys anywhere — you do that manually

set -euo pipefail

# ---- tunables ----
PORT="${HOLLY_PORT:-3003}"
APP_USER="${APP_USER:-lazaruz}"
APP_DIR="${APP_DIR:-/var/www/holly}"
NGINX_SITE="${NGINX_SITE:-/etc/nginx/sites-available/andyluciani.com}"
SERVICE_NAME="${SERVICE_NAME:-andyluciani-holly}"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
PUBLIC_PATH="${PUBLIC_PATH:-/holly}"

echo "============================================================="
echo " Holly Import deploy"
echo "   user        : $APP_USER"
echo "   app dir     : $APP_DIR"
echo "   listen      : 127.0.0.1:$PORT"
echo "   nginx site  : $NGINX_SITE"
echo "   service     : $SERVICE_NAME"
echo "   public URL  : https://andyluciani.com${PUBLIC_PATH}/"
echo "============================================================="
echo

# ---- preflight ----
[[ $EUID -eq 0 ]]              || { echo "ERROR: run as root (sudo bash $0)"; exit 1; }
command -v nginx >/dev/null    || { echo "ERROR: nginx not installed"; exit 1; }
[[ -f "$NGINX_SITE" ]]         || { echo "ERROR: $NGINX_SITE not found"; exit 1; }
id "$APP_USER" >/dev/null 2>&1 || { echo "ERROR: user $APP_USER does not exist"; exit 1; }
[[ -d "$APP_DIR/.git" ]]       || { echo "ERROR: $APP_DIR is not a git checkout"; exit 1; }
[[ -f "$APP_DIR/app.py" ]]     || { echo "ERROR: $APP_DIR/app.py missing"; exit 1; }

# ---- system packages ----
echo ">>> apt-get install python3-venv ..."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv >/dev/null

# ---- ownership ----
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# ---- venv + python deps ----
echo ">>> creating venv + installing python deps (as $APP_USER) ..."
sudo -u "$APP_USER" bash -lc "
  set -e
  cd '$APP_DIR'
  [[ -d .venv ]] || python3 -m venv .venv
  .venv/bin/pip install --upgrade pip wheel >/dev/null
  .venv/bin/pip install -r requirements.txt
"

# ---- fetch model images on first deploy (best-effort; logged) ----
if [[ ! -f "$APP_DIR/static/img/models/_manifest.json" ]]; then
  echo ">>> downloading model images (one-time) ..."
  sudo -u "$APP_USER" "$APP_DIR/.venv/bin/python" "$APP_DIR/scripts/fetch_images.py" || \
    echo "WARN: image fetch had failures — re-run manually later"
fi

# ---- .env scaffold ----
if [[ ! -f "$APP_DIR/.env" ]]; then
  echo ">>> scaffolding $APP_DIR/.env from .env.example"
  sudo -u "$APP_USER" cp "$APP_DIR/.env.example" "$APP_DIR/.env"
fi
chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"

# ---- systemd unit ----
echo ">>> writing systemd unit at $SERVICE_FILE ..."
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Holly Import — MG/Maxus dealer site (andyluciani.com${PUBLIC_PATH})
After=network.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
Environment=APP_ROOT_PATH=$PUBLIC_PATH
ExecStart=$APP_DIR/.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port $PORT --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=on-failure
RestartSec=5
ProtectSystem=full
ProtectHome=read-only
NoNewPrivileges=true
ReadWritePaths=$APP_DIR/leads $APP_DIR/static/img/models

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service" >/dev/null
systemctl restart "${SERVICE_NAME}.service"

# ---- patch nginx ----
if grep -q "location ${PUBLIC_PATH}/" "$NGINX_SITE"; then
  echo ">>> nginx already has ${PUBLIC_PATH}/ block; leaving as-is"
else
  echo ">>> backing up $NGINX_SITE and inserting ${PUBLIC_PATH}/ block ..."
  cp "$NGINX_SITE" "${NGINX_SITE}.bak.$(date +%s)"

  BLOCK_TMP=$(mktemp)
  cat > "$BLOCK_TMP" <<EOF
    location = ${PUBLIC_PATH} {
        return 301 ${PUBLIC_PATH}/;
    }

    location ${PUBLIC_PATH}/ {
        proxy_pass http://127.0.0.1:$PORT/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300;
    }

EOF

  awk -v blockfile="$BLOCK_TMP" '
    BEGIN {
      while ((getline line < blockfile) > 0) block = block line "\n"
      close(blockfile)
    }
    /^[[:space:]]*location[[:space:]]*\/[[:space:]]*\{/ && !done {
      printf "%s", block
      done = 1
    }
    { print }
  ' "$NGINX_SITE" > "${NGINX_SITE}.new"

  mv "${NGINX_SITE}.new" "$NGINX_SITE"
  rm -f "$BLOCK_TMP"
fi

# ---- test + reload nginx ----
echo ">>> testing nginx config ..."
if nginx -t 2>&1 | tail -3; then
  systemctl reload nginx
  echo ">>> nginx reloaded"
else
  echo "ERROR: nginx -t FAILED. The ${PUBLIC_PATH}/ block may have broken the config."
  echo "       To restore the previous config:"
  echo "         cp \$(ls -t ${NGINX_SITE}.bak.* | head -1) $NGINX_SITE"
  echo "         nginx -t && systemctl reload nginx"
  exit 1
fi

cat <<EOF

=============================================================
 Holly Import deploy complete.
 The service is running but the chat agent and Telegram
 forwarding will be inactive until you fill in:
   - OPENROUTER_API_KEY
   - TELEGRAM_BOT_TOKEN
   - TELEGRAM_CHAT_ID
=============================================================

FINAL STEPS:

  1) Edit env file:
       sudo -u $APP_USER nano $APP_DIR/.env

  2) Restart the service:
       sudo systemctl restart $SERVICE_NAME

  3) Tail logs:
       sudo journalctl -u $SERVICE_NAME -f

  4) Open the site:
       https://andyluciani.com${PUBLIC_PATH}/

To pull future updates:
       sudo -u $APP_USER git -C $APP_DIR pull
       sudo -u $APP_USER $APP_DIR/.venv/bin/pip install -r $APP_DIR/requirements.txt
       sudo systemctl restart $SERVICE_NAME

When ready to map a custom domain (e.g. hollyimport.com):
       Point hollyimport.com DNS A record at this server's IP, then add a
       new server block in /etc/nginx/sites-available/hollyimport.com that
       proxy_passes http://127.0.0.1:$PORT with APP_ROOT_PATH unset (use a
       second systemd unit if you want both subpath + root domain to work,
       or change APP_ROOT_PATH on this unit when you cut over).
EOF
