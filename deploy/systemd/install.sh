#!/usr/bin/env bash
# Install + enable the corticore local-swarm systemd user timers so they run
# without you starting them by hand.
#
# Usage:
#   ./deploy/systemd/install.sh              # install, seed key, enable linger+timers
#   ./deploy/systemd/install.sh --no-enable  # install units only
#
# What this does:
#   1. Installs corticore-swarm.{service,timer} (04:00 Asia/Kolkata)
#   2. Installs corticore-swarm-report.{service,timer} (09:30 Asia/Kolkata)
#   3. Seeds ~/.config/corticore-swarm/env from the repo .env (CURSOR_API_KEY)
#   4. Ensures TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID placeholders exist
#   5. Enables systemd user linger (timers fire even with no GUI login)
#   6. Enables + starts both timers

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
ENV_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/corticore-swarm"
ENABLE=true

for arg in "$@"; do
  case "$arg" in
    --no-enable) ENABLE=false ;;
    --enable) ENABLE=true ;;
    -h|--help)
      sed -n '2,18p' "$0"
      exit 0
      ;;
  esac
done

mkdir -p "$UNIT_DIR" "$ENV_DIR" "$HOME/.local/share/corticore-swarm"

install_unit() {
  local name="$1"
  local src_service="$SCRIPT_DIR/${name}.service"
  local dst_service="$UNIT_DIR/${name}.service"
  sed "s|WorkingDirectory=.*|WorkingDirectory=$REPO_ROOT|" "$src_service" > "$dst_service"
  cp "$SCRIPT_DIR/${name}.timer" "$UNIT_DIR/${name}.timer"
}

install_unit "corticore-swarm"
install_unit "corticore-swarm-report"

ENV_FILE="$ENV_DIR/env"
REPO_ENV="$REPO_ROOT/.env"

seed_key_from_repo_env() {
  # Pull CURSOR_API_KEY from the repo .env without printing the secret.
  if [ ! -f "$REPO_ENV" ]; then
    return 1
  fi
  KEY_LINE="$(grep -E '^[[:space:]]*CURSOR_API_KEY=' "$REPO_ENV" | tail -n1 || true)"
  if [ -z "$KEY_LINE" ]; then
    return 1
  fi
  KEY_VALUE="${KEY_LINE#CURSOR_API_KEY=}"
  KEY_VALUE="${KEY_VALUE%\"}"
  KEY_VALUE="${KEY_VALUE#\"}"
  KEY_VALUE="${KEY_VALUE%\'}"
  KEY_VALUE="${KEY_VALUE#\'}"
  if [ -z "$KEY_VALUE" ]; then
    return 1
  fi
  printf 'CURSOR_API_KEY=%s\nSWARM_ENABLED=true\n' "$KEY_VALUE" > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  return 0
}

ensure_env_key() {
  local key="$1"
  local comment="$2"
  if [ ! -f "$ENV_FILE" ]; then
    return 0
  fi
  if grep -qE "^[[:space:]]*${key}=" "$ENV_FILE" 2>/dev/null; then
    return 0
  fi
  {
    echo ""
    echo "# ${comment}"
    echo "${key}="
  } >> "$ENV_FILE"
}

if [ ! -f "$ENV_FILE" ] || ! grep -qE '^CURSOR_API_KEY=.+' "$ENV_FILE" 2>/dev/null; then
  if seed_key_from_repo_env; then
    echo "Seeded $ENV_FILE from repo .env (CURSOR_API_KEY present)."
  else
    cat > "$ENV_FILE" <<'EOF'
# Required. Get a key from https://cursor.com/dashboard/integrations
CURSOR_API_KEY=

# Must be true for the executor to commit. Set false to think only.
SWARM_ENABLED=true
EOF
    chmod 600 "$ENV_FILE"
    echo "Created $ENV_FILE — set CURSOR_API_KEY before the next 04:00 run."
  fi
else
  echo "Keeping existing $ENV_FILE"
fi

ensure_env_key "TELEGRAM_BOT_TOKEN" "From @BotFather (/newbot). Required for 09:30 digest."
ensure_env_key "TELEGRAM_CHAT_ID" "Your chat id. Message the bot once, then: python orchestrate/report_daily.py --print-chat-id"

systemctl --user daemon-reload
echo "Installed units to $UNIT_DIR"

# Linger: user systemd stays up after logout / without an active session.
if command -v loginctl >/dev/null 2>&1; then
  if loginctl enable-linger "$USER" 2>/dev/null; then
    echo "Enabled systemd user linger for $USER (unattended timers)."
  else
    echo "NOTE: could not enable linger automatically. Run once (may need sudo):"
    echo "  sudo loginctl enable-linger $USER"
  fi
fi

if [ "$ENABLE" = true ]; then
  if ! grep -qE '^CURSOR_API_KEY=.+' "$ENV_FILE" 2>/dev/null; then
    echo "WARNING: CURSOR_API_KEY is empty in $ENV_FILE — swarm timer runs will fail until set."
  fi
  if ! grep -qE '^TELEGRAM_BOT_TOKEN=.+' "$ENV_FILE" 2>/dev/null \
     || ! grep -qE '^TELEGRAM_CHAT_ID=.+' "$ENV_FILE" 2>/dev/null; then
    echo "WARNING: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID incomplete — 09:30 report will fail until set."
    echo "  See deploy/systemd/README.md (BotFather steps)."
  fi
  systemctl --user enable --now corticore-swarm.timer
  systemctl --user enable --now corticore-swarm-report.timer
  echo
  echo "Timers enabled. You do not need to start the swarm or report daily."
  systemctl --user list-timers 'corticore-swarm*' --no-pager || true
  echo
  echo "Useful commands:"
  echo "  systemctl --user status corticore-swarm.timer"
  echo "  systemctl --user status corticore-swarm-report.timer"
  echo "  journalctl --user -u corticore-swarm.service -f"
  echo "  journalctl --user -u corticore-swarm-report.service -f"
  echo "  systemctl --user start corticore-swarm-report.service   # send report now"
else
  echo
  echo "Units installed but not enabled (--no-enable)."
  echo "  systemctl --user enable --now corticore-swarm.timer"
  echo "  systemctl --user enable --now corticore-swarm-report.timer"
fi
