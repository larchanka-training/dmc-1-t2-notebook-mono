# Database Backup, Retention, and Restore Verification

This document is the operational guide for automated PostgreSQL backups, retention policies, encrypted off-host replication, disposable restore verification, and disaster recovery for JS Notebook on the Aeza production VPS.

---

## 1. Overview and Architecture

- **Host:** Aeza VPS (`fortunate-pink`, IP `89.169.35.207`, user `deploy`).
- **Compose project:** `jsnotes-production` (`/home/deploy/jsnb-production`).
- **Database service:** `postgres` (`postgres:16`, database `wiki`, user `wiki`).
- **Backup tooling:**
  - Automated backup script: [`scripts/backup-aeza.sh`](../scripts/backup-aeza.sh)
  - Disposable restore verification script: [`scripts/restore-disposable-db.sh`](../scripts/restore-disposable-db.sh)
  - Unit & functional tests: [`scripts/tests/test_backup_scripts.py`](../scripts/tests/test_backup_scripts.py)

### Backup Directory Layout

All backup directories and archives are restricted to the `deploy` user (mode `0700` directories, mode `0600` files):

```text
/home/deploy/
├── jsnb-backups/                               # Mode 0700 (scheduled periodic backups)
│   ├── backup.log                              # Mode 0600 (structured audit log)
│   ├── daily/                                  # Mode 0700 (daily retention tier)
│   │   └── daily-20260916T030000Z-XXXXXX/      # Mode 0700 (local working backup)
│   │       ├── database.dump                   # Mode 0600 (local plaintext dump for fast rollback)
│   │       ├── restore-list.txt                # Mode 0600 (TOC generated via pg_restore --list)
│   │       ├── row-counts.txt                  # Mode 0600 (table counts at dump time)
│   │       ├── backup-meta.txt                 # Mode 0600 (metadata: host, timestamp, size)
│   │       ├── SHA256SUMS                      # Mode 0600 (local integrity checksums)
│   │       └── export/                         # Mode 0700 (DEDICATED OFF-HOST EXPORT BUNDLE)
│   │           ├── database.dump.age (or .gpg) # Mode 0600 (ENCRYPTED ciphertext archive)
│   │           ├── restore-list.txt            # Mode 0600
│   │           ├── row-counts.txt              # Mode 0600
│   │           ├── backup-meta.txt             # Mode 0600
│   │           └── SHA256SUMS                  # Mode 0600 (checksums for export bundle ONLY)
│   └── weekly/                                 # Mode 0700 (weekly retention tier)
│       └── weekly-20260916T030000Z/            # Mode 0700
└── jsnb-deploy-backups/aeza-production/        # Mode 0700 (pre-deploy rollback dumps from CI)
```

> [!IMPORTANT]
> **Plaintext Exclusion Principle:** The off-host export bundle (`export/`) strictly excludes `database.dump`. Only ciphertext (`.age` or `.gpg`) and non-sensitive integrity metadata are ever transferred off the Aeza host.

### Security & Access Control

1. **Strict permissions:** Root backup directory is mode `0700` (`drwx------`). Individual dump and metadata files are mode `0600` (`-rw-------`). If `.env.prod` has loose permissions (e.g. `0644`), `backup-aeza.sh` fails closed with exit code 1.
2. **Confidentiality:** Dumps contain live user identities, sessions, and notebooks. Dump archives must never be committed to Git or exposed via web servers.
3. **Pre-flight disk safety guard:** The backup script checks available space on the target filesystem (`df -Pk`) and refuses to start if less than 1 GiB free disk space is available.
4. **Fail-closed encryption:** If encryption is requested but neither `age` nor `gpg` is available, or if encryption fails, the backup script halts immediately with an error and records `BACKUP_FAILED` in `backup.log`.

---

## 2. Retention and Rotation Policy

| Tier | Schedule | Age-Based Retention | Storage Location |
|---|---|---|---|
| **Daily** | Every night at 03:00 UTC | 14 days (`-mtime +14`) | `/home/deploy/jsnb-backups/daily/` |
| **Weekly** | Every Sunday at 03:00 UTC | 28 days (`-mtime +28`) | `/home/deploy/jsnb-backups/weekly/` |
| **Pre-deploy** | Before every CD deployment | 14 days (`-mtime +14`) | `/home/deploy/jsnb-deploy-backups/aeza-production/` |

