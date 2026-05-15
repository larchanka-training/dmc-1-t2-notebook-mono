#!/usr/bin/env bash
set -euo pipefail

compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    echo "Docker Compose is not installed." >&2
    exit 1
  fi
}


# Запуск Docker Compose
echo "🚀 Запуск Frontend и API-Backend..."
compose up --build -d

echo "🚀 Проверка статуса:"

compose ps

echo "✅ Фронтенд и API-Бэкенд запущены!."
