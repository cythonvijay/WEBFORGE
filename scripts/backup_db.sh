#!/usr/bin/env bash
# Safe WebForge database backup wrapper. Never logs credentials.
set -euo pipefail

OUTPUT_FILE="${1:-backups/webforge_$(date -u +%Y%m%dT%H%M%SZ).wfbackup.json}"
mkdir -p "$(dirname "$OUTPUT_FILE")"

cd "$(dirname "$0")/../backend"
python3 -m scripts.db_ops backup --output "../$OUTPUT_FILE"
