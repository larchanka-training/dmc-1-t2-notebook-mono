# Database Backup, Retention, and Restore Verification

This document is the operational guide for automated PostgreSQL backups, retention policies, off-host replication, and disposable restore verification for JS Notebook on the Aeza production VPS.

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

All backup directories and archives are restricted to the `deploy` user:

```text
/home/deploy/
├── jsnb-backups/                      # Mode 0700 (scheduled periodic backups)
│   ├── backup.log                     # Mode 0600 (timestamped audit log)
│   ├── daily/                         # Mode 0700 (daily retention tier)
│   │   └── daily-20260916T030000Z-XXXXXX/  # Mode 0700
│   │       ├── database.dump          # Mode 0600 (custom compressed pg_dump)
│   │       ├── restore-list.txt       # Mode 0600 (TOC generated via pg_restore --list)
│   │       ├── row-counts.txt         # Mode 0600 (table counts at dump time)
│   │       ├── backup-meta.txt        # Mode 0600 (metadata: host, timestamp, size)
│   │       ├── database.dump.enc      # Mode 0600 (optional encrypted copy)
│   │       └── SHA256SUMS             # Mode 0600 (cryptographic checksums)
│   └── weekly/                        # Mode 0700 (weekly retention tier)
│       └── weekly-20260916T030000Z/   # Mode 0700
└── jsnb-deploy-backups/aeza-production/ # Mode 0700 (pre-deploy rollback dumps from CI)
```

### Security & Access Control

1. **Strict permissions:** Root backup directory is mode `0700` (`drwx------`). Individual dump and metadata files are mode `0600` (`-rw-------`).
2. **Confidentiality:** Dumps contain live user identities, sessions, and notebooks. Dump archives must never be committed to Git or exposed via web servers.
3. **Pre-flight disk safety guard:** The backup script checks available space on the target filesystem (`df -Pk`) and refuses to start if less than 1 GiB free disk space is available.

---

## 2. Retention and Rotation Policy

| Tier | Schedule | Retention Window | Storage Location |
|---|---|---|---|
| **Daily** | Every night at 03:00 UTC | 14 days | `/home/deploy/jsnb-backups/daily/` |
| **Weekly** | Every Sunday at 03:00 UTC | 4 weeks (28 days) | `/home/deploy/jsnb-backups/weekly/` |
| **Pre-deploy** | Before every CD deployment | 14 days | `/home/deploy/jsnb-deploy-backups/aeza-production/` |

- **Daily rotation:** Daily backup directories older than 14 days (`-mtime +14`) are automatically pruned at the end of each run.
- **Weekly rotation:** Weekly snapshots older than 28 days (`-mtime +28`) are automatically pruned.
- **Audit logging:** Each run appends a structured record (`BACKUP_OK` or `BACKUP_FAILED`) with directory path, timestamp, and size in bytes to `/home/deploy/jsnb-backups/backup.log`.

---

## 3. Production Cron Setup on Aeza

To configure automated execution on the Aeza VPS under user `deploy`:

```bash
crontab -e
```

Add the following crontab entry:

```cron
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

# Dry-run check (verifies host, env file, permissions, and disk space without dumping)
/home/deploy/jsnb-production/scripts/backup-aeza.sh --dry-run
```

---

## 4. Off-Host Backup Replication Runbook

> [!IMPORTANT]
> Hosting provider snapshots alone do not constitute a reliable disaster recovery plan. Backups must be copied off the Aeza VPS to an independent storage location (operator workstation, S3-compatible off-host bucket, or dedicated backup server).

### Pulling Backups to Operator Workstation (Mac)

Run from an authenticated operator machine:

