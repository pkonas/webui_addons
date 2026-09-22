#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

for script in "$HERE/install-vut-ai-tutor-universal-v2.3.4.sh" "$HERE/verify-vut-ai-tutor-universal-v2.3.4.sh" "$0"; do
  bash -n "$script"
done
printf '[PASS] Bash syntax\n'

while IFS= read -r -d '' file; do
  "$PYTHON_BIN" -m py_compile "$file"
done < <(find "$HERE" -type f -name '*.py' -print0)
printf '[PASS] Python compilation\n'

"$PYTHON_BIN" "$HERE/tests/test_package_contract_v2.3.4.py"
printf '[PASS] package contract\n'

"$PYTHON_BIN" "$HERE/tests/test_powershell_lexical_v2.3.4.py"
printf '[PASS] PowerShell lexical and CmdletBinding contract\n'

self_report="$(mktemp -t vut-selftest-XXXXXX.json)"
trap 'rm -f "$self_report"' EXIT
bash "$HERE/install-vut-ai-tutor-universal-v2.3.4.sh" --action self-test --report-path "$self_report"
printf '[PASS] dispatcher and engine self-test\n'

"$PYTHON_BIN" "$HERE/tests/test_platform_detection_v2.3.4.py"
printf '[PASS] platform detection and Docker published-port discovery\n'

"$PYTHON_BIN" "$HERE/tests/test_desktop_official_lifecycle_v2.3.4.py"
printf '[PASS] official Desktop lifecycle and Verify autostart\n'

"$PYTHON_BIN" "$HERE/tests/test_api_platforms_e2e_v2.3.4.py"
printf '[PASS] Remote/Docker/BareMetal install-verify-uninstall and rollback E2E\n'

"$PYTHON_BIN" "$HERE/tests/test_cli_wrappers_e2e_v2.3.4.py"
printf '[PASS] Bash/Python entry-point E2E with reverse-proxy prefix\n'

"$PYTHON_BIN" "$HERE/tests/test_universal_pdf_integration.py"
printf '[PASS] universal PDF payload and feature-preservation contracts\n'

"$PYTHON_BIN" "$HERE/tests/test_pdf_installer.py"
printf '[PASS] Desktop Function backup and settings preservation against mock API\n'

if [[ "${VUT_RUN_PDF_TESTS:-0}" == "1" ]]; then
  "$PYTHON_BIN" "$HERE/tests/test_pdf_delivery.py"
  "$PYTHON_BIN" "$HERE/tests/test_pdf_source_recovery.py"
  node --check "$HERE/docs/canvas.pdf-hotfix.js"
  node --test "$HERE/tests/test_pdf_diagnostic.mjs"
  printf '[PASS] optional real-ASGI PDF and JavaScript regression tests\n'
fi

"$PYTHON_BIN" "$HERE/tests/test_canvas_layout_contract.py"
printf '[PASS] Canvas layout contract and preservation\n'
if [[ "${VUT_RUN_CANVAS_BROWSER_TESTS:-0}" == "1" ]]; then
  "$PYTHON_BIN" "$HERE/tests/test_canvas_layout_browser.py"
  printf '[PASS] Chromium Canvas lifecycle regressions\n'
fi

printf '[PASS] VUT AI Tutor Universal Installer 2.3.4 Linux/macOS-safe test completed.\n'
