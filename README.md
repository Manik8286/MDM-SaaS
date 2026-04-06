# MDM SaaS — Multi-Tenant Apple MDM Server

A production-ready multi-tenant Mobile Device Management (MDM) server built with FastAPI, designed to manage macOS devices with Microsoft Entra ID Platform SSO (PSSO), software distribution, compliance enforcement, and JIT admin access.

---

## Features

| Category | Capability |
|----------|-----------|
| **Enrollment** | Token-based enrollment, signed `.mobileconfig` delivery, APNs push registration |
| **Device Management** | Lock, erase, restart, query device info, per-device and fleet-wide actions |
| **PSSO** | Platform SSO with Microsoft Entra ID (Secure Enclave or Password auth) |
| **Policies** | USB storage block (macOS 12–15+), Gatekeeper enforcement — push/remove per device or fleet |
| **Patch Management** | Installed app inventory, available OS updates, compliance scan, remote install |
| **Software Distribution** | Package upload (`.pkg`, `.dmg`, `.zip`), self-service portal, admin approval workflow |
| **JIT Admin Access** | Temporary admin elevation via portal request, auto-revoke on expiry |
| **Compliance** | Policy-based compliance engine (FileVault, Firewall, Gatekeeper, PSSO, updates) |
| **Audit Logs** | Full audit trail for all admin actions |
| **Webhook Notifications** | Slack / Teams / Discord notifications for requests and auto-revoke events |
| **Management Agent** | Pure-bash LaunchDaemon agent — installs software, runs scripts, no Python dependency |
| **Multi-Tenancy** | Full tenant isolation — every query scoped by `tenant_id` |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         MDM SaaS Platform                           │
│                                                                     │
│  ┌──────────────┐    ┌──────────────────────────────────────────┐  │
│  │  Next.js     │    │              FastAPI App                  │  │
│  │  Dashboard   │───▶│                                          │  │
│  └──────────────┘    │  ┌─────────────┐  ┌──────────────────┐  │  │
│                       │  │  REST API   │  │   MDM Protocol   │  │  │
│  ┌──────────────┐    │  │  /api/v1/   │  │  /mdm/apple/     │  │  │
│  │  macOS Device│    │  │  ─ auth     │  │  ─ checkin (PUT) │  │  │
│  │   (Mac/VM)   │────┼─▶│  ─ devices  │  │  ─ connect (PUT) │  │  │
│  └──────┬───────┘    │  │  ─ profiles │  └──────────────────┘  │  │
│         │            │  │  ─ packages │                          │  │
│         │ APNs Push  │  │  ─ portal   │  ┌──────────────────┐  │  │
│         │            │  │  ─ agent    │  │   Auto-Revoke    │  │  │
│  ┌──────▼───────┐    │  └─────────────┘  │   Background     │  │  │
│  │ Apple APNs   │    │                    │   Worker         │  │  │
│  │ api.push.    │    └────────────┬───────┴──────────────────┘  │  │
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

### Software Install Flow (Agent)

```
User (Portal)      MDM Server         Agent (Mac)
    │                  │                   │
    │ Request app       │                   │
    │─────────────────▶│                   │
    │ Admin approves   │                   │
    │──────────────────▶ ScriptJob queued  │
    │                  │                   │ polls /agent/jobs
    │                  │◀──────────────────│
    │                  │ job (base64 cmd)  │
    │                  │──────────────────▶│
    │                  │                   │ executes (curl | installer)
    │                  │  POST result      │
    │                  │◀──────────────────│
    │                  │ status: completed │
    │◀─────────────────│                   │
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
  │ share URL ─────────────────────────────│ (Safari)
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
| Dashboard | Next.js (App Router) |
| Database | PostgreSQL 16 + SQLAlchemy 2.x async + asyncpg |
| Queue | AWS SQS (LocalStack for dev) |
| Push | Apple APNs HTTP/2 via httpx |
| Auth | JWT (dashboard) + mTLS (MDM endpoints) |
| Profiles | plistlib + cryptography (CMS signing) |
| Agent | Pure bash LaunchDaemon (no Python/Xcode dependency) |
| Infra | Docker Compose (dev) / AWS ECS Fargate (prod) |

---

## Prerequisites

- macOS (host) or Linux
- Docker Desktop
- Python 3.12+
- Node.js 18+ (for dashboard dev server)
- ngrok or reverse proxy for public HTTPS URL

---

## Quick Start (Local Dev)

### 1. Clone and configure

```bash
git clone <repo>
cd mdm-saas
cp .env.example .env
# Edit .env — set MDM_SERVER_URL to your ngrok/public HTTPS URL
```

### 2. Generate dev certificates

```bash
# Device identity cert for enrollment profile
bash scripts/gen_dev_certs.sh

