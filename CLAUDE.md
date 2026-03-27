# MDM SaaS — Claude Code Project Guide

## What this project is
A multi-tenant SaaS MDM (Mobile Device Management) server that manages Mac and Windows
devices. Key differentiator: built-in support for macOS Platform SSO (PSSO) with
Microsoft Entra ID.

## Repository layout
```
mdm-saas/
├── app/
│   ├── main.py                  # FastAPI app entry point
│   ├── core/
│   │   ├── config.py            # Settings (pydantic-settings)
│   │   ├── security.py          # JWT auth, mTLS cert validation
│   │   └── deps.py              # FastAPI dependency injection
│   ├── db/
│   │   ├── base.py              # SQLAlchemy async engine + session
│   │   ├── models.py            # ORM models (all tables)
│   │   └── migrations/          # Alembic migrations
│   ├── api/
│   │   └── routes/
│   │       ├── auth.py          # POST /auth/login, /auth/sso/entra
│   │       ├── tenant.py        # GET/PATCH /tenant, APNs + Entra config
│   │       ├── devices.py       # Device CRUD + remote actions
│   │       ├── enrollment.py    # Token generation, profile delivery
│   │       ├── profiles.py      # Config profiles + PSSO profile builder
│   │       └── audit.py         # Audit log query + export
│   ├── mdm/
│   │   ├── apple/
│   │   │   ├── checkin.py       # PUT /mdm/apple/checkin handler
│   │   │   ├── connect.py       # PUT /mdm/apple/connect handler
│   │   │   ├── plist.py         # Plist encode/decode helpers
│   │   │   ├── commands.py      # MDM command builders
│   │   │   ├── profiles.py      # .mobileconfig builder + signer
│   │   │   └── apns.py          # APNs HTTP/2 push sender
│   │   └── windows/
│   │       ├── omadm.py         # OMA-DM sync handler (Phase 2)
│   │       └── enrollment.py    # Windows MDM enrollment (Phase 2)
│   └── services/
│       ├── command_queue.py     # SQS consumer → APNs push worker
│       ├── psso.py              # PSSO profile generator + status tracker
│       └── audit.py             # Audit log writer middleware
├── tests/
│   ├── unit/
│   │   ├── test_plist.py        # Plist parsing for all message types
│   │   ├── test_commands.py     # Command builder output validation
│   │   ├── test_profiles.py     # .mobileconfig XML structure tests
│   │   └── test_psso.py         # PSSO payload builder tests
│   └── integration/
│       ├── test_checkin.py      # Full checkin HTTP flow (httpx TestClient)
│       ├── test_connect.py      # Connect + command delivery flow
│       └── test_enrollment.py   # Token → profile → checkin cycle
├── infra/terraform/             # AWS infra (ECS, RDS, SQS, Secrets Manager)
├── scripts/
│   ├── gen_dev_certs.sh         # Generate dev MDM signing certs (openssl)
│   └── seed_db.py               # Seed a test tenant + device
├── .env.example
├── docker-compose.yml           # Local dev: app + postgres + localstack
├── Dockerfile
└── pyproject.toml
```

## Tech stack
- Python 3.12
- FastAPI (async) + uvicorn
- SQLAlchemy 2.x async + asyncpg (PostgreSQL)
- plistlib (stdlib) for plist parsing — binary plist via biplist if needed
- httpx (async) for APNs HTTP/2 provider API
- boto3 for SQS and Secrets Manager
- pydantic-settings for config
- cryptography for cert/plist signing
- pytest + pytest-asyncio + httpx for tests
- Alembic for DB migrations

## Critical multi-tenancy rules
1. EVERY database query MUST include `WHERE tenant_id = :tenant_id`
2. tenant_id is ALWAYS resolved from the JWT (dashboard API) or device UDID
   lookup (MDM endpoints) — NEVER from URL params or request body
