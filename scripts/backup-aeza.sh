#!/usr/bin/env bash
# ==============================================================================
# backup-aeza.sh - Automated PostgreSQL Backup with Retention & Integrity Verification
#
# Production backup script for Aeza VPS (host: fortunate-pink).
# - Validates execution environment and host identity
# - Enforces pre-flight disk-space safety guards (>= 1 GiB free)
# - Performs compressed custom-format pg_dump with lock-wait timeouts
# - Verifies archive integrity via pg_restore --list and SHA256 checksums
# - Captures row-count audit snapshots
# - Applies retention rotation policy (14 daily / 4 weekly)
# - Supports optional public-key encryption (age / gpg)
# - Appends structured audit logs to backup.log
# ==============================================================================

set -euo pipefail

# ------------------------------------------------------------------------------
# Defaults and configuration
# ------------------------------------------------------------------------------
DEFAULT_HOST="fortunate-pink"
BACKUP_ROOT="${BACKUP_ROOT:-/home/deploy/jsnb-backups}"
ENV_FILE="${ENV_FILE:-/home/deploy/jsnb-production/.env.prod}"
COMPOSE_FILE="${COMPOSE_FILE:-/home/deploy/jsnb-production/docker-compose.prod.yaml}"
PROJECT_NAME="${PROJECT_NAME:-jsnotes-production}"
MIN_FREE_KB="${MIN_FREE_KB:-1048576}" # 1 GiB in KB
POSTGRES_IMAGE="${POSTGRES_IMAGE:-postgres:16}"

SKIP_HOSTNAME_CHECK=false
DRY_RUN=false
FORCE_WEEKLY=false
ENCRYPT_RECIPIENT="${BACKUP_ENCRYPT_RECIPIENT:-}"

# ------------------------------------------------------------------------------
# Usage
# ------------------------------------------------------------------------------
usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Automated database backup with integrity verification and rotation on Aeza.

Options:
  -h, --help                  Show this help message and exit
  -n, --dry-run               Check prerequisites, disk space, and paths without executing dump
  --skip-hostname-check       Allow running on hosts other than '$DEFAULT_HOST'
  --backup-root <DIR>         Root backup directory (default: $BACKUP_ROOT)
  --env-file <FILE>           Path to production .env file (default: $ENV_FILE)
  --compose-file <FILE>       Path to Compose file (default: $COMPOSE_FILE)
  --project-name <NAME>       Compose project name (default: $PROJECT_NAME)
  --min-free-kb <KB>          Minimum free space in KB required (default: $MIN_FREE_KB)
  --weekly                    Force creating a weekly retention snapshot
  --encrypt-recipient <KEY>   Public key (age or GPG recipient) for optional encryption

Environment variables:
  BACKUP_ROOT, ENV_FILE, COMPOSE_FILE, PROJECT_NAME, MIN_FREE_KB,
  BACKUP_ENCRYPT_RECIPIENT, POSTGRES_IMAGE
EOF
}

# ------------------------------------------------------------------------------
# Parse CLI arguments
# ------------------------------------------------------------------------------
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    -n|--dry-run)
      DRY_RUN=true
      shift
      ;;
    --skip-hostname-check)
      SKIP_HOSTNAME_CHECK=true
      shift
      ;;
    --backup-root)
      BACKUP_ROOT="$2"
      shift 2
      ;;
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --compose-file)
      COMPOSE_FILE="$2"
      shift 2
      ;;
    --project-name)
      PROJECT_NAME="$2"
      shift 2
      ;;
    --min-free-kb)
      MIN_FREE_KB="$2"
      shift 2
      ;;
    --weekly)
      FORCE_WEEKLY=true
      shift
      ;;
    --encrypt-recipient)
      ENCRYPT_RECIPIENT="$2"
      shift 2
      ;;
    *)
      echo "ERROR: Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

# ------------------------------------------------------------------------------
# Logging helper
# ------------------------------------------------------------------------------
log() {
  local timestamp
  timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "[$timestamp] $*"
  if [ "$DRY_RUN" = false ] && [ -d "$BACKUP_ROOT" ]; then
    echo "[$timestamp] $*" >> "${BACKUP_ROOT}/backup.log" 2>/dev/null || true
  fi
}

log_err() {
  local timestamp
  timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "[$timestamp] ERROR: $*" >&2
  if [ "$DRY_RUN" = false ] && [ -d "$BACKUP_ROOT" ]; then
    echo "[$timestamp] ERROR: $*" >> "${BACKUP_ROOT}/backup.log" 2>/dev/null || true
  fi
}

