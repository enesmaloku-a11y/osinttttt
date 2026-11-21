
#!/bin/sh
set -eu

python -m streamlit run dashboard.py \
  --server.address=0.0.0.0 \
  --server.port="${PORT:-8501}" &
WEB_PID=$!

WORKER_PID=
cleanup() {
  if [ -n "$WORKER_PID" ]; then
    kill "$WORKER_PID" 2>/dev/null || true
  fi
  kill "$WEB_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Pa një bazë të shprehur, dashboard-i në cloud hap demon sintetike.
# Një punëtor pa OSINT_DB do të shkruante në një bazë tjetër, të padukshme për dashboard-in.
if [ -n "${OSINT_DB:-}" ]; then
  set -- --interval "${OSINT_INTERVAL:-3600}"
  if [ "${OSINT_RUN_AI:-0}" != "1" ]; then
    set -- "$@" --mbledhje
  fi
  python -u ekzekuto.py 20 "$@" &
  WORKER_PID=$!
fi

wait "$WEB_PID"
