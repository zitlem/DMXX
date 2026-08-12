#!/usr/bin/env bash
#
# update.sh - pull, build and restart a DMXX deployment.
#
# Safe to re-run. Backs up the database first, rolls back to the previous
# commit if the service does not come back healthy.
#
#   ./update.sh                 pull, build if needed, restart, verify
#   ./update.sh --force-build   rebuild the frontend even if nothing changed
#   ./update.sh --no-build      skip the frontend build entirely
#   ./update.sh --no-restart    update files only, leave the service running
#   ./update.sh --check         report what an update would do, change nothing
#
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE="dmxx.service"
BACKUP_DIR="/root"
KEEP_BACKUPS=5
HEALTH_PATH="/api/blackout/status"
HEALTH_RETRIES=15

FORCE_BUILD=0
DO_BUILD=1
DO_RESTART=1
CHECK_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --force-build) FORCE_BUILD=1 ;;
    --no-build)    DO_BUILD=0 ;;
    --no-restart)  DO_RESTART=0 ;;
    --check)       CHECK_ONLY=1 ;;
    -h|--help)     sed -n '3,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ok\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m  !!\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m  xx\033[0m %s\n' "$*" >&2; exit 1; }

cd "$APP_DIR"

# ---------------------------------------------------------------- preflight --
[ -d .git ] || die "$APP_DIR is not a git checkout - nothing to pull"

if [ "$DO_RESTART" = 1 ] && [ "$(id -u)" != 0 ]; then
  die "restarting $SERVICE needs root - re-run with sudo, or pass --no-restart"
fi

# The port systemd actually serves on, which need not match config.json
PORT="$(systemctl cat "$SERVICE" 2>/dev/null \
        | grep -oE '\-\-port[= ][0-9]+' | grep -oE '[0-9]+' | head -1)"
PORT="${PORT:-80}"
HEALTH_URL="http://127.0.0.1:${PORT}${HEALTH_PATH}"

say "Fetching origin"
git fetch --quiet origin || die "git fetch failed - is the network up?"

BEFORE="$(git rev-parse HEAD)"
TARGET="$(git rev-parse '@{u}')"

if [ "$BEFORE" = "$TARGET" ] && [ "$FORCE_BUILD" = 0 ]; then
  ok "already up to date at ${BEFORE:0:7}"
  [ "$CHECK_ONLY" = 1 ] && exit 0
  exit 0
fi

CHANGED="$(git diff --name-only "$BEFORE" "$TARGET")"
NEED_DEPS=0;  grep -q '^backend/requirements.txt$'      <<<"$CHANGED" && NEED_DEPS=1
NEED_BUILD=0; grep -qE '^frontend/(src|package.*|vite)' <<<"$CHANGED" && NEED_BUILD=1
[ "$FORCE_BUILD" = 1 ] && NEED_BUILD=1

if [ "$CHECK_ONLY" = 1 ]; then
  say "Would update ${BEFORE:0:7} -> ${TARGET:0:7}"
  git --no-pager log --oneline "$BEFORE..$TARGET" | sed 's/^/    /'
  echo "    files changed: $(wc -l <<<"$CHANGED")"
  echo "    reinstall deps: $([ "$NEED_DEPS" = 1 ] && echo yes || echo no)"
  echo "    rebuild frontend: $([ "$NEED_BUILD" = 1 ] && echo yes || echo no)"
  exit 0
fi

# Refuse to clobber local edits - they are almost certainly someone's work
if ! git diff --quiet || ! git diff --cached --quiet; then
  git --no-pager diff --stat | sed 's/^/    /'
  die "uncommitted changes in $APP_DIR - commit or stash them first"
fi

# ------------------------------------------------------------------- backup --
say "Backing up"
STAMP="$(date +%Y%m%d-%H%M%S)"
if [ -f data/database.db ]; then
  cp -a data/database.db "$BACKUP_DIR/dmxx-db-$STAMP.db"
  ok "database -> $BACKUP_DIR/dmxx-db-$STAMP.db"
fi
echo "$BEFORE" > "$BACKUP_DIR/dmxx-last-commit"
ls -1t "$BACKUP_DIR"/dmxx-db-*.db 2>/dev/null | tail -n +$((KEEP_BACKUPS + 1)) | xargs -r rm -f

# --------------------------------------------------------------------- pull --
say "Updating ${BEFORE:0:7} -> ${TARGET:0:7}"
git merge --ff-only "$TARGET" --quiet \
  || die "cannot fast-forward - the deployment has diverged from origin"
git --no-pager log --oneline "$BEFORE..$TARGET" | sed 's/^/    /'

# ------------------------------------------------------------------ install --
if [ "$NEED_DEPS" = 1 ]; then
  say "Installing Python dependencies"
  pip3 install --quiet --break-system-packages -r backend/requirements.txt \
    || pip3 install --quiet -r backend/requirements.txt \
    || die "dependency install failed"
  ok "dependencies up to date"
fi

# -------------------------------------------------------------------- build --
if [ "$DO_BUILD" = 1 ] && [ "$NEED_BUILD" = 1 ]; then
  if command -v npm >/dev/null; then
    say "Building frontend"
    ( cd frontend
      if [ -f package-lock.json ]; then npm ci --silent; else npm install --silent; fi
      npm run build --silent ) || die "frontend build failed - service left running on the old bundle"
    ok "bundle rebuilt"
  else
    warn "npm not installed - using the committed frontend/dist"
  fi
elif [ "$NEED_BUILD" = 1 ]; then
  warn "frontend changed but --no-build was given - dist may be stale"
fi

# ------------------------------------------------------------------ restart --
if [ "$DO_RESTART" = 0 ]; then
  ok "files updated; $SERVICE not restarted (--no-restart)"
  exit 0
fi

say "Restarting $SERVICE"
systemctl restart "$SERVICE"

for i in $(seq 1 "$HEALTH_RETRIES"); do
  sleep 1
  if curl -fsS -m 3 -o /dev/null "$HEALTH_URL" 2>/dev/null; then
    ok "healthy on port $PORT after ${i}s"
    say "Now at $(git --no-pager log --oneline -1)"
    exit 0
  fi
done

# ----------------------------------------------------------------- rollback --
warn "did not become healthy within ${HEALTH_RETRIES}s - rolling back"
git reset --hard --quiet "$BEFORE"
if [ "$NEED_BUILD" = 1 ] && command -v npm >/dev/null; then
  ( cd frontend && npm run build --silent ) || warn "rebuild of the old bundle failed"
fi
systemctl restart "$SERVICE"
sleep 3

if curl -fsS -m 3 -o /dev/null "$HEALTH_URL" 2>/dev/null; then
  die "update failed and was rolled back to ${BEFORE:0:7} - service is healthy again"
fi
die "update failed AND rollback did not restore health - check: journalctl -u $SERVICE -n 50"
