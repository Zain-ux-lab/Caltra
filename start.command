#!/bin/zsh
cd "${0:A:h}"
if [[ ! -x .venv/bin/python || ! -f dist/index.html ]]; then
  echo 'Setup is missing. See README.md for installation steps.'
  read '?Press Enter to close.'
  exit 1
fi
if /usr/bin/curl -fsS http://127.0.0.1:8000/api/status >/dev/null 2>&1; then
  open http://127.0.0.1:8000
  exit 0
fi
(sleep 2; open http://127.0.0.1:8000) &
exec .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
