#!/bin/sh
set -e
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
sqlite3 /app/db/udlaeg.db ".backup /app/data/backups/udlaeg-${TIMESTAMP}.db"
echo "Backup written: udlaeg-${TIMESTAMP}.db"