- **Age-based rotation:** Pruning is based on directory modification age (`find ... -mtime +14` for daily, `-mtime +28` for weekly), ensuring older snapshots are cleaned up automatically regardless of execution frequency.
- **Audit logging:** Each run appends a structured record (`BACKUP_OK` or `BACKUP_FAILED`) with directory path, timestamp, and size in bytes to `/home/deploy/jsnb-backups/backup.log` (mode `0600`).

---

## 3. Production Cron Setup on Aeza

### Step 1: Pre-provision Directory Structure

Before installing the crontab, ensure the base directory exists with strict permissions so log redirection cannot fail:

```bash
install -d -m 700 /home/deploy/jsnb-backups
touch /home/deploy/jsnb-backups/cron.log
chmod 600 /home/deploy/jsnb-backups/cron.log
```

### Step 2: Configure Crontab

Under the `deploy` user on Aeza (`fortunate-pink`):

```bash
crontab -e
```

Add the following crontab entry (executing at 03:00 UTC daily):

```cron
CRON_TZ=UTC
# Daily PostgreSQL backup at 03:00 UTC with automated rotation and integrity check
0 3 * * * /home/deploy/jsnb-production/scripts/backup-aeza.sh >> /home/deploy/jsnb-backups/cron.log 2>&1
```

### Manual Backup Execution

To take an immediate backup on Aeza:

```bash
# Standard daily backup
/home/deploy/jsnb-production/scripts/backup-aeza.sh

# Force weekly retention snapshot
/home/deploy/jsnb-production/scripts/backup-aeza.sh --weekly

# Backup with age encryption for off-host export
/home/deploy/jsnb-production/scripts/backup-aeza.sh --encrypt-recipient "age1..."

# Dry-run check (verifies host, env file, permissions, encryption tools, and disk space)
/home/deploy/jsnb-production/scripts/backup-aeza.sh --dry-run
```

---

## 4. Off-Host Backup Replication Runbook

> [!IMPORTANT]
> Hosting provider snapshots alone do not constitute a reliable disaster recovery plan. Backups must be copied off the Aeza VPS to an independent storage location (operator workstation, S3-compatible off-host bucket, or dedicated backup server).

### Pulling Encrypted Export Bundle to Operator Workstation (Mac)

Run from an authenticated operator machine. Notice that we transfer **only** the `export/` subdirectory, ensuring plaintext data never leaves Aeza:

```bash
(
  set -euo pipefail
  umask 077
  local_root="$HOME/DevelopmentWorkspaces/backup/aeza-production"
  mkdir -p -m 700 "$local_root"

  # Find latest remote daily backup directory
  latest_daily="$(ssh -o IdentitiesOnly=yes -i ~/.ssh/aeza-jsnotebook-prod deploy@89.169.35.207 \
    'ls -td /home/deploy/jsnb-backups/daily/daily-* | head -n 1')"

  backup_name="$(basename "$latest_daily")"
  echo "Pulling encrypted off-host export: $backup_name"

  # Pull ONLY the export directory containing ciphertext and metadata
  scp -o IdentitiesOnly=yes -i ~/.ssh/aeza-jsnotebook-prod -r \
    "deploy@89.169.35.207:$latest_daily/export" \
    "$local_root/$backup_name-export"

  cd "$local_root/$backup_name-export"

  # Verify cryptographic checksums of the export bundle
  shasum -a 256 --check SHA256SUMS

  # Assert plaintext exclusion: database.dump must NOT be present
  if [ -f "database.dump" ]; then
    echo "ERROR: Security violation! Plaintext database.dump was transferred." >&2
    exit 1
  fi

  echo "OFFHOST_ENCRYPTED_BACKUP_VERIFIED_OK: $PWD"
)
```

### Decrypting and Restoring Off-Host Archives

To verify or restore an off-host encrypted archive on an operator machine:

