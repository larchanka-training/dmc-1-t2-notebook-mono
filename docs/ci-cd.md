# CI/CD документация

## 1. Структура репозитория

Проект состоит из нескольких частей:

```text
.
├── api
├── ui
├── proxy
├── docs
├── docker-compose.yaml
├── start-services.sh
├── .gitmodules
└── README.md
```

## 2. Компоненты проекта

### Backend: `api`

Backend находится в директории `api`.

Обнаружено:

- Python backend
- FastAPI-приложение
- есть `pyproject.toml`
- есть `requirements-dev.txt`
- есть тесты в директории `tests`
- пример теста: `tests/test_health.py`

### Frontend: `ui`

Frontend находится в директории `ui`.

Обнаружено:

- TypeScript frontend
- Vite
- npm
- есть `package.json`
- есть `package-lock.json`
- есть `eslint.config.js`

### Proxy: `proxy`

Proxy находится в директории `proxy`.

Обнаружено:

- nginx
- `Dockerfile`
- `nginx.conf`

## 3. Git submodules

В ходе проверки было обнаружено, что директории `api` и `ui` подключены как Git submodules.

Это означает, что основной репозиторий хранит не полный код `api` и `ui`, а ссылки на отдельные репозитории и конкретные commit hash.

Проверить конфигурацию submodules:

```bash
cat .gitmodules
```

Проверить статус submodules:

```bash
git submodule status
```

## 4. Клонирование репозитория

При обычном клонировании:

```bash
git clone <repository-url>
```

директории `api` и `ui` могут оказаться пустыми.

Для корректного клонирования проекта нужно использовать:

```bash
git clone --recurse-submodules <repository-url>
```

Если репозиторий уже был склонирован без submodules:

```bash
git submodule update --init --recursive
```

## 5. Важное требование для GitHub Actions

Так как проект использует Git submodules, будущий GitHub Actions workflow должен использовать recursive checkout:

```yaml
- uses: actions/checkout@v4
  with:
    submodules: recursive
```

Без этого `api` и `ui` не будут загружены в CI.

## 6. Обнаруженные проблемы

### Каталог `docs ` с пробелом в конце

В репозитории был обнаружен каталог:

```text
docs 
```

В имени директории был лишний пробел в конце.

Это может вызывать проблемы в:

- терминале
- IDE
- GitHub Actions
- Docker scripts
- документации

Проблема исправляется переименованием:

```bash
mv "docs " docs
```

## 7. Локальный запуск и Docker

Для локального запуска требуется запущенный Docker daemon.

На macOS нужно запустить Docker Desktop:

```text
Applications → Docker
```

Проверить, что Docker работает:

```bash
docker info
```

Если Docker не запущен, при запуске проекта может появиться ошибка:

```text
Cannot connect to the Docker daemon
```

Запуск сервисов:

```bash
./start-services.sh
```

или напрямую:

```bash
docker compose -f docker-compose.yaml up -d --build
```

## 8. Вывод по первому DevOps-аудиту

По итогам проверки:

- структура репозитория изучена
- обнаружены Git submodules `api` и `ui`
- определены команды для корректного клонирования submodules
- обнаружена и исправляется проблема с каталогом `docs `
- определено требование для будущего GitHub Actions: `submodules: recursive`
- зафиксировано требование: Docker Desktop должен быть запущен перед локальным стартом проекта
