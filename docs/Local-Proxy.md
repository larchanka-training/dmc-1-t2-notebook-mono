# Reverse-Proxy

## 1. General Information

The project uses [**Nginx** as a **reverse proxy**](https://github.com/larchanka-training/python-typescript-wiki/blob/5fb06aecf7fa8bc8dbbb1bf0e3e38be20a0e10ca/docker-compose.yaml#L61) to route traffic to different services within the local Docker network. The reverse proxy performs the following functions:

- Proxying for the applications and the API.
- Providing SSL encryption via a self-signed certificate.
- Forwarding HTTP headers for correct client identification.
- Centralized management of access to services.

Services in use:

|Domain|Proxies to|Application port|
|---|---|---|
|`training.wiki`|Frontend application|3000|
|`api.training.wiki`|API|8000|
|`pgadmin.training.wiki`|pgAdmin|5050|

---

## 2. [Dockerfile](https://github.com/larchanka-training/python-typescript-wiki/blob/main/proxy/Dockerfile)

The Dockerfile creates a container with Nginx and configures SSL:

```dockerfile
FROM nginx:alpine

COPY nginx.conf /etc/nginx/nginx.conf

RUN apk update && apk add bash openssl

RUN mkdir /keys  # Create a directory for the keys

RUN openssl genrsa -out /keys/training.wiki-key.pem 2048  # Generate the private key

RUN openssl req -x509 -new -nodes -batch \ # Generate a self-signed certificate
	-key /keys/training.wiki-key.pem \
	-sha256 -days 365 \
	-subj "/CN=training.wiki" \
	-out /keys/training.wiki.pem

```

**Notes:**

- The `nginx:alpine` image is used for a minimal size.
- The `bash` and `openssl` utilities are installed.
- A self-signed certificate is generated for HTTPS (a `.pem` file and a `.key` key).
- All keys are stored in `/keys`.

---

## 3. Nginx Configuration ([`nginx.conf`](https://github.com/larchanka-training/python-typescript-wiki/blob/main/proxy/nginx.conf))

### 3.1 Main Parameters

```nginx
worker_processes 1;
events { worker_connections 1024; }
http {
	sendfile on;
	include mime.types;`
```

- `worker_processes` — the number of Nginx worker processes (1 for a simple project).
- `worker_connections` — the maximum number of connections per process.
- `sendfile on;` — speeds up serving static files.

---

### 3.2 Upstream Services

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

- The upstream blocks define the internal services that Nginx will proxy requests to.
- `host.docker.internal` is used to access the host machine from the Docker container (a test configuration for local development).
    

---

### 3.3 Servers

#### 3.3.1 Frontend Application

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

**Common settings for all servers:**

- `proxy_pass` — the address of the internal service.
- `proxy_redirect off` — disables automatic modification of Location headers.
- `proxy_set_header` — forwarding of HTTP headers for identifying the original request and for the correct operation of the applications.

---

## 4. Operational Notes

1. The Nginx container handles all requests on ports 80 (HTTP) and 443 (HTTPS) for the different subdomains.
2. All services are available via subdomains:
    - `training.wiki` → frontend
    - `api.training.wiki` → API
    - `pgadmin.training.wiki` → pgAdmin
3. A **self-signed SSL certificate** is used, so browsers may show a warning on local access.
4. For production, it is recommended to replace the certificate with a CA-signed one (for example, Let's Encrypt).