3. MDM device endpoints (/mdm/apple/*) use mTLS — no JWT
   Tenant resolution: `SELECT tenant_id FROM devices WHERE udid = $1`
4. Never log raw plist bodies — they may contain device tokens (PII)

## Apple MDM protocol — key facts
- Check-in URL: PUT /mdm/apple/checkin  (device cert auth via mTLS)
- Connect URL:  PUT /mdm/apple/connect  (device cert auth via mTLS)
- All bodies are XML plist (Content-Type: application/x-apple-aspen-config
  for profiles, application/x-www-form-urlencoded for commands)
- Checkin message types: Authenticate, TokenUpdate, CheckOut,
  UserAuthenticate, GetBootstrapToken, DeclarativeManagement
- Server response to Idle (no queued command): HTTP 200 with empty body
- Server response to queued command: HTTP 200 with plist command body
- Device ALWAYS sends result of previous command in the connect body
  alongside requesting next command

## APNs push flow
1. Server queues command in mdm_commands table (status=queued)
2. SQS message sent with {device_id, command_id}
3. SQS consumer (command_queue.py) picks it up
4. Sends APNs push to api.push.apple.com/3/device/{push_token}
   Headers: apns-push-type=mdm, apns-topic={push_topic}.voip NOT needed
   The MDM push topic ends in .mdmAPNSTopic from the device enrollment
5. APNs wakes device → device calls /mdm/apple/connect
6. Server returns queued command plist
7. Device executes, calls /mdm/apple/connect again with result
8. Server marks command status=completed or failed

## PSSO profile structure (critical for Entra ID login on Mac)
The PSSO config is delivered as an Extensible SSO payload inside a
.mobileconfig profile. Key fields:
- PayloadType: com.apple.extensiblesso
- ExtensionIdentifier: com.microsoft.CompanyPortalMac.ssoextension
- TeamIdentifier: UBF8T346G9
- Type: Credential
- Urls: [https://login.microsoftonline.com, https://login.microsoft.com,
         https://graph.microsoft.com]
- PlatformSSO.AuthenticationMethod: UserSecureEnclaveKey (or Password)
- PlatformSSO.EnableCreateUserAtLogin: true
- PlatformSSO.RegistrationToken: <from Entra>

## Key Apple documentation refs
- Check-in protocol: https://developer.apple.com/documentation/devicemanagement/check-in
- Commands: https://developer.apple.com/documentation/devicemanagement/commands_and_queries
- Profiles: https://developer.apple.com/documentation/devicemanagement/profile-specific_payload_keys
- PSSO integration guide: https://learn.microsoft.com/en-us/entra/identity/devices/macos-psso-integration-guide
- Apple device-management schema repo: https://github.com/apple/device-management

## NanoMDM (Go reference implementation)
Study these files for protocol details before implementing:
- https://github.com/micromdm/nanomdm/blob/main/mdm/mdm.go  (message structs)
- https://github.com/micromdm/nanomdm/blob/main/http/mdm/   (HTTP handlers)

## Environment variables (see .env.example)
- DATABASE_URL          asyncpg connection string
- SECRET_KEY            JWT signing key (256-bit)
- AWS_REGION            e.g. ap-south-1
- SQS_COMMAND_QUEUE_URL SQS queue URL for MDM commands
- APNS_CERT_SECRET_ARN  Secrets Manager ARN for APNs cert
- APNS_KEY_SECRET_ARN   Secrets Manager ARN for APNs private key
- MDM_SIGNING_CERT_PATH Path to MDM profile signing cert (local dev)
- ENVIRONMENT           development | staging | production

## Testing approach
- Unit tests: test plist parsing, command builders, profile XML output
  in isolation. No DB, no network. Use fixtures for sample plist bodies.
- Integration tests: use FastAPI TestClient + pytest-asyncio.
  Use a real PostgreSQL DB (Docker Compose) — not mocks.
  Test full HTTP flows: token → checkin → connect → command delivery.
- Real device testing: manual only. Requires physical Mac + dev certs.

## Common Claude Code tasks
When asked to implement a feature, always:
1. Write the implementation
2. Write unit tests for it
3. Run: pytest tests/unit/ -v
4. Fix any failures before reporting done

When modifying DB models, always:
1. Update app/db/models.py
2. Generate migration: alembic revision --autogenerate -m "description"
3. Review the generated migration file before applying

## What NOT to implement yet (Phase 2)
- Windows OMA-DM (app/mdm/windows/) — stubs only
- Apple Business Manager (ABM) DEP integration
- Apps and Books (VPP) management
- Declarative Device Management (DDM)
Focus on: enrollment → checkin → connect → PSSO profile push → audit log