# APNs push certificate — see APNs Setup section below
# Copy to: certs/dev/apns.pem + certs/dev/apns.key
```

### 3. Start services

```bash
# Start PostgreSQL + LocalStack + MDM app
docker compose up -d

# Run migrations
docker compose exec app alembic upgrade head

# Seed test tenant + admin user
docker compose exec app python scripts/seed_db.py
```

### 4. Start the dashboard

```bash
cd dashboard
npm install
npm run dev
# Dashboard at http://localhost:3000
```

### 5. Verify

```bash
curl -s https://<your-url>/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@acme.com","password":"secret"}'
# → {"access_token": "..."}
```

### 6. Enroll a device

1. In the dashboard go to **Enrollment** → generate a token
2. Open the enrollment URL in **Safari** on the Mac
3. Install the profile when prompted
4. Device appears in the dashboard as `enrolled`

---

## Key Endpoints

### Dashboard API (JWT auth)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/login` | Get JWT token |
| GET | `/api/v1/devices` | List enrolled devices |
| GET | `/api/v1/devices/{id}` | Device detail |
| POST | `/api/v1/devices/{id}/query` | Queue DeviceInformation |
| POST | `/api/v1/devices/{id}/lock` | Queue DeviceLock |
| POST | `/api/v1/devices/{id}/erase` | Queue EraseDevice |
| POST | `/api/v1/devices/{id}/restart` | Queue RestartDevice |
| GET | `/api/v1/devices/{id}/users` | List device users |
| GET | `/api/v1/devices/{id}/patch/apps` | Installed apps |
| GET | `/api/v1/devices/{id}/patch/updates` | Available OS updates |
| POST | `/api/v1/devices/{id}/patch/scan` | Trigger patch scan |
| POST | `/api/v1/devices/{id}/patch/install` | Install specific updates |
| POST | `/api/v1/enrollment/tokens` | Create enrollment token |
| GET | `/api/v1/enrollment/{token}` | Download enrollment profile |
| POST | `/api/v1/profiles/psso` | Push PSSO (Entra ID SSO) profile to all devices |
| POST | `/api/v1/profiles/usb-block/push` | Push USB block to all devices |
| POST | `/api/v1/profiles/usb-block/push/{device_id}` | Push USB block to one device |
| POST | `/api/v1/profiles/usb-block/remove/{device_id}` | Remove USB block from one device |
| POST | `/api/v1/profiles/gatekeeper/push` | Push Gatekeeper policy to all devices |
| GET | `/api/v1/packages` | List uploaded software packages |
| POST | `/api/v1/packages` | Upload a package (multipart) |
| GET | `/api/v1/packages/{id}/download` | Download package |
| GET | `/api/v1/compliance/summary` | Fleet compliance summary |
| GET | `/api/v1/compliance/policies` | List compliance policies |
| GET | `/api/v1/admin-access/requests` | List JIT admin access requests |
| POST | `/api/v1/admin-access/requests/{id}/approve` | Approve admin elevation |
| POST | `/api/v1/admin-access/requests/{id}/revoke` | Revoke admin access |
| GET | `/api/v1/audit` | Audit log |

### MDM Protocol (mTLS / device cert auth)

| Method | Path | Description |
|--------|------|-------------|
| PUT | `/mdm/apple/checkin` | Device check-in (Authenticate, TokenUpdate, CheckOut) |
| PUT | `/mdm/apple/connect` | Command delivery + result reporting |