# ------------------------------------------------------------------------------
# Pre-flight checks
# ------------------------------------------------------------------------------
log "Starting Aeza backup execution (dry_run=$DRY_RUN)"

# 1. Hostname verification
current_host="$(hostname -s 2>/dev/null || hostname)"
if [ "$SKIP_HOSTNAME_CHECK" = false ] && [ "$current_host" != "$DEFAULT_HOST" ]; then
  log_err "Host check failed: current host '$current_host' is not '$DEFAULT_HOST'. Use --skip-hostname-check to bypass."
  exit 1
fi

# 2. Files and configuration
if [ ! -f "$ENV_FILE" ]; then
  log_err "Environment file '$ENV_FILE' not found"
  exit 1
fi

# Check permissions on env file (should be 600 or 400)
env_perms="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || stat -f '%Lp' "$ENV_FILE" 2>/dev/null || echo "unknown")"
if [ "$env_perms" != "600" ] && [ "$env_perms" != "400" ]; then
  log "WARNING: Environment file '$ENV_FILE' permissions are $env_perms (expected 600 or 400)"
fi

if [ ! -f "$COMPOSE_FILE" ]; then
  log_err "Compose file '$COMPOSE_FILE' not found"
  exit 1
fi

# 3. Disk space verification
check_dir="$BACKUP_ROOT"
while [ ! -d "$check_dir" ] && [ "$check_dir" != "/" ] && [ "$check_dir" != "." ]; do
  check_dir="$(dirname "$check_dir")"
done

available_kb="$(df -Pk "$check_dir" 2>/dev/null | awk 'NR == 2 {print $4}')"
if [ "${available_kb:-0}" -lt "$MIN_FREE_KB" ]; then
  log_err "Insufficient disk space in '$check_dir': ${available_kb:-0} KB available, required at least ${MIN_FREE_KB} KB"
  exit 1
fi
log "Disk space pre-flight check passed: ${available_kb} KB available (min required: ${MIN_FREE_KB} KB)"

# ------------------------------------------------------------------------------
# Prepare backup directories
# ------------------------------------------------------------------------------
if [ "$DRY_RUN" = true ]; then
  log "DRY_RUN: Pre-flight checks passed successfully. Would execute pg_dump and rotation under $BACKUP_ROOT."
  exit 0
fi

install -d -m 700 "$BACKUP_ROOT"
install -d -m 700 "${BACKUP_ROOT}/daily"
install -d -m 700 "${BACKUP_ROOT}/weekly"

backup_timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="$(mktemp -d "${BACKUP_ROOT}/daily/daily-${backup_timestamp}-XXXXXX")"
chmod 700 "$backup_dir"

log "Created daily backup directory: $backup_dir"

# ------------------------------------------------------------------------------
# Execute database dump
# ------------------------------------------------------------------------------
log "Executing custom compressed pg_dump from container..."
if ! docker compose \
  -p "$PROJECT_NAME" \
  --env-file "$ENV_FILE" \
  -f "$COMPOSE_FILE" \
  exec -T postgres sh -ceu \
    'exec pg_dump --format=custom --compress=6 --lock-wait-timeout=10s -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  > "$backup_dir/database.dump"; then
  log_err "pg_dump command failed"
  rm -rf "$backup_dir"
  exit 1
fi

# ------------------------------------------------------------------------------
# Verify archive integrity
# ------------------------------------------------------------------------------
if [ ! -s "$backup_dir/database.dump" ]; then
  log_err "Database dump file '$backup_dir/database.dump' is empty"
  rm -rf "$backup_dir"
  exit 1
fi

log "Verifying archive table of contents (pg_restore --list)..."
if ! docker run --rm -i "$POSTGRES_IMAGE" pg_restore --list \
  < "$backup_dir/database.dump" \
  > "$backup_dir/restore-list.txt"; then
  log_err "TOC verification with pg_restore --list failed"
  rm -rf "$backup_dir"
  exit 1
fi

if [ ! -s "$backup_dir/restore-list.txt" ]; then
  log_err "TOC file '$backup_dir/restore-list.txt' is empty"
  rm -rf "$backup_dir"
  exit 1
fi

# ------------------------------------------------------------------------------
# Capture row counts snapshot
# ------------------------------------------------------------------------------
log "Capturing table row counts snapshot..."
docker compose \
  -p "$PROJECT_NAME" \
  --env-file "$ENV_FILE" \
  -f "$COMPOSE_FILE" \
  exec -T postgres sh -ceu \
    'psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<'\''SQL'\''
