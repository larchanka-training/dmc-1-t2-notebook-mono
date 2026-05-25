# AWS Setup Guide — JS Notebook Mono

## Project Overview

This is a **monorepo** (`dmc-1-t2-notebook-mono`) that orchestrates two submodules:

| Submodule | Tech | Image |
|---|---|---|
| `api/` | Python FastAPI + Liquibase | `ghcr.io/larchanka-training/js-notebook-api` |
| `ui/` | JavaScript frontend | `ghcr.io/larchanka-training/js-notebook-ui` |

Production is defined by `docker-compose.prod.yaml` — four containers: `frontend`, `api`, `postgres:16`, and `proxy` (Nginx 1.27 on port 80). **No AWS exists yet.** The `deploy.yml` workflow is a dry-run that validates inputs only.

---

## Deep Technical Explanation: AWS for This Project

### The Architecture That Must Be Built

```
Internet
   │
   ▼
Route 53 (DNS A record → Elastic IP)
   │
   ▼
EC2 Instance (t3.small or t3.medium)
   ├── Security Group: :443 open, :80 open, :22 restricted
   ├── Elastic IP (static public IP)
   └── Docker Compose stack
         ├── proxy (Nginx :80/:443) ← only container exposed
         ├── frontend (internal :80)
         ├── api (internal :8000, health-checked)
         └── postgres (internal :5432, volume-mounted)

GitHub Actions (OIDC)
   └── IAM Role → can SSH to EC2 and optionally push to ECR
```

### AWS Services Involved and Why

#### 1. EC2 (Elastic Compute Cloud)

EC2 is the virtual machine that runs the Docker Compose stack. The current `docker-compose.prod.yaml` is designed for a **single-host deployment** — all four containers share a Docker network on one machine.

**Why EC2 over ECS Fargate for this project:**
- Fargate launches each container as a separate task. PostgreSQL in Fargate requires EFS (Elastic File System) for persistence, which adds cost and complexity. EC2 with a named Docker volume (`psql-data:`) is simpler and matches the current Compose file exactly.
- Fargate is worth the trade-off only when horizontal scaling is needed. A single-EC2 deploy can be upgraded to ECS later.

**Recommended instance:** `t3.small` (2 vCPU, 2 GB RAM) for staging; `t3.medium` (2 vCPU, 4 GB RAM) for production.

**AMI choice:** Ubuntu 24.04 LTS (`ami-0c7217cdde317cfec` in eu-central-1). Docker's official packages are on Ubuntu's apt repos. Amazon Linux 2023 also works but requires `dnf` instead of `apt`.

#### 2. Elastic IP

EC2 instances get a new public IP on every stop/start unless pinned to an Elastic IP. The `SSH_HOST` GitHub secret must be stable — use Elastic IP.

**Cost:** Free while associated with a running instance. Billed ~$0.005/hr when the instance is stopped (to discourage waste).

#### 3. Security Group

Acts as a stateful firewall at the instance level. Required rules for this project:

| Direction | Port | Protocol | Source | Reason |
|---|---|---|---|---|
| Inbound | 80 | TCP | 0.0.0.0/0 | HTTP |
| Inbound | 443 | TCP | 0.0.0.0/0 | HTTPS |
| Inbound | 22 | TCP | your IP only | SSH for deployment |
| Outbound | all | all | 0.0.0.0/0 | Docker pulls, GitHub |

**Critical:** Never open port 5432 (PostgreSQL) or 8000 (FastAPI) to the internet. They are internal to Docker's network.

#### 4. IAM + OIDC (GitHub Actions Authentication)

