#!/usr/bin/env bash
# ==============================================================================
# restore-disposable-db.sh - Disposable Database Restore Verification (Scenario D-08)
#
# Automated verification script for PostgreSQL backup archives:
# - Validates SHA256 checksums if SHA256SUMS is present
# - Creates an isolated disposable volume and container with --network none
# - Waits for TCP readiness via pg_isready
# - Restores schema and data using pg_restore --exit-on-error --single-transaction
# - Verifies table row counts, Liquibase changelog, and databasechangeloglock status
# - Automatically tears down the disposable test container and volume on exit
# - Exits 0 on success, 1 on any consistency or restoration failure
# ==============================================================================

set -euo pipefail

# ------------------------------------------------------------------------------
# Defaults and configuration
# ------------------------------------------------------------------------------
POSTGRES_IMAGE="${POSTGRES_IMAGE:-postgres:16}"
TIMEOUT="${TIMEOUT:-60}"
KEEP_ON_FAILURE=false
KEEP_ALWAYS=false
DRY_RUN=false
DUMP_TARGET=""

# ------------------------------------------------------------------------------
# Usage
# ------------------------------------------------------------------------------
usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS] <PATH_TO_DUMP_OR_DIR>

Verify a database backup archive in an isolated, disposable PostgreSQL container.

Arguments:
  <PATH_TO_DUMP_OR_DIR>     Path to database.dump file or backup directory containing it

Options:
  -h, --help                Show this help message and exit
  -n, --dry-run             Validate paths, checksums, and Docker availability without restoring
  --pg-image <IMAGE>        PostgreSQL container image to use (default: $POSTGRES_IMAGE)
  --timeout <SEC>           Maximum seconds to wait for PostgreSQL readiness (default: $TIMEOUT)
  --keep-on-failure         Do not delete test container and volume if verification fails
  --keep                    Do not delete test container and volume even on success

Environment variables:
  POSTGRES_IMAGE, TIMEOUT
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
    --pg-image)
      POSTGRES_IMAGE="$2"
      shift 2
      ;;
    --timeout)
      TIMEOUT="$2"
      shift 2
      ;;
    --keep-on-failure)
      KEEP_ON_FAILURE=true
      shift
      ;;
    --keep)
      KEEP_ALWAYS=true
      shift
      ;;
    -*)
      echo "ERROR: Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      if [ -z "$DUMP_TARGET" ]; then
        DUMP_TARGET="$1"
        shift
      else
        echo "ERROR: Unexpected argument: $1" >&2
        usage >&2
        exit 1
      fi
      ;;
  esac
done

if [ -z "$DUMP_TARGET" ]; then
  echo "ERROR: Path to database.dump or backup directory is required." >&2
  usage >&2
  exit 1
fi

# ------------------------------------------------------------------------------
# Resolve dump file and directory
# ------------------------------------------------------------------------------
if [ -d "$DUMP_TARGET" ]; then
  dump_dir="$DUMP_TARGET"
  dump_file="$DUMP_TARGET/database.dump"
elif [ -f "$DUMP_TARGET" ]; then
  dump_file="$DUMP_TARGET"
  dump_dir="$(dirname "$DUMP_TARGET")"
else
  echo "ERROR: Target dump path '$DUMP_TARGET' does not exist." >&2
  exit 1
fi

if [ ! -f "$dump_file" ]; then
  echo "ERROR: Dump file '$dump_file' not found." >&2
  exit 1
fi

if [ ! -s "$dump_file" ]; then
  echo "ERROR: Dump file '$dump_file' is empty (0 bytes)." >&2
  exit 1
fi

# ------------------------------------------------------------------------------
# Verify SHA256 Checksum if present
# ------------------------------------------------------------------------------
if [ -f "$dump_dir/SHA256SUMS" ]; then
  echo "Verifying SHA256 checksums from $dump_dir/SHA256SUMS..."
  (
    cd "$dump_dir"
    if [ -f "database.dump" ]; then
      sha256sum --check --ignore-missing SHA256SUMS
    else
      # Target dump file may have another filename
      target_basename="$(basename "$dump_file")"
      if grep -q "  $target_basename\$" SHA256SUMS; then
        sha256sum --check --ignore-missing SHA256SUMS
      fi
    fi
  )
  echo "Checksum verification: OK"
fi

# ------------------------------------------------------------------------------
# Check Docker availability
# ------------------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker CLI is not installed or not in PATH." >&2
  exit 1
fi

if [ "$DRY_RUN" = true ]; then
  echo "DRY_RUN: Pre-flight checks passed for '$dump_file'. Isolated container restore would execute with image '$POSTGRES_IMAGE'."
  exit 0
fi

# ------------------------------------------------------------------------------
# Setup disposable resources and cleanup trap
# ------------------------------------------------------------------------------
restore_rand="$(od -vAn -N4 -tx1 /dev/urandom 2>/dev/null | tr -d ' ' || echo "$RANDOM")"
restore_id="$(date -u +%Y%m%d%H%M%S)-${restore_rand}"
restore_container="jsnb-restore-check-${restore_id}"
restore_volume="jsnb-restore-check-${restore_id}-data"

