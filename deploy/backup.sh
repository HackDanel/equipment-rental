#!/bin/sh
# Резервная копия продакшена: дамп PostgreSQL и архив загруженных фото.
# Запускается на сервере из каталога стека:  cd ~/rental && ./backup.sh
# Хранит последние KEEP копий в ./backups.
set -eu
cd "$(dirname "$0")"
KEEP=${KEEP:-14}
STAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p backups

docker compose exec -T db pg_dump -U rental -d rental --format=custom > "backups/db_$STAMP.dump"
docker compose exec -T web tar -C /app -czf - media > "backups/media_$STAMP.tar.gz"

ls -1t backups/db_*.dump | tail -n +$((KEEP + 1)) | xargs -r rm --
ls -1t backups/media_*.tar.gz | tail -n +$((KEEP + 1)) | xargs -r rm --
echo "backups/db_$STAMP.dump backups/media_$STAMP.tar.gz"