This is the most security-critical piece. Instead of storing long-lived `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in GitHub Secrets (which can be leaked), GitHub Actions uses **OIDC (OpenID Connect)**:

1. GitHub's OIDC provider issues a short-lived JWT token for each workflow run.
2. AWS STS (Security Token Service) validates that token against a trusted OIDC provider.
3. STS issues a temporary IAM session credential (15-minute lifetime) scoped to a specific role.
4. The workflow uses that credential — no static keys ever exist.

The trust policy in `docs/aws-infrastructure.md` restricts which repos/branches can assume the role via the `sub` claim: `repo:larchanka-training/dmc-1-t2-notebook-mono:*`.

For SSH-only deployment (current architecture), the IAM role actually needs **no AWS permissions at all** — the OIDC flow only authenticates to GitHub. The deployment is pure SSH; AWS credentials would only be needed if you push to ECR or read from SSM Parameter Store.

#### 5. Route 53 (DNS)

Hosted zone for your domain. A single **A record** pointing to the EC2 Elastic IP. TTL of 300 seconds (5 min) for fast DNS propagation during first setup; raise to 3600 after stabilization.

#### 6. ACM + TLS (Two Options)

**Option A — Let's Encrypt / Certbot on the instance (simpler, no ALB cost):**
- Certbot runs on EC2, writes certs to `/etc/letsencrypt/`.
- Nginx reads certs from a mounted volume inside the `proxy` container.
- Auto-renews via cron. Port 443 terminates TLS at Nginx.

**Option B — ACM + Application Load Balancer (managed, higher cost):**
- ACM issues a free cert tied to your Route 53 domain.
- ALB terminates TLS, forwards plain HTTP to EC2 port 80.
- EC2 security group only allows port 80 from the ALB's security group — internet cannot reach port 80 directly.
- Higher cost (~$16/month for ALB) but zero cert renewal management.

For a small project, **Option A (Certbot)** is recommended.

#### 7. ECR vs GHCR Decision

Currently images are in GHCR (`ghcr.io/larchanka-training/`). Pulling from GHCR on EC2 requires a GitHub PAT (`GHCR_READ_TOKEN`) stored in GitHub Secrets and used in the deploy workflow. This works fine.

**If you switch to ECR:**
- Push to ECR in `docker-publish.yml` CI: `aws ecr get-login-password | docker login ...`
- EC2 instance profile (IAM role attached to EC2) grants `ecr:GetAuthorizationToken` and `ecr:BatchGetImage` — no token in secrets.
- Cleaner security posture; adds ECR storage cost (~$0.10/GB/month).

For this project size, **GHCR is adequate** — migration to ECR is an optional improvement.

#### 8. RDS vs Docker PostgreSQL

`docker-compose.prod.yaml` runs `postgres:16` with a named volume `psql-data`. This is simple but risky:

- If the EC2 instance is terminated (not stopped), the volume is lost.
- No automated backups unless you snapshot the EBS volume manually.

**Amazon RDS for PostgreSQL** adds:
- Automated daily backups with configurable retention.
- Point-in-time recovery.
- Multi-AZ failover.
- Cost: ~$15-25/month for `db.t3.micro`.

The application is database-URL-agnostic — only `DATABASE_URL` in `.env.prod` needs to change from `postgresql://admin:pass@postgres:5432/wiki` to `postgresql://admin:pass@<rds-endpoint>:5432/wiki`. The `postgres` service in the Compose file is simply removed.

---

## Step-by-Step AWS Console Setup

### Prerequisites

- AWS account created (root account → MFA enabled)
- A domain name registered (Route 53 or external registrar)
- GitHub repo: `larchanka-training/dmc-1-t2-notebook-mono`

---

### Phase 1 — IAM Baseline

**Step 1.1 — Enable MFA on root account**

1. Console → top-right username → **Security credentials**
2. **Multi-factor authentication (MFA)** → **Assign MFA device**
3. Choose **Authenticator app** → scan QR code → save

**Step 1.2 — Create an admin IAM user for daily use (do not use root)**

1. **IAM** → **Users** → **Create user**
2. Username: `admin-yourname`
3. **Attach policies directly** → `AdministratorAccess`
4. Create → save access keys
5. Enable MFA for this user too
6. Log in as this user from now on

**Step 1.3 — Create OIDC provider for GitHub Actions**

1. **IAM** → **Identity providers** → **Add provider**
2. Provider type: **OpenID Connect**
3. Provider URL: `https://token.actions.githubusercontent.com`
4. Click **Get thumbprint**
5. Audience: `sts.amazonaws.com`
6. **Add provider**

**Step 1.4 — Create IAM role for GitHub Actions**