```bash
(
  set -euo pipefail
  target_dir="$HOME/DevelopmentWorkspaces/backup/aeza-production/<BACKUP_NAME>-export"
  cd "$target_dir"

  # 1. Decrypt ciphertext archive
  if [ -f "database.dump.age" ]; then
    age -d -i ~/.ssh/backup-age-key database.dump.age > database.dump
  elif [ -f "database.dump.gpg" ]; then
    gpg --decrypt database.dump.gpg > database.dump
  else
    echo "ERROR: No supported encrypted dump found" >&2
    exit 1
  fi
  chmod 600 database.dump

  # 2. Verify TOC matches recorded metadata
  docker run --rm -i postgres:16 pg_restore --list < database.dump > verify-list.txt
  diff -u restore-list.txt verify-list.txt

  # 3. Execute disposable restore verification
  /path/to/project/scripts/restore-disposable-db.sh "$PWD"
)
```

---

## 5. Disposable Database Restore Verification (Scenario D-08)

The restore verification script [`scripts/restore-disposable-db.sh`](../scripts/restore-disposable-db.sh) proves the viability of a backup archive without touching the live database, exposing ports, or risking production data.

### Verification Principles

1. **Isolation:** Runs a dedicated disposable container with `--network none`, non-root resource limits (`--memory=512m --cpus=1`), and a temporary disposable Docker volume (`jsnb-restore-check-*`).
2. **Checksum validation:** Automatically checks `SHA256SUMS` before running the restore.
3. **Atomic restore:** Executes `pg_restore --exit-on-error --single-transaction --no-owner --no-privileges`.
4. **Deterministic row count equivalence:**
   - Queries restored database tables in user schemas (`public`, `users`, `notebooks`).
   - Compares restored table row counts directly against `row-counts.txt` snapshot via `diff -u`. Any mismatch causes immediate failure.
5. **Core non-emptiness checks:**
   - Verifies `users.users` contains $> 0$ rows.
   - Verifies `public.databasechangelog` contains $> 0$ applied changesets.
   - Verifies `public.databasechangeloglock` contains exactly 1 row and `locked = false`.
6. **Automatic teardown:** The disposable container and volume are automatically destroyed on script completion via a shell `EXIT` trap.

### Running Restore Verification

On the Aeza VPS:

```bash
# Verify the latest daily backup (plaintext local working copy)
latest_daily="$(ls -td /home/deploy/jsnb-backups/daily/daily-* | head -n 1)"
/home/deploy/jsnb-production/scripts/restore-disposable-db.sh "$latest_daily"

# Dry run (checks checksums, row-counts.txt presence, and dump non-emptiness only)
/home/deploy/jsnb-production/scripts/restore-disposable-db.sh --dry-run "$latest_daily"

# Debugging mode: preserve container & volume if restore fails
/home/deploy/jsnb-production/scripts/restore-disposable-db.sh --keep-on-failure "$latest_daily"
```

Expected output:

```text
Verifying SHA256 checksums from .../SHA256SUMS...
database.dump: OK
Checksum verification: OK
Creating disposable volume 'jsnb-restore-check-20260916...-data'...
Starting isolated test PostgreSQL container 'jsnb-restore-check-20260916...' (--network none)...
Waiting for PostgreSQL TCP readiness (timeout: 60s)...
PostgreSQL is ready.
Restoring database from '.../database.dump'...
pg_restore completed successfully.
Querying restored table counts across schemas...
Restored table counts:
notebooks.notebook_ai_context	0
notebooks.notebooks	8
public.databasechangelog	8
public.databasechangeloglock	1
users.otps	30
users.refresh_tokens	65
users.sessions	19
users.users	5
Comparing restored table counts against expected snapshot '.../row-counts.txt'...
Row count equivalence: OK (exact match across all tracked tables)
Asserting non-emptiness and integrity of core tables...
Table 'users.users': 5 rows (>0 OK)
Table 'public.databasechangelog': 8 changesets (>0 OK)
Liquibase lock status: UNLOCKED (locked=f OK)
========================================================================
RESTORE_VERIFICATION_OK: container=jsnb-restore-check-... volume=...
All consistency, schema, and row-count equivalence checks passed.
========================================================================
Tearing down disposable container 'jsnb-restore-check-...' and volume '...'
```

---

## 6. Emergency Production Disaster Recovery Runbook

If the live production database suffers corruption, accidental deletion, or catastrophic hardware failure, follow this procedure to restore from a verified backup.

### Step 1: Halt Application Writes

Stop the API service to ensure no new HTTP requests or partial writes hit the database:

```bash
docker compose \
  -p jsnotes-production \
  --env-file /home/deploy/jsnb-production/.env.prod \
  -f /home/deploy/jsnb-production/docker-compose.prod.yaml \
  stop api
```

