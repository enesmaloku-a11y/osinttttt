
#!/bin/sh
set -eu

python -m streamlit run dashboard.py \
  --server.address=0.0.0.0 \
  --server.port="${PORT:-8501}" &
WEB_PID=$!

(
  while kill -0 "$WEB_PID" 2>/dev/null; do
    if [ "${OSINT_RUN_AI:-0}" = "1" ]; then
      python -u ekzekuto.py 20 || true
    else
      python -u -c \
        'import collector; print(collector.mblidh_te_gjitha())' || true
    fi
    sleep "${OSINT_INTERVAL:-3600}"
  done
) &
WORKER_PID=$!

trap 'kill "$WEB_PID" "$WORKER_PID" 2>/dev/null || true' INT TERM EXIT
wait "$WEB_PID"