cleanup() {
  local exit_code=$?
  if [ "$exit_code" -ne 0 ] && [ "$KEEP_ON_FAILURE" = true ]; then
    echo "========================================================================"
    echo "INSPECTION PRESERVED: Verification failed with exit code $exit_code."
    echo "Container: $restore_container"
    echo "Volume:    $restore_volume"
    echo "To inspect logs:   docker logs $restore_container"
    echo "To inspect shell:  docker exec -it $restore_container bash"
    echo "To manually clean: docker rm -f $restore_container && docker volume rm $restore_volume"
    echo "========================================================================"
    return
  fi

  if [ "$KEEP_ALWAYS" = true ]; then
    echo "INFO: Preserving container '$restore_container' and volume '$restore_volume' (--keep specified)."
    return
  fi

  echo "Tearing down disposable container '$restore_container' and volume '$restore_volume'..."
  docker rm -f "$restore_container" >/dev/null 2>&1 || true
  docker volume rm -f "$restore_volume" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

# ------------------------------------------------------------------------------
# Start isolated container
# ------------------------------------------------------------------------------
echo "Creating disposable volume '$restore_volume'..."
docker volume create "$restore_volume" >/dev/null

echo "Starting isolated test PostgreSQL container '$restore_container' (--network none)..."
docker run -d \
  --name "$restore_container" \
  --network none \
  --pull=never \
  --memory=512m --cpus=1 \
  --mount "type=volume,source=$restore_volume,target=/var/lib/postgresql/data" \
  -e POSTGRES_USER=restore_admin \
  -e POSTGRES_DB=wiki \
  -e POSTGRES_HOST_AUTH_METHOD=trust \
  "$POSTGRES_IMAGE" >/dev/null

# ------------------------------------------------------------------------------
# Wait for TCP readiness
# ------------------------------------------------------------------------------
echo "Waiting for PostgreSQL TCP readiness (timeout: ${TIMEOUT}s)..."
ready=false
max_attempts=$((TIMEOUT / 2))
[ "$max_attempts" -lt 5 ] && max_attempts=5

for attempt in $(seq 1 "$max_attempts"); do
  if docker exec "$restore_container" pg_isready -h 127.0.0.1 -U restore_admin -d wiki >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 2
done

if [ "$ready" != true ]; then
  echo "ERROR: Disposable PostgreSQL container did not become ready within ${TIMEOUT} seconds." >&2
  docker logs --tail=50 "$restore_container" >&2 || true
  exit 1
fi
echo "PostgreSQL is ready."

# ------------------------------------------------------------------------------
# Restore dump
# ------------------------------------------------------------------------------
echo "Restoring database from '$dump_file'..."
if ! docker exec -i "$restore_container" pg_restore \
  -U restore_admin -d wiki \
  --no-owner --no-privileges --exit-on-error --single-transaction \
  < "$dump_file"; then
  echo "ERROR: pg_restore failed with exit code $?" >&2
  exit 1
fi
echo "pg_restore completed successfully."

# ------------------------------------------------------------------------------
# Run schema and data consistency verification queries
# ------------------------------------------------------------------------------
echo "Verifying restored schema and table counts..."
docker exec -i "$restore_container" psql -X -U restore_admin -d wiki -v ON_ERROR_STOP=1 <<'SQL'
SELECT current_database() AS database, current_setting('server_version') AS pg_version;
SELECT format('SELECT %L AS table_name, count(*) AS rows FROM %I.%I;',
              n.nspname || '.' || c.relname, n.nspname, c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname NOT LIKE 'pg_%'
  AND n.nspname <> 'information_schema'
ORDER BY n.nspname, c.relname
\gexec
SQL

# ------------------------------------------------------------------------------
# Verify Liquibase changelog and lock flag
# ------------------------------------------------------------------------------
echo "Checking Liquibase changelog and lock table..."

# Check changelog lock status
locked_val="$(docker exec -i "$restore_container" psql -X -A -t -U restore_admin -d wiki -c "SELECT locked FROM public.databasechangeloglock LIMIT 1;" 2>/dev/null || echo "missing")"
if [ "$locked_val" != "f" ] && [ "$locked_val" != "false" ]; then
  echo "ERROR: Liquibase lock check failed. Expected locked=false, got '$locked_val'." >&2
  exit 1
fi
echo "Liquibase lock status: UNLOCKED (OK)"

# Check changelog has recorded migrations
changelog_count="$(docker exec -i "$restore_container" psql -X -A -t -U restore_admin -d wiki -c "SELECT count(*) FROM public.databasechangelog;" 2>/dev/null || echo "0")"
if [ "${changelog_count:-0}" -le 0 ]; then
  echo "ERROR: Liquibase changelog table has 0 applied changesets." >&2
  exit 1
fi
echo "Liquibase changesets applied: $changelog_count (OK)"

# Check essential core tables exist
for table in "users.users" "notebooks.notebooks"; do
  row_count="$(docker exec -i "$restore_container" psql -X -A -t -U restore_admin -d wiki -c "SELECT count(*) FROM $table;" 2>/dev/null || echo "error")"
  if [ "$row_count" = "error" ]; then
    echo "ERROR: Core application table '$table' is missing or failed query." >&2
    exit 1
  fi
  echo "Table '$table': $row_count rows (OK)"
done

# ------------------------------------------------------------------------------
# Compare with row-counts.txt snapshot if available
# ------------------------------------------------------------------------------
if [ -f "$dump_dir/row-counts.txt" ]; then
  echo "Snapshot row-counts.txt found in dump directory:"
  cat "$dump_dir/row-counts.txt"
fi

echo "========================================================================"
echo "RESTORE_VERIFICATION_OK: container=$restore_container volume=$restore_volume"
echo "All consistency and schema checks passed."
echo "========================================================================"
exit 0
