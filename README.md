# MDM SaaS — Multi-Tenant Apple MDM Server

A production-ready multi-tenant Mobile Device Management (MDM) server built with FastAPI, designed to manage macOS devices and deliver Microsoft Entra ID Platform SSO (PSSO) at scale.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         MDM SaaS Platform                           │
│                                                                     │
│  ┌──────────────┐    ┌──────────────────────────────────────────┐  │
│  │   Dashboard  │    │              FastAPI App                  │  │
│  │   (Browser)  │───▶│                                          │  │
│  └──────────────┘    │  ┌─────────────┐  ┌──────────────────┐  │  │
│                       │  │  REST API   │  │   MDM Protocol   │  │  │
│  ┌──────────────┐    │  │  /api/v1/   │  │  /mdm/apple/     │  │  │
│  │  macOS Device│    │  │  ─ auth     │  │  ─ checkin (PUT) │  │  │
│  │   (VM/Mac)   │────┼─▶│  ─ devices  │  │  ─ connect (PUT) │  │  │
│  └──────┬───────┘    │  │  ─ profiles │  └──────────────────┘  │  │
│         │            │  │  ─ enroll   │                          │  │
│         │ APNs Push  │  └─────────────┘  ┌──────────────────┐  │  │
│         │            │                    │   SQS Consumer   │  │  │
│  ┌──────▼───────┐    │                    │  command_queue   │  │  │
│  │ Apple APNs   │    │                    └──────────────────┘  │  │
│  │ api.push.    │    └────────────┬─────────────────────────────┘  │
│  │ apple.com    │                 │                                 │
│  └──────────────┘         ┌──────▼──────┐  ┌──────────────────┐   │
│                            │  PostgreSQL  │  │   AWS SQS        │   │
│                            │  (mdmdb)    │  │  (commands queue)│   │
│                            └─────────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### MDM Command Flow

```
Admin API          SQS Queue         APNs              macOS Device
    │                  │               │                     │
    │ POST /lock        │               │                     │
    │──────────────┐   │               │                     │
    │  DB: queued  │   │               │                     │
    │◀─────────────┘   │               │                     │
    │                  │               │                     │
    │ SQS message ────▶│               │                     │
    │                  │ send push ───▶│                     │
    │                  │               │ wake-up push ──────▶│
    │                  │               │                     │ PUT /connect
    │                  │               │             ┌───────│
    │                  │               │  deliver    │       │
    │◀──────────────────────────────── │ ◀── command │       │
    │                  │               │             └──────▶│ execute
    │                  │               │             ┌───────│
    │  DB: completed   │               │    result   │       │
    │◀──────────────────────────────────────────────▶│       │
    │                  │               │             └───────┘
```

### Enrollment Flow

```
Admin             MDM Server          macOS Device
  │                   │                    │
  │ POST /tokens       │                    │
  │──────────────────▶│                    │
  │  enrollment URL   │                    │
  │◀──────────────────│                    │
  │                   │                    │
  │ share URL ──────────────────────────── │ (Safari)
  │                   │                    │
  │                   │ GET /enroll/{token}│
  │                   │◀───────────────────│
  │                   │ signed .mobileconfig
  │                   │───────────────────▶│ install profile
  │                   │                    │
  │                   │ PUT /checkin (Authenticate)
  │                   │◀───────────────────│
  │                   │ PUT /checkin (TokenUpdate)
  │                   │◀───────────────────│
  │                   │  device enrolled   │
  │                   │────────────────────│
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI (async) + Uvicorn |
| Database | PostgreSQL 15 + SQLAlchemy 2.x async + asyncpg |
| Queue | AWS SQS (LocalStack for dev) |
| Push | Apple APNs HTTP/2 via httpx |
| TLS | Caddy reverse proxy + mkcert (dev) / ACM (prod) |
| Auth | JWT (dashboard) + mTLS (MDM endpoints) |
| Profiles | plistlib + cryptography (CMS signing) |
| Infra | Docker Compose (dev) / AWS ECS Fargate (prod) |

---

## Prerequisites

- macOS (host) or Linux
- Docker Desktop
- Python 3.12+
- Caddy (`brew install caddy`)
- mkcert (`brew install mkcert`) — dev TLS only

---

## Quick Start (Local Dev)

### 1. Clone and configure

```bash
git clone <repo>
cd mdm-saas
cp .env.example .env
# Edit .env — set MDM_SERVER_URL to your host IP
```

### 2. Generate dev certificates

```bash
# Install mkcert CA
mkcert -install