SELECT current_database(), current_setting('\''server_version'\'');
SELECT format('\''SELECT %L AS table_name, count(*) AS rows FROM %I.%I;'\'',
              n.nspname || '\''.'\'' || c.relname, n.nspname, c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = '\''r'\''
  AND n.nspname NOT LIKE '\''pg_%'\''
  AND n.nspname <> '\''information_schema'\''
ORDER BY n.nspname, c.relname
\gexec
SQL' > "$backup_dir/row-counts.txt" 2>/dev/null || true

# ------------------------------------------------------------------------------
# Record metadata
# ------------------------------------------------------------------------------
dump_size_bytes="$(stat -c '%s' "$backup_dir/database.dump" 2>/dev/null || stat -f '%z' "$backup_dir/database.dump" 2>/dev/null || echo 0)"
cat <<EOF > "$backup_dir/backup-meta.txt"
timestamp=$backup_timestamp
host=$current_host
project=$PROJECT_NAME
dump_size_bytes=$dump_size_bytes
postgres_image=$POSTGRES_IMAGE
EOF

# ------------------------------------------------------------------------------
# Optional encryption
# ------------------------------------------------------------------------------
if [ -n "$ENCRYPT_RECIPIENT" ]; then
  log "Encrypting backup archive for recipient: $ENCRYPT_RECIPIENT"
  if command -v age >/dev/null 2>&1; then
    age -r "$ENCRYPT_RECIPIENT" -o "$backup_dir/database.dump.enc" "$backup_dir/database.dump"
    log "Encrypted with age: database.dump.enc"
  elif command -v gpg >/dev/null 2>&1; then
    gpg --batch --yes --encrypt --recipient "$ENCRYPT_RECIPIENT" \
      --output "$backup_dir/database.dump.gpg" "$backup_dir/database.dump"
    log "Encrypted with gpg: database.dump.gpg"
  else
    log "WARNING: Neither age nor gpg found in PATH; skipping encryption"
  fi
fi

# ------------------------------------------------------------------------------
# Compute SHA256 checksums
# ------------------------------------------------------------------------------
log "Generating SHA256 checksums..."
(
  cd "$backup_dir"
  # Generate checksums for all files except SHA256SUMS itself
  find . -maxdepth 1 -type f ! -name 'SHA256SUMS' -exec sha256sum {} + | sort -k 2 > SHA256SUMS
  sha256sum --check SHA256SUMS >/dev/null
)

# Set strict file permissions
chmod 600 "$backup_dir"/*

log "Daily backup completed: OK (dir=$backup_dir, size=${dump_size_bytes} bytes)"

# ------------------------------------------------------------------------------
# Weekly snapshot replication (if Sunday or forced)
# ------------------------------------------------------------------------------
day_of_week="$(date -u +%u)" # 1 = Monday, 7 = Sunday
if [ "$FORCE_WEEKLY" = true ] || [ "$day_of_week" -eq 7 ]; then
  weekly_dir="${BACKUP_ROOT}/weekly/weekly-${backup_timestamp}"
  log "Creating weekly retention snapshot at $weekly_dir..."
  cp -a "$backup_dir" "$weekly_dir"
  chmod 700 "$weekly_dir"
  chmod 600 "$weekly_dir"/*
  log "Weekly snapshot created: OK ($weekly_dir)"
fi

# ------------------------------------------------------------------------------
# Retention rotation
# ------------------------------------------------------------------------------
log "Applying retention rotation..."

# Prune daily backups older than 14 days
pruned_daily="$(find "${BACKUP_ROOT}/daily" -mindepth 1 -maxdepth 1 -type d -name 'daily-*' -mtime +14 -print -exec rm -rf -- {} + 2>/dev/null || true)"
if [ -n "$pruned_daily" ]; then
  log "Pruned daily backups older than 14 days: $pruned_daily"
fi

# Prune weekly backups older than 28 days (4 weeks)
pruned_weekly="$(find "${BACKUP_ROOT}/weekly" -mindepth 1 -maxdepth 1 -type d -name 'weekly-*' -mtime +28 -print -exec rm -rf -- {} + 2>/dev/null || true)"
if [ -n "$pruned_weekly" ]; then
  log "Pruned weekly backups older than 28 days: $pruned_weekly"
fi

log "BACKUP_OK: backup_dir=$backup_dir size=$dump_size_bytes timestamp=$backup_timestamp"
echo "BACKUP_OK: $backup_dir"
exit 0