```bash
(
  set -euo pipefail
  umask 077
  local_root="$HOME/DevelopmentWorkspaces/backup/aeza-production"
  mkdir -p -m 700 "$local_root"

  # Find latest remote daily backup directory
  latest_backup="$(ssh -o IdentitiesOnly=yes -i ~/.ssh/aeza-jsnotebook-prod deploy@89.169.35.207 \
    'ls -td /home/deploy/jsnb-backups/daily/daily-* | head -n 1')"

  backup_name="$(basename "$latest_backup")"
  echo "Pulling off-host backup: $backup_name"

  scp -o IdentitiesOnly=yes -i ~/.ssh/aeza-jsnotebook-prod -r \
    "deploy@89.169.35.207:$latest_backup" \
    "$local_root/"

  cd "$local_root/$backup_name"
  shasum -a 256 --check SHA256SUMS
  echo "OFFHOST_BACKUP_VERIFIED_OK: $PWD"
)
```

### Optional Public-Key Encryption

If off-host transit passes through untrusted storage, configure encryption using `age` or `gpg` with a public recipient key:

```bash
# Using age recipient key
/home/deploy/jsnb-production/scripts/backup-aeza.sh --encrypt-recipient "age1..."

# Or configure in environment
export BACKUP_ENCRYPT_RECIPIENT="age1..."
```

---

## 5. Disposable Database Restore Verification (Scenario D-08)

The restore verification script [`scripts/restore-disposable-db.sh`](../scripts/restore-disposable-db.sh) proves the viability of a backup archive without touching the live database, exposing ports, or risking production data.

### Verification Principles

1. **Isolation:** Runs a dedicated disposable container with `--network none`, non-root resource limits (`--memory=512m --cpus=1`), and a temporary disposable Docker volume (`jsnb-restore-check-*`).
2. **Checksum validation:** Automatically checks `SHA256SUMS` before running the restore.
3. **Atomic restore:** Executes `pg_restore --exit-on-error --single-transaction --no-owner --no-privileges`.
4. **Data & schema checks:**
   - Queries database version and table counts across user schemas.
   - Verifies `public.databasechangeloglock.locked = false`.
   - Verifies `public.databasechangelog` contains applied changesets.
   - Verifies core application tables exist (`users.users`, `notebooks.notebooks`).
5. **Automatic teardown:** The disposable container and volume are automatically destroyed on script completion via a shell `EXIT` trap.

### Running Restore Verification

On the Aeza VPS:

```bash
# Verify the latest daily backup
latest_daily="$(ls -td /home/deploy/jsnb-backups/daily/daily-* | head -n 1)"
/home/deploy/jsnb-production/scripts/restore-disposable-db.sh "$latest_daily"

# Dry run (checks checksums and dump non-emptiness only)
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
Verifying restored schema and table counts...
...
Liquibase lock status: UNLOCKED (OK)
Liquibase changesets applied: 8 (OK)
Table 'users.users': 5 rows (OK)
Table 'notebooks.notebooks': 8 rows (OK)
========================================================================
RESTORE_VERIFICATION_OK: container=jsnb-restore-check-... volume=...
All consistency and schema checks passed.
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

  # Source credentials
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

If restoring a dump created prior to recent Liquibase changesets:

```bash
docker run --rm \
  --network jsnotes-production_backend \
  --env-file /home/deploy/jsnb-production/.env.prod \
  -e LIQUIBASE_COMMAND_URL="jdbc:postgresql://postgres:5432/wiki" \
  -e LIQUIBASE_COMMAND_USERNAME="wiki" \
  -e LIQUIBASE_COMMAND_PASSWORD="$POSTGRES_PASSWORD" \
  ghcr.io/larchanka-training/dmc-1-t2-notebook-api:sha-... \
  sh -c 'liquibase --search-path=/app/db/changelog update'
```

### Step 6: Restart Stack & Execute Health Gates

```bash
docker compose \
  -p jsnotes-production \
  --env-file /home/deploy/jsnb-production/.env.prod \
  -f /home/deploy/jsnb-production/docker-compose.prod.yaml \
  up -d

# Verify origin health
python3 /home/deploy/jsnb-production/.github/scripts/validate_deploy_health.py \
  --url "https://127.0.0.1/api/v1/health" \
  --environment "production" \
  --insecure

# Verify public health
curl -fsS https://jsnb.org/api/v1/health
```