# TLS cert for HTTPS (replace IP with your vmnet8 interface IP)
mkcert 192.168.64.1
mv 192.168.64.1.pem 192.168.64.1-key.pem ./

# MDM profile signing cert (use Apple Developer ID Application cert)
# Copy to: certs/dev/mdm_signing.pem + certs/dev/mdm_signing.key

# Device identity cert (for enrollment profile PKCS#12)
bash scripts/gen_dev_certs.sh

# APNs push certificate
# → See: docs/apns-setup.md
```

### 3. Start services

```bash
# Start PostgreSQL + LocalStack (SQS)
docker compose up -d db localstack

# Run migrations
docker compose run --rm app alembic upgrade head

# Seed test tenant + admin user
docker compose run --rm app python scripts/seed_db.py

# Start MDM server
docker compose up -d app

# Start HTTPS reverse proxy
caddy start --config Caddyfile
```

### 4. Verify

```bash
curl -sk https://<your-ip>/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@acme.com","password":"secret"}'
# → {"access_token": "..."}
```

---

## Key Endpoints

### Dashboard API (JWT auth)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/login` | Get JWT token |
| GET | `/api/v1/devices` | List enrolled devices |
| GET | `/api/v1/devices/{id}` | Device detail (serial, OS, model) |
| POST | `/api/v1/devices/{id}/query` | Queue DeviceInformation |
| POST | `/api/v1/devices/{id}/lock` | Queue DeviceLock |
| POST | `/api/v1/devices/{id}/erase` | Queue EraseDevice |
| POST | `/api/v1/devices/{id}/restart` | Queue RestartDevice |
| POST | `/api/v1/enrollment/tokens` | Create enrollment token |
| GET | `/api/v1/enrollment/{token}` | Download enrollment profile |
| POST | `/api/v1/profiles` | Create config profile |
| POST | `/api/v1/profiles/{id}/push` | Push profile to all devices |
| POST | `/api/v1/profiles/psso` | Push PSSO (Entra ID SSO) profile |

### MDM Protocol (mTLS / device cert auth)

| Method | Path | Description |
|--------|------|-------------|
| PUT | `/mdm/apple/checkin` | Device check-in (Authenticate, TokenUpdate, CheckOut) |
| PUT | `/mdm/apple/connect` | Command delivery + result reporting |

---

## How It Works

### Multi-Tenancy
Every database query is scoped by `tenant_id`. Tenant is resolved from:
- **Dashboard API**: JWT claims (`sub` = user ID → `tenant_id`)
- **MDM endpoints**: `devices.udid` lookup → `tenant_id` (no JWT)

### Device Enrollment
1. Admin creates an enrollment token via API
2. Token URL is shared with the user
3. User opens URL in Safari on their Mac → downloads signed `.mobileconfig`
4. Profile installs → macOS sends `Authenticate` then `TokenUpdate` to `/mdm/apple/checkin`
5. Server stores APNs push token, push magic, push topic
6. Device appears in dashboard as `enrolled`

### Command Delivery
1. Admin calls API (e.g., `POST /devices/{id}/lock`)
2. `MdmCommand` record created with `status=queued`
3. SQS message queued with `{device_id, command_id}`
4. SQS consumer (`command_queue.py`) picks up message → sends APNs wake-up push
5. Device wakes → calls `PUT /mdm/apple/connect`
6. Server returns queued command plist
7. Device executes → calls connect again with result
8. Server marks command `completed` or `failed`, stores result

### PSSO (Platform Single Sign-On)
Pushes `com.apple.extensiblesso` payload to enable macOS login with Microsoft Entra ID credentials. Requires:
- Microsoft Company Portal app installed on device
- Entra ID tenant configured
- Registration token from Entra (for automated device registration)