### Management Agent

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/agent/bootstrap` | Bootstrap script (pipe to bash) |
| GET | `/api/v1/agent/jobs` | Poll pending jobs (agent token auth) |
| POST | `/api/v1/agent/jobs/{id}/result` | Submit job result |

### Self-Service Portal (agent token auth)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/portal` | Portal HTML page |
| GET | `/api/v1/portal/catalog` | Available software catalog |
| POST | `/api/v1/portal/software-requests` | Request software install |
| POST | `/api/v1/portal/admin-access` | Request temporary admin access |

---

## How It Works

### Multi-Tenancy
Every database query is scoped by `tenant_id`. Tenant is resolved from:
- **Dashboard API**: JWT claims (`sub` = user ID → `tenant_id`)
- **MDM endpoints**: `devices.udid` lookup → `tenant_id` (no JWT)

### Device Enrollment
1. Admin creates an enrollment token via dashboard
2. Token URL shared with user — opened in **Safari** on Mac
3. Signed `.mobileconfig` downloaded and installed
4. macOS sends `Authenticate` then `TokenUpdate` to `/mdm/apple/checkin`
5. Server stores APNs push token, device appears in dashboard as `enrolled`

### Command Delivery
1. Admin triggers action (lock/erase/profile push etc.)
2. `MdmCommand` record created with `status=queued`
3. SQS message queued → consumer sends APNs wake-up push
4. Device calls `PUT /mdm/apple/connect` → server returns command plist
5. Device executes → returns result → server marks `completed` or `failed`

### PSSO (Platform Single Sign-On)
Pushes `com.apple.extensiblesso` payload enabling macOS login with Microsoft Entra ID credentials. Uses Secure Enclave key (passwordless) or Password auth. Requires Microsoft Company Portal installed on device.

### USB Block Policy
- **macOS 12–13**: `com.apple.systemuiserver` with `mount-controls` (deny external disks)
- **macOS 14+**: `com.apple.security.diskaccess` with `DenyExternalStorage: true`
- Both payloads sent together for full coverage
- Uses deterministic `PayloadIdentifier` (`com.mdmsaas.usb.block.profile.{tenant_id}`) so `RemoveProfile` can target it reliably
- Per-device push and remove supported from device detail page

### Software Distribution
1. Admin uploads `.pkg` / `.dmg` / `.zip` to package library
2. Packages appear in self-service portal catalog
3. User requests installation → admin approves in dashboard
4. Management agent picks up job, runs install script, reports result
5. Status updates automatically (installing → completed / failed)

### JIT Admin Access
1. User requests temporary admin elevation from self-service portal
2. Admin approves with duration (1–24 hours)
3. Agent runs `dseditgroup` to add user to admin group
4. Auto-revoke worker checks every 60 seconds — removes access when `revoke_at` passes
5. Webhook notification sent on auto-revoke

### Management Agent
Pure-bash LaunchDaemon installed via:
```bash
curl -sSLG -d auth=<token> <bootstrap_url> | sudo bash
```
- Polls `/agent/jobs` every 30 seconds
- Commands delivered as base64-encoded strings (avoids shell quoting issues)
- Runs installs, scripts, dseditgroup, reports stdout/stderr + exit code
- No Python, Xcode, or other dependencies required

### Compliance Engine
Evaluates devices against policies with configurable rules:
- FileVault encryption required
- Firewall enabled
- Gatekeeper enforced
- PSSO registered
- Screen lock required
- Max check-in age
- Critical update threshold