### Step 2: Snapshot Current State

If the current PostgreSQL database is still readable, capture an emergency snapshot before overwriting:

```bash
/home/deploy/jsnb-production/scripts/backup-aeza.sh
```

### Step 3: Validate Target Backup Archive

Run the disposable restore check against the target backup archive to confirm its integrity prior to applying it to production:

```bash
/home/deploy/jsnb-production/scripts/restore-disposable-db.sh /path/to/target/backup
```

### Step 4: Restore Target Dump into Production Database

```bash
(
  set -euo pipefail
  target_dump="/path/to/target/backup/database.dump"
  env_file="/home/deploy/jsnb-production/.env.prod"
  compose_file="/home/deploy/jsnb-production/docker-compose.prod.yaml"

  db_user="$(grep -E '^POSTGRES_USER=' "$env_file" | cut -d '=' -f 2-)"
  db_name="$(grep -E '^POSTGRES_DB=' "$env_file" | cut -d '=' -f 2-)"

  # Drop and recreate schema objects cleanly via pg_restore --clean
  docker compose \
    -p jsnotes-production \
    --env-file "$env_file" \
    -f "$compose_file" \
    exec -T postgres pg_restore \
      -U "$db_user" -d "$db_name" \
      --clean --if-exists --exit-on-error --single-transaction \
      < "$target_dump"

  echo "Production restore completed: OK"
)
```

### Step 5: Execute Liquibase Migrations (if schema catch-up is needed)

If restoring a dump created prior to recent Liquibase changesets, run migrations using the canonical project runner:

```bash
(
  set -euo pipefail
  env_file="/home/deploy/jsnb-production/.env.prod"

  db_name="$(grep -E '^POSTGRES_DB=' "$env_file" | cut -d '=' -f 2-)"
  db_user="$(grep -E '^POSTGRES_USER=' "$env_file" | cut -d '=' -f 2-)"
  db_password="$(grep -E '^POSTGRES_PASSWORD=' "$env_file" | cut -d '=' -f 2-)"
  image_tag="$(grep -E '^IMAGE_TAG=' "$env_file" | cut -d '=' -f 2-)"

  migration_env="$(mktemp)"
  chmod 600 "$migration_env"
  trap 'rm -f "$migration_env"' EXIT

  cat <<EOF > "$migration_env"
LIQUIBASE_COMMAND_URL=jdbc:postgresql://postgres:5432/${db_name}
LIQUIBASE_COMMAND_USERNAME=${db_user}
LIQUIBASE_COMMAND_PASSWORD=${db_password}
LIQUIBASE_COMMAND_CHANGELOG_FILE=changelog-master.xml
LIQUIBASE_COMMAND_CONTEXTS=production
EOF

  docker run --rm \
    --network jsnotes-production_default \
    --env-file "$migration_env" \
    "ghcr.io/larchanka-training/jsnotes-t2:migrations-${image_tag}"
)
```

### Step 6: Restart Stack & Execute Health Gates

```bash
# Restart production services
docker compose \
  -p jsnotes-production \
  --env-file /home/deploy/jsnb-production/.env.prod \
  -f /home/deploy/jsnb-production/docker-compose.prod.yaml \
  up -d

# Verify origin API health using validate_deploy_health.py via stdin
curl -kfsS --resolve "jsnb.org:443:127.0.0.1" "https://jsnb.org/api/v1/health" | \
  python3 /home/deploy/jsnb-production/.github/scripts/validate_deploy_health.py \
    --expected-environment production

# Verify origin UI root using validate_deploy_ui.py
headers_file="$(mktemp)"
body_file="$(mktemp)"
curl -kfsS --resolve "jsnb.org:443:127.0.0.1" -D "$headers_file" -o "$body_file" "https://jsnb.org/"
python3 /home/deploy/jsnb-production/.github/scripts/validate_deploy_ui.py \
  --headers-file "$headers_file" \
  --body-file "$body_file"
rm -f "$headers_file" "$body_file"

# Verify public Cloudflare endpoint
curl -fsS "https://jsnb.org/api/v1/health" | \
  python3 /home/deploy/jsnb-production/.github/scripts/validate_deploy_health.py \
    --expected-environment production
```
