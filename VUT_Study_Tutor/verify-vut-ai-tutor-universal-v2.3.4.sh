#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$HERE/install-vut-ai-tutor-universal-v2.3.4.sh" --action verify "$@"
