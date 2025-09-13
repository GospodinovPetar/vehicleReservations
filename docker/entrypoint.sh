#!/usr/bin/env sh
set -e

until python - <<'PY'
import os, socket, sys
h=os.environ.get("DB_HOST","db"); p=int(os.environ.get("DB_PORT","5432"))
s=socket.socket()
try: s.connect((h,p)); sys.exit(0)
except Exception: sys.exit(1)
PY
do
  echo "[entrypoint] db not ready, retrying..."
  sleep 1
done

python manage.py makemigrations --noinput || true

python manage.py migrate --noinput

exec "$@"