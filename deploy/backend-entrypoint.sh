#!/bin/sh
# Startskript des Backend-Containers: erst Migrationen, dann der eigentliche Befehl.
# Mit RUN_MIGRATIONS=0 lässt sich der Schritt abschalten (z. B. für einmalige Hilfsbefehle).
set -eu

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "backend-entrypoint: alembic upgrade head"
    alembic upgrade head
fi

exec "$@"