1. **IAM** → **Roles** → **Create role**
2. Trusted entity type: **Web identity**
3. Identity provider: `token.actions.githubusercontent.com`
4. Audience: `sts.amazonaws.com`
5. **Next** → for now attach **no permissions** (SSH-only deploy needs none)
6. Role name: `github-actions-deploy`
7. **Create role**
8. Open the role → **Trust relationships** → **Edit trust policy**
9. Replace with:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<YOUR_ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:larchanka-training/dmc-1-t2-notebook-mono:*"
        }
      }
    }
  ]
}
```

Replace `<YOUR_ACCOUNT_ID>` with your 12-digit account ID (visible top-right in console). Save.

---

### Phase 2 — Networking

**Step 2.1 — Choose region**

Navigate to **eu-central-1 (Frankfurt)** in the top-right region selector. All subsequent resources must be in the same region.

**Step 2.2 — Security Group**

1. **EC2** → **Security Groups** → **Create security group**
2. Name: `notebook-prod-sg`
3. Description: `Production security group for notebook app`
4. VPC: default VPC is fine
5. **Inbound rules** → Add rule:
   - Type: `HTTP`, Port `80`, Source: `Anywhere-IPv4` (`0.0.0.0/0`)
   - Type: `HTTPS`, Port `443`, Source: `Anywhere-IPv4`
   - Type: `SSH`, Port `22`, Source: **My IP** (console fills this automatically)
6. Outbound: leave default (all traffic allowed)
7. **Create security group**

---

### Phase 3 — EC2 Instance

**Step 3.1 — Generate SSH Key Pair**

1. **EC2** → **Key Pairs** → **Create key pair**
2. Name: `notebook-prod-key`
3. Key pair type: `RSA`
4. Private key file format: `.pem`
5. **Create key pair** — downloads `notebook-prod-key.pem` to your machine
6. Run locally: `chmod 400 notebook-prod-key.pem`

This `.pem` file becomes the `SSH_PRIVATE_KEY` GitHub secret later.

**Step 3.2 — Launch EC2 Instance**

1. **EC2** → **Instances** → **Launch instances**
2. Name: `notebook-prod`
3. **AMI**: Ubuntu Server 24.04 LTS (search in community AMIs — free tier eligible in eu-central-1)
4. **Instance type**: `t3.small` for staging, `t3.medium` for production
5. **Key pair**: `notebook-prod-key`
6. **Network settings** → Edit:
   - VPC: default
   - Subnet: any public subnet
   - **Auto-assign public IP**: Disable (we'll use Elastic IP)
   - Security group: select `notebook-prod-sg`
7. **Storage**: 20 GB gp3 (increase to 30 GB if you expect large DB growth)
8. **Launch instance**

**Step 3.3 — Allocate and Associate Elastic IP**

1. **EC2** → **Elastic IPs** → **Allocate Elastic IP address**
2. Network border group: `eu-central-1`
3. **Allocate**
4. Select the new Elastic IP → **Actions** → **Associate Elastic IP address**
5. Resource type: `Instance`
6. Instance: select `notebook-prod`
7. **Associate**

Note the Elastic IP (e.g., `3.121.x.x`) — this becomes `SSH_HOST`.

**Step 3.4 — Install Docker on the instance**

SSH into the instance:

```bash
ssh -i notebook-prod-key.pem ubuntu@<ELASTIC_IP>
```

On the instance:

```bash
sudo apt-get update && sudo apt-get upgrade -y

curl -fsSL https://get.docker.com | sudo sh

sudo usermod -aG docker ubuntu

sudo apt-get install -y docker-compose-plugin

exit
```

SSH back in and verify:

```bash
docker --version
docker compose version
docker run hello-world
```

**Step 3.5 — Upload production env file to instance**

```bash
scp -i notebook-prod-key.pem .env.prod ubuntu@<ELASTIC_IP>:/home/ubuntu/.env.prod
```

Edit on instance, replacing all `change-me` values:

```bash
nano /home/ubuntu/.env.prod
```

Also copy the Nginx config:

```bash
scp -i notebook-prod-key.pem proxy/nginx.prod.conf ubuntu@<ELASTIC_IP>:/home/ubuntu/nginx.prod.conf
```

---

### Phase 4 — DNS (Route 53)

**Step 4.1 — Create Hosted Zone**

1. **Route 53** → **Hosted zones** → **Create hosted zone**
2. Domain name: `notebook.yourdomain.com` (or your root domain)
3. Type: **Public hosted zone**
4. **Create hosted zone**
5. Note the 4 NS records shown — update your domain registrar to use these name servers

**Step 4.2 — Create A Record**

1. In the hosted zone → **Create record**
2. Record name: leave blank for root, or `www`
3. Record type: `A`
4. Value: `<ELASTIC_IP>`
5. TTL: `300`
6. **Create records**

DNS propagation takes 5–60 minutes.

---

### Phase 5 — TLS with Certbot (Let's Encrypt)

On the EC2 instance:

```bash
sudo apt-get install -y certbot

