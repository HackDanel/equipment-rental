#!/bin/sh
# Копирует приложение на сервер по SSH и (пере)запускает стек.
# Использование: deploy/deploy.sh <ssh-host> [remote-dir] [domain]
# При первом запуске создаёт <remote-dir>/.env со случайными секретами.
set -eu
HOST=${1:?usage: deploy.sh <ssh-host> [remote-dir] [domain]}
DIR=${2:-rental}
DOMAIN=${3:-rental.37.194.184.235.sslip.io}
ROOT=$(cd "$(dirname "$0")/.." && pwd)

ssh "$HOST" "mkdir -p $DIR/src"
rsync -az --delete \
  --exclude .git --exclude .venv --exclude .env --exclude db.sqlite3 --exclude media \
  --exclude staticfiles --exclude docs --exclude deploy --exclude e2e --exclude '__pycache__' \
  "$ROOT/" "$HOST:$DIR/src/"
rsync -az "$ROOT/deploy/docker-compose.prod.yml" "$HOST:$DIR/docker-compose.yml"
rsync -az "$ROOT/deploy/apache-rental.conf" "$ROOT/deploy/backup.sh" "$HOST:$DIR/"

ssh "$HOST" "cd $DIR && if [ ! -f .env ]; then
  {
    echo DOMAIN=$DOMAIN
    echo WEB_PORT=8210
    echo SECRET_KEY=\$(head -c 48 /dev/urandom | base64 | tr -d '/+=')
    echo DB_PASSWORD=\$(head -c 24 /dev/urandom | base64 | tr -d '/+=')
  } > .env
  chmod 600 .env
fi
# Полный лог в файл, на экран — хвост; при ошибке сборки скрипт завершается с ошибкой.
if docker compose up -d --build > deploy.log 2>&1; then tail -3 deploy.log; else tail -30 deploy.log; exit 1; fi"