---

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL async URL | `postgresql+asyncpg://mdm:mdm@db:5432/mdmdb` |
| `SECRET_KEY` | JWT signing key (256-bit hex) | `5b4875...` |
| `MDM_SERVER_URL` | Public HTTPS URL of MDM server | `https://your-ngrok-url.app` |
| `APNS_CERT_PATH` | APNs push certificate PEM | `./certs/dev/apns.pem` |
| `APNS_KEY_PATH` | APNs push private key | `./certs/dev/apns.key` |
| `APNS_USE_SANDBOX` | Use APNs sandbox | `false` |
| `APNS_PUSH_TOPIC` | APNs push topic from cert | `com.apple.mgmt.External.xxx` |
| `MDM_SIGNING_CERT_PATH` | Profile signing cert | `./certs/dev/mdm_signing.pem` |
| `MDM_SIGNING_KEY_PATH` | Profile signing key | `./certs/dev/mdm_signing.key` |
| `DEVICE_IDENTITY_P12_PATH` | Device identity PKCS#12 | `./certs/dev/device_identity.p12` |
| `SQS_COMMAND_QUEUE_URL` | SQS queue URL | `http://localstack:4566/.../mdm-commands` |
| `AWS_REGION` | AWS region | `ap-south-1` |
| `NOTIFICATION_WEBHOOK_URL` | Slack/Teams/Discord webhook | `https://hooks.slack.com/...` |
| `UPLOAD_DIR` | Package upload directory | `/app/uploads/packages` |

---

## Database Schema

```
tenants              users                devices
────────             ─────                ───────
id (PK)              id (PK)              id (PK)
slug                 tenant_id (FK)       tenant_id (FK)
name                 email                udid
apns_push_topic      hashed_password      serial_number / model
entra_tenant_id      role                 os_version / hostname
entra_client_id                           push_token / push_magic
                                          push_topic / status
enrollment_tokens    mdm_commands         psso_status
─────────────────    ────────────         compliance_status
id (PK)              id (PK)              enrolled_at / last_checkin
tenant_id (FK)       tenant_id (FK)
token                device_id (FK)       software_packages
platform             command_uuid         ─────────────────
reusable             command_type         id (PK)
expires_at           status               tenant_id (FK)
                     payload (JSONB)      name / version
profiles             result (JSONB)       filename / file_path
────────             queued_at            file_size / pkg_type
id (PK)              executed_at          uploaded_at
tenant_id (FK)
name / type          admin_access_requests
payload (JSONB)      ─────────────────────
                     id (PK)
device_users         device_id / device_user_id
────────────         status / reason
id (PK)              duration_hours
device_id (FK)       requested_at / revoke_at
short_name
is_admin             script_jobs (agent queue)
is_logged_in         ──────────────────────────
                     id (PK)
compliance_results   device_id (FK)
──────────────────   command (base64)
id (PK)              status / result
device_id / policy_id exit_code
status               created_at
passing / failing
```

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
8. Set `APNS_CERT_PATH`, `APNS_KEY_PATH`, `APNS_PUSH_TOPIC` in `.env`
9. Update `apns_push_topic` in `tenants` table with the UID from the cert

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
┌─────────────────┐     ┌─────────────────┐
│  ALB (HTTPS)    │────▶│  ECS Fargate    │
│  ACM cert       │     │  MDM App Tasks  │
└─────────────────┘     └────────┬────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼              ▼
             ┌──────────┐  ┌──────────┐  ┌──────────┐
             │  RDS     │  │  SQS     │  │ Secrets  │
             │ Postgres │  │ Commands │  │ Manager  │
             │ (Multi-AZ│  │  Queue   │  │ APNs Key │
             └──────────┘  └──────────┘  └──────────┘
                                  │
                           ┌──────▼──────┐
                           │  EFS Volume │
                           │  (uploads)  │
                           └─────────────┘
```

See `infra/terraform/` for full AWS infrastructure code.

---

## Production Limitations (Current Dev Setup)

| Issue | Dev Workaround | Production Fix |
|-------|---------------|----------------|
| ngrok URL changes on restart | Update `MDM_SERVER_URL` in `.env`, rebuild | Fixed domain via Route 53 |
| APNs push unreliable on VMs | `sudo /usr/libexec/mdmclient daemon` | Real Macs respond instantly |
| SQS consumer built into app | Runs in same process | Separate ECS task |
| Local file uploads | Docker volume mount | EFS / S3 |
| Single server | Docker Compose | ECS Fargate + RDS + SQS |

---

## Tested On

- macOS Sequoia 15.x (Apple Silicon — physical Mac and UTM VM)
- Apple APNs production endpoint (`api.push.apple.com`)
- mdmcert.download vendor signing
- Apple Push Certificates Portal (`identity.apple.com/pushcert`)
- Microsoft Entra ID PSSO with Company Portal
