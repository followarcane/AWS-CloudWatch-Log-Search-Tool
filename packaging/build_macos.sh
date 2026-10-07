#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 -m pip install -r requirements.txt
python3 -m PyInstaller packaging/logsearcher.spec --noconfirm --distpath packaging/dist --workpath packaging/build

echo "Built: $ROOT/packaging/dist/AWS Log Searcher.app"
echo "Ensure awslogs is on PATH for end users (pip install awslogs) and AWS profiles are configured."