---

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL async URL | `postgresql+asyncpg://mdm:mdm@localhost:5433/mdmdb` |
| `SECRET_KEY` | JWT signing key (256-bit hex) | `5b4875...` |
| `MDM_SERVER_URL` | Public HTTPS URL of MDM server | `https://192.168.64.1` |
| `APNS_CERT_PATH` | APNs push certificate PEM | `./certs/dev/apns.pem` |
| `APNS_KEY_PATH` | APNs push private key | `./certs/dev/apns.key` |
| `APNS_USE_SANDBOX` | Use APNs sandbox | `false` |
| `APNS_PUSH_TOPIC` | APNs push topic from cert | `com.apple.mgmt.External.xxx` |
| `MDM_SIGNING_CERT_PATH` | Profile signing cert (Developer ID) | `./certs/dev/mdm_signing.pem` |
| `MDM_SIGNING_KEY_PATH` | Profile signing key | `./certs/dev/mdm_signing.key` |
| `SQS_COMMAND_QUEUE_URL` | SQS queue URL | `http://localhost:4566/.../mdm-commands` |
| `AWS_REGION` | AWS region | `ap-south-1` |

---

## Database Schema

```
tenants          users            devices
────────         ─────            ───────
id (PK)          id (PK)          id (PK)
slug             tenant_id (FK)   tenant_id (FK)
name             email            udid
apns_push_topic  hashed_password  serial_number
                 role             os_version
                                  model / hostname
enrollment_tokens                 push_token
─────────────────                 push_magic
id (PK)          mdm_commands     push_topic
tenant_id (FK)   ────────────     status
token            id (PK)          enrolled_at
platform         tenant_id (FK)   last_checkin
reusable         device_id (FK)
expires_at       command_uuid     profiles
used             command_type     ────────
                 status           id (PK)
                 payload (JSONB)  tenant_id (FK)
                 result (JSONB)   name / type
                 queued_at        payload (JSONB)
                 executed_at
```

---

## Production Limitations (Current Dev Setup)

| Issue | Dev Workaround | Production Fix |
|-------|---------------|----------------|
| APNs push unreliable on VMs | `sudo /usr/libexec/mdmclient daemon` | Real Macs respond instantly |
| Caddy must be started manually | `caddy start --config Caddyfile` | Run as ECS sidecar or ALB |
| SQS consumer not auto-started | Send push manually | ECS task for `command_queue.py` |
| mkcert CA (not publicly trusted) | Install CA profile on device | ACM / Let's Encrypt cert |
| Single server | Docker Compose | ECS Fargate + RDS + SQS |

---

## AWS Production Architecture

```
Internet
    │
    ▼
┌─────────────────┐
│  Route 53 DNS   │
│  mdm.company.io │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  ACM Certificate│
│  (auto-renew)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│  ALB (HTTPS)    │────▶│  ECS Fargate    │
│  port 443       │     │  MDM App Tasks  │
└─────────────────┘     └────────┬────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼              ▼
             ┌──────────┐  ┌──────────┐  ┌──────────┐
             │  RDS     │  │  SQS     │  │ Secrets  │
             │ Postgres │  │ Commands │  │ Manager  │
             │ (Multi-AZ│  │  Queue   │  │ APNs Key │
             └──────────┘  └──────────┘  └──────────┘
```

See `infra/terraform/` for full AWS infrastructure code.

---

## APNs Push Certificate Setup

Getting a real APNs MDM push certificate requires:

1. Register at `https://mdmcert.download` (organizational email required)
2. Generate encryption key pair: `openssl req -newkey rsa:2048 ...`
3. Generate push CSR: `openssl req -newkey rsa:2048 -keyout apns.key ...`
4. Submit to mdmcert.download API (see `scripts/get_apns_cert.py`)
5. Decrypt the returned `.p7` file with your encryption key
6. Upload the decrypted request to `https://identity.apple.com/pushcert`
7. Download the `.pem` certificate
8. Set `APNS_CERT_PATH` and `APNS_KEY_PATH` in `.env`
9. Update `apns_push_topic` in `tenants` table with UID from the cert

---

## Tested On

- macOS Sequoia 15.1 (Apple Silicon VM via UTM/Parallels)
- Apple APNs production endpoint (`api.push.apple.com`)
- mdmcert.download vendor signing (Jesse Peterson / MacTechs)
- Apple Push Certificates Portal (`identity.apple.com/pushcert`)