sudo certbot certonly --standalone -d notebook.yourdomain.com --email you@example.com --agree-tos --non-interactive

ls /etc/letsencrypt/live/notebook.yourdomain.com/
```

Update `nginx.prod.conf` on the instance to add an HTTPS block:

```nginx
server {
    listen 80;
    server_name notebook.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name notebook.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/notebook.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/notebook.yourdomain.com/privkey.pem;

    location = /api/v1 {
        proxy_pass http://api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/v1/ {
        proxy_pass http://api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://frontend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Mount the certs into the `proxy` container by updating `docker-compose.prod.yaml` (proxy service volumes):

```yaml
proxy:
  volumes:
    - ./nginx.prod.conf:/etc/nginx/conf.d/default.conf:ro
    - /etc/letsencrypt:/etc/letsencrypt:ro
```

Set up auto-renewal:

```bash
sudo crontab -e
# Add:
0 3 * * * certbot renew --quiet && docker compose -f /home/ubuntu/docker-compose.prod.yaml restart proxy
```

---

### Phase 6 — First Real Deploy

**Step 6.1 — Add GitHub Environment Secrets**

GitHub → repo → **Settings** → **Environments** → `staging` → **Add secret**:

| Secret | Value |
|---|---|
| `SSH_HOST` | `<ELASTIC_IP>` |
| `SSH_USER` | `ubuntu` |
| `SSH_PRIVATE_KEY` | contents of `notebook-prod-key.pem` |
| `GHCR_USERNAME` | your GitHub username |
| `GHCR_READ_TOKEN` | GitHub PAT with `read:packages` scope |
| `POSTGRES_PASSWORD` | strong random password |
| `OAUTH_NAME_APPLICATION_ID` | your OAuth app ID |
| `OAUTH_NAME_SECRET_KEY` | your OAuth app secret |

**Step 6.2 — Update `deploy.yml` with real SSH steps**

Replace the dry-run `validate` job with the actual deploy as documented in `docs/deploy.md`:

```yaml
- name: Deploy via SSH
  uses: appleboy/ssh-action@v1
  with:
    host: ${{ secrets.SSH_HOST }}
    username: ${{ secrets.SSH_USER }}
    key: ${{ secrets.SSH_PRIVATE_KEY }}
    script: |
      echo "${{ secrets.GHCR_READ_TOKEN }}" | docker login ghcr.io -u "${{ secrets.GHCR_USERNAME }}" --password-stdin
      docker pull ghcr.io/larchanka-training/js-notebook-api:${{ inputs.image_tag }}
      docker pull ghcr.io/larchanka-training/js-notebook-ui:${{ inputs.image_tag }}
      IMAGE_TAG=${{ inputs.image_tag }} docker compose --env-file /home/ubuntu/.env.prod -f /home/ubuntu/docker-compose.prod.yaml up -d
```

**Step 6.3 — Trigger the workflow**

GitHub → **Actions** → `Manual Deploy` → **Run workflow** → `staging` → `main` → Run.

**Step 6.4 — Smoke check**

```bash
curl -fsS https://notebook.yourdomain.com/api/v1/health
curl -fsS https://notebook.yourdomain.com/
```

---

### Phase 7 — Rollback Procedure

Trigger `Manual Deploy` with a previous immutable tag:

```
sha-8be47cc
```

**Never use `main` for production rollback** — `main` is a mutable pointer and may have moved forward.

---

## Summary of AWS Resources Created

| Resource | Name | Monthly Cost (est.) |
|---|---|---|
| EC2 t3.small | `notebook-prod` | ~$15 |
| Elastic IP | (attached) | $0 while running |
| EBS 20 GB gp3 | root volume | ~$1.60 |
| Route 53 hosted zone | 1 zone | $0.50 |
| Route 53 queries | ~1M/month | ~$0.40 |
| ACM cert | (free with ALB) | $0 |
| **Total** | | **~$18/month** |

Optional additions if upgrading later: RDS `db.t3.micro` (+$15/month), ALB (+$16/month), ECR (+$0.10/GB).
