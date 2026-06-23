#!/bin/bash
# Create a full RAW Timesheet backup on the server (DB + code + env).
set -euo pipefail

TS=$(date +%Y%m%d_%H%M%S)
DEST="/root/manual-backups/raw-full-${TS}"
mkdir -p "$DEST"

sudo -u postgres pg_dump raw_timesheet | gzip -9 > "${DEST}/raw_timesheet_db.sql.gz"
gzip -t "${DEST}/raw_timesheet_db.sql.gz"

tar --exclude=raw-timesheet-backend/venv \
    --exclude=raw-timesheet-backend/__pycache__ \
    -czf "${DEST}/raw-timesheet-backend.tar.gz" \
    -C /opt raw-timesheet-backend

gzip -9 -c /opt/raw-timesheet-backend/.env > "${DEST}/server.env.gz"

cat > "${DEST}/README.txt" << EOF
RAW Labour Hire full server backup
Created: $(date)
Host: $(hostname)

Contents:
- raw_timesheet_db.sql.gz   PostgreSQL dump (raw_timesheet)
- raw-timesheet-backend.tar.gz   /opt/raw-timesheet-backend (venv excluded)
- server.env.gz   server environment (secrets)
EOF

BUNDLE="/root/manual-backups/raw-full-${TS}-mac-download.tar.gz"
tar czf "$BUNDLE" -C /root/manual-backups "raw-full-${TS}"

echo "Backup folder: ${DEST}"
echo "Download bundle: ${BUNDLE}"
ls -lah "${DEST}" "$BUNDLE"
