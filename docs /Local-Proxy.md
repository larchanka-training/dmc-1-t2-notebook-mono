# Reverse-Proxy

## 1. Общая информация

Проект использует [**Nginx** как **reverse-proxy**](https://github.com/larchanka-training/python-typescript-wiki/blob/5fb06aecf7fa8bc8dbbb1bf0e3e38be20a0e10ca/docker-compose.yaml#L61) для маршрутизации трафика к разным сервисам внутри локальной сети Docker. Reverse-proxy выполняет следующие функции:

- Прокси для приложений и API.
- Обеспечение SSL шифрования через самоподписанный сертификат.
- Проброс HTTP заголовков для корректной идентификации клиента.
- Централизованное управление доступом к сервисам.

Используемые сервисы:

|Домен|Прокси на|Порт приложения|
|---|---|---|
|`training.wiki`|Frontend-приложение|3000|
|`api.training.wiki`|API|8000|
|`pgadmin.training.wiki`|pgAdmin|5050|

---

## 2. [Dockerfile](https://github.com/larchanka-training/python-typescript-wiki/blob/main/proxy/Dockerfile)

Dockerfile создаёт контейнер с Nginx и настраивает SSL:

```dockerfile
FROM nginx:alpine

COPY nginx.conf /etc/nginx/nginx.conf

RUN apk update && apk add bash openssl

RUN mkdir /keys  # Создание директории для ключей

RUN openssl genrsa -out /keys/training.wiki-key.pem 2048  # Генерация приватного ключа

RUN openssl req -x509 -new -nodes -batch \ # Генерация самоподписанного сертификата
	-key /keys/training.wiki-key.pem \
	-sha256 -days 365 \
	-subj "/CN=training.wiki" \
	-out /keys/training.wiki.pem

```

**Примечания:**

- Используется образ `nginx:alpine` для минимального размера.
- Устанавливаются утилиты `bash` и `openssl`.
- Генерируется самоподписанный сертификат для HTTPS (`.pem` и ключ `.key`).
- Все ключи сохраняются в `/keys`.

---

## 3. Конфигурация Nginx ([`nginx.conf`](https://github.com/larchanka-training/python-typescript-wiki/blob/main/proxy/nginx.conf))

### 3.1 Основные параметры

```nginx
worker_processes 1;
events { worker_connections 1024; }
http {
	sendfile on;
	include mime.types;`
```

- `worker_processes` — количество рабочих процессов Nginx (1 для простого проекта).
- `worker_connections` — максимальное количество соединений на один процесс.
- `sendfile on;` — ускоряет отдачу статических файлов.

---

### 3.2 Upstream сервисы

```nginx
upstream app {
  server host.docker.internal:3000;
}
upstream api {
  server host.docker.internal:8000;
}
upstream pgadmin {
  server host.docker.internal:5050;
}

```

- Upstream блоки задают внутренние сервисы, к которым Nginx будет проксировать запросы.
- `host.docker.internal` используется для доступа к хост-машине из контейнера Docker (тестовая конфигурация для локальной разработки).
    

---

### 3.3 Серверы

#### 3.3.1 Frontend-приложение

```nginx
server {
  listen 80;
  listen 443 ssl;
  server_name training.wiki;

  ssl_certificate /keys/training.wiki.pem;
  ssl_certificate_key /keys/training.wiki-key.pem;

  location / {
      proxy_pass http://app;
      proxy_redirect     off;
      proxy_set_header   Host $host;
      proxy_set_header   X-Real-IP $remote_addr;
      proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header   X-Forwarded-Host $server_name;
  }
}
```

#### 3.3.2 API

```nginx
server {
  listen 80;
  listen 443 ssl;
  server_name api.training.wiki;

  ssl_certificate /keys/training.wiki.pem;
  ssl_certificate_key /keys/training.wiki-key.pem;

  location / {
      proxy_pass http://api;
      proxy_redirect     off;
      proxy_set_header   Host $host;
      proxy_set_header   X-Real-IP $remote_addr;
      proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header   X-Forwarded-Host $server_name;
  }
}
```

#### 3.3.3 pgAdmin

```nginx
server {
  listen 80;
  listen 443 ssl;
  server_name pgadmin.training.wiki;

  ssl_certificate /keys/training.wiki.pem;
  ssl_certificate_key /keys/training.wiki-key.pem;

  location / {
      proxy_pass http://pgadmin;
      proxy_redirect     off;
      proxy_set_header   Host $host;
      proxy_set_header   X-Real-IP $remote_addr;
      proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header   X-Forwarded-Host $server_name;
  }
}
```

**Общие настройки для всех серверов:**

- `proxy_pass` — адрес внутреннего сервиса.
- `proxy_redirect off` — отключает автоматическое изменение Location заголовков.
- `proxy_set_header` — проброс HTTP-заголовков для идентификации исходного запроса и корректной работы приложений.

---

## 4. Особенности работы

1. Контейнер Nginx обслуживает все запросы на порты 80 (HTTP) и 443 (HTTPS) для разных поддоменов.
2. Все сервисы доступны по поддоменам:
    - `training.wiki` → frontend
    - `api.training.wiki` → API
    - `pgadmin.training.wiki` → pgAdmin
3. Используется **самоподписанный SSL сертификат**, поэтому браузеры могут выдавать предупреждение при локальном доступе.
4. Для продакшена рекомендуется заменить сертификат на подписанный CA (например, Let's Encrypt).
