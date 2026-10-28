#!/usr/bin/env bash
# Safe WebForge database restore wrapper into a disposable target database. Never logs credentials.
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 <backup_file.wfbackup.json> <disposable_target_database_url>" >&2
  exit 1
fi

BACKUP_FILE="$1"
TARGET_DB_URL="$2"

cd "$(dirname "$0")/../backend"
python3 -m scripts.db_ops restore --input "$BACKUP_FILE" --target-url "$TARGET_DB_URL"
