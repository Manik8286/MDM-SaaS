# MDM SaaS — Troubleshooting Guide

---

## Table of Contents

1. [Enrollment Issues](#1-enrollment-issues)
2. [APNs Push Issues](#2-apns-push-issues)
3. [MDM Commands Not Executing](#3-mdm-commands-not-executing)
4. [Profile Install / Remove Issues](#4-profile-install--remove-issues)
5. [PSSO Issues](#5-psso-issues)
6. [USB Block Policy Issues](#6-usb-block-policy-issues)
7. [Management Agent Issues](#7-management-agent-issues)
8. [Software Distribution Issues](#8-software-distribution-issues)
9. [JIT Admin Access Issues](#9-jit-admin-access-issues)
10. [Dashboard / API Issues](#10-dashboard--api-issues)
11. [Database Issues](#11-database-issues)
12. [Docker / Infrastructure Issues](#12-docker--infrastructure-issues)
13. [macOS Terminal / Shell Issues](#13-macos-terminal--shell-issues)
14. [Useful Diagnostic Commands](#14-useful-diagnostic-commands)

---

## 1. Enrollment Issues

### Device doesn't appear after installing the enrollment profile

**Symptoms:** Profile installs on Mac, no error, but device never shows as `enrolled` in dashboard.

**Causes & Fixes:**

1. **Wrong MDM_SERVER_URL** — the device cannot reach the server.
   ```bash
   # Check what URL is in the enrollment profile
   sudo profiles list -verbose | grep Server
   # Must be reachable from the device — test with:
   curl -v https://<your-mdm-url>/api/v1/healthz
   ```

2. **ngrok URL changed** — if using ngrok, the URL changes on restart.
   - Update `MDM_SERVER_URL` in `.env`
   - Restart the app: `docker compose restart app`
   - Generate a new enrollment token (old profiles point to the old URL)

3. **Profile not trusted by macOS** — self-signed cert not trusted.
   - Install the mkcert CA: `mkcert -install`
   - Or use a publicly trusted cert (ngrok provides one automatically)

4. **Check checkin logs:**
   ```bash
   docker compose logs app | grep -i "checkin\|authenticate\|tokenupdate"
   ```

---

### Enrollment URL opens blank page in Safari

The enrollment endpoint returns a `.mobileconfig` file. If Safari shows blank:
- The URL must be opened in **Safari**, not Chrome or Firefox
- Check the Content-Type header: must be `application/x-apple-aspen-config`
- Verify the profile is valid XML: `curl -sk <url> | head -5`

---

### "Profile installation failed" on macOS

1. **Unsigned profile** — macOS 13+ requires signed profiles for supervised devices.
   - Check `MDM_SIGNING_CERT_PATH` and `MDM_SIGNING_KEY_PATH` are set and files exist.

2. **Expired enrollment token**
   ```bash
   docker compose exec -T db psql -U mdm mdmdb -c \
     "SELECT token, expires_at, used FROM enrollment_tokens ORDER BY created_at DESC LIMIT 5;"
   ```
   Generate a new token if expired.

3. **Device already enrolled** — macOS won't install a second MDM profile.
   - Remove the existing MDM profile: System Settings → Privacy & Security → Profiles → Remove
   - Or unenroll via dashboard first.

---

## 2. APNs Push Issues

### Commands queued but device never wakes up

**Check 1: Does the device have a push token?**
```bash
docker compose exec -T db psql -U mdm mdmdb -c \
  "SELECT id, hostname, push_token IS NOT NULL as has_token, push_topic FROM devices;"
```
If `has_token = false`: the device completed `Authenticate` but not `TokenUpdate`. Re-enroll.

**Check 2: APNs cert validity**
```bash
openssl x509 -in ./certs/dev/apns.pem -noout -dates
# notAfter must be in the future
```
APNs certificates expire annually. Renew at identity.apple.com/pushcert.

**Check 3: APNs environment mismatch**
- Production cert → `APNS_USE_SANDBOX=false` (api.push.apple.com)
- Development cert → `APNS_USE_SANDBOX=true` (api.development.push.apple.com)

**Check 4: Push topic mismatch**
```bash
# Get topic from cert
openssl x509 -in ./certs/dev/apns.pem -noout -subject | grep -o 'UID=[^/]*'
# Compare with DB
docker compose exec -T db psql -U mdm mdmdb -c "SELECT apns_push_topic FROM tenants;"
```
They must match exactly.

**Check 5: VM/device APNs daemon**
On macOS VMs, APNs push may not wake the device reliably.
```bash
# Run on the Mac to manually trigger MDM check-in:
sudo /usr/libexec/mdmclient daemon
```

**Check app logs for APNs errors:**
```bash
docker compose logs app | grep -i "apns\|push"
```

---

### APNs push succeeds but device still doesn't respond

The device will pick up commands on the **next poll** even without APNs. Force a check-in:
```bash
# On the Mac:
sudo /usr/libexec/mdmclient daemon
```

Commands are queued in the DB — they won't be lost. The device will execute them when it next connects.

---

## 3. MDM Commands Not Executing

### Command stuck in `queued` status

```bash
docker compose exec -T db psql -U mdm mdmdb -c \
  "SELECT command_uuid, command_type, status, queued_at FROM mdm_commands \
   WHERE status='queued' ORDER BY queued_at DESC LIMIT 10;"
```

**Fix:** Manually trigger APNs push or run `sudo /usr/libexec/mdmclient daemon` on the device.

---

### Command stuck in `running` status

This means the device started executing but never returned a result (e.g. agent crashed mid-job).

```bash
# Reset stuck commands back to queued
docker compose exec -T db psql -U mdm mdmdb -c \
  "UPDATE mdm_commands SET status='queued' WHERE status='running' \
   AND queued_at < NOW() - INTERVAL '10 minutes';"
```

---

### Command shows `failed` with error

Check the result field:
```bash
docker compose exec -T db psql -U mdm mdmdb -c \
  "SELECT command_uuid, command_type, status, result \
   FROM mdm_commands WHERE status='failed' ORDER BY queued_at DESC LIMIT 5;"
```

Common failure reasons:
| Error | Cause | Fix |
|-------|-------|-----|
| `NotNow` | Device busy (updating, sleeping) | Retry — will re-queue automatically |
| `ManagedApplicationAlreadyInstalled` | App already installed | Expected — not a real failure |
| `ProfileNotFound` | RemoveProfile target doesn't exist | Profile already removed or wrong identifier |
| `AccessDenied` | Command requires supervised device | Supervise the device via ABM/ASM |

---

## 4. Profile Install / Remove Issues

### InstallProfile command completes but profile not on device

```bash
# Check installed profiles on Mac:
sudo profiles list
sudo profiles list -verbose
```

If the profile isn't there despite `completed` status, the device may have rejected it silently. Check macOS Console.app for MDM errors.

---

### RemoveProfile fails — "Profile is not removable"

This happens when `PayloadRemovalDisallowed: true` and you try to remove via `sudo profiles remove`.

**RemoveProfile must be sent as an MDM command:**
```bash
# Find the exact top-level PayloadIdentifier first:
sudo profiles list | grep Identifier

# Queue RemoveProfile via the API or directly:
docker compose exec -T app python3 - <<'EOF'
import asyncio, sys
sys.path.insert(0, '/app')
async def main():
    from app.db.base import AsyncSessionLocal
    from app.mdm.apple.commands import make_remove_profile_command
    async with AsyncSessionLocal() as db:
        cmd = make_remove_profile_command(
            "<device_id>", "<tenant_id>",
            "<exact-PayloadIdentifier-from-profiles-list>"
        )
        db.add(cmd)
        await db.commit()
        print(f"Queued: {cmd.command_uuid}")
asyncio.run(main())
EOF
```

---

### RemoveProfile command completes but profile still there

The identifier in the `RemoveProfile` command doesn't match the installed profile's `PayloadIdentifier`.

**Diagnose:**
```bash
# On the Mac — get exact identifier:
sudo profiles list | grep -A3 "USB\|Block\|mdmsaas"
```

The `PayloadIdentifier` in the `RemoveProfile` command must match the **top-level** identifier, not the inner payload identifiers.

For USB Block profiles deployed after the fix: identifier is `com.mdmsaas.usb.block.profile.{tenant_id}`.
For older profiles with random UUIDs: you must use the exact UUID shown in `sudo profiles list`.

---

### Profile has wrong PayloadIdentifier (old random UUID profiles)

For profiles installed before the deterministic-identifier fix, you need to manually queue removal:

```bash
# 1. Find the identifier on the Mac:
sudo profiles list | grep Identifier

# 2. Decode from DB to confirm:
docker compose exec -T app python3 - <<'EOF'
import asyncio, sys, plistlib, base64
sys.path.insert(0, '/app')
async def main():
    from app.db.base import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        rows = await db.execute(text("""
            SELECT command_uuid, queued_at, payload
            FROM mdm_commands
            WHERE device_id = '<device_id>' AND command_type = 'InstallProfile'
            ORDER BY queued_at DESC LIMIT 5
        """))
        for row in rows:
            raw = row.payload.get("Payload", "")
            if raw:
                p = plistlib.loads(base64.b64decode(raw))
                print(f"{row.queued_at} → {p.get('PayloadIdentifier')}")
asyncio.run(main())
EOF
```

---

## 5. PSSO Issues

### PSSO profile installed but login screen still shows local password

1. **Microsoft Company Portal not installed** — required for the SSO extension.
   Install from the Mac App Store or deploy via software distribution.

2. **Device not registered with Entra** — PSSO requires device registration.
   - Open Company Portal → sign in with Entra credentials → complete device registration
   - Check registration status: `app-sso -s com.microsoft.CompanyPortalMac.ssoextension`

3. **Wrong Entra tenant ID / client ID**
   - Verify in tenant settings in the dashboard
   - Cross-check with Azure Portal → App Registrations

4. **PSSO requires macOS 13+**
   ```bash
   sw_vers -productVersion  # must be 13.0 or higher
   ```

---

### PSSO registration token expired

Registration tokens from Entra are time-limited. Generate a new one:
- Azure Portal → Devices → macOS PSSO → Generate token
- Push new PSSO profile from Policies page with updated token

---

## 6. USB Block Policy Issues

### USB block profile installed but USB drive still mounts

1. **Device not supervised** — `com.apple.security.diskaccess` (macOS 14+) requires supervision for silent blocking. On unsupervised devices macOS shows a dismissable dialog.
   ```bash
   # Check supervision status on Mac:
   sudo profiles status -type enrollment
   # or from dashboard: device detail → "Is Supervised"
   ```

2. **Restart required** — USB block takes effect after the first restart after profile install.
   ```bash
   # Restart the device via dashboard or:
   sudo shutdown -r now
   ```

3. **Wrong macOS version coverage** — verify both payloads are in the profile:
   ```bash
   sudo profiles list -verbose | grep -A20 "USB"
   # Should show both com.apple.systemuiserver and com.apple.security.diskaccess payloads
   ```

4. **USB-C adapter vs native USB** — some USB-C hubs are classified differently. Test with a direct USB-A/USB-C drive.

---

### "Push USB Block" button returns error

**Route conflict** — if you see `422 Unprocessable Entity` or `invalid UUID 'usb-block'`:
- The `/usb-block/push` route may be matched by `/{profile_id}/push` before FastAPI reaches the specific route.
- Specific routes must be defined **before** parameterized routes in `profiles.py`.

---

### "Remove USB Block" doesn't work after push

Old profiles installed before the deterministic-identifier fix have random `PayloadIdentifier` UUIDs. The remove command won't find them.

**Fix:**
1. Check current profiles on device: `sudo profiles list`
2. If you see `com.mdmsaas.profile.<random-uuid>`, queue a manual RemoveProfile with that exact identifier (see [RemoveProfile fails](#removeprofile-fails--profile-is-not-removable) above).
3. New pushes after the fix use `com.mdmsaas.usb.block.profile.{tenant_id}` — remove will work correctly.

---

## 7. Management Agent Issues

### Bootstrap command shows `dquote>` prompt

**Cause:** macOS/zsh smart quotes convert `"` → `"` `"` which breaks the shell command.

**Fix:** Use `-G -d` to pass the auth token as a query parameter — no quoting needed:
```bash
curl -sSLG -d auth=<YOUR_TOKEN> <BOOTSTRAP_URL> | sudo bash
```
Do **not** wrap the URL or token in quotes when typing in Terminal.

---

### Bootstrap runs but shows Xcode/Python errors

Old version of `mdm_agent.sh` is cached in the Docker image. Rebuild:
```bash
docker compose build app --no-cache
docker compose up -d app
```

---

### Agent starts but `curl exit 56` in logs

**Cause:** ngrok browser warning interstitial is intercepting the request.

**Fix:** The agent must include the `ngrok-skip-browser-warning: 1` header. Check `scripts/mdm_agent.sh` includes:
```bash
-H "ngrok-skip-browser-warning: 1"
```
If the header is missing, re-bootstrap after rebuilding the container.

---

### Agent shows `HTTP 401 Invalid agent token`

**Cause:** The agent parsed the wrong JSON field from the bootstrap response.

**Diagnose:**
```bash
# On the Mac, check what the agent stored:
sudo cat /etc/mdm-agent/config
# or check the LaunchDaemon env:
sudo launchctl print system/com.mdmsaas.agent
```

**Fix:** Re-run the bootstrap command with the correct `auth` token:
```bash
curl -sSLG -d auth=<CORRECT_TOKEN> <BOOTSTRAP_URL> | sudo bash
```

To get a valid agent token:
- Dashboard → Device detail → Agent Bootstrap section → copy the token

---

### Agent runs but job command is the job ID, not the actual command

**Cause:** Old agent version before base64 command encoding fix.

**Fix:** Rebuild the container and re-bootstrap:
```bash
docker compose build app --no-cache && docker compose up -d app
# Then on the Mac:
curl -sSLG -d auth=<token> <url> | sudo bash
```

---

### Jobs stuck in `running` state

Old agent runs marked jobs as running but crashed before completing.

```bash
# Reset stuck jobs to pending:
docker compose exec -T db psql -U mdm mdmdb -c \
  "UPDATE script_jobs SET status='pending' \
   WHERE status='running' AND created_at < NOW() - INTERVAL '10 minutes';"
```

---

### Agent installed but not polling

```bash
# Check LaunchDaemon status on Mac:
sudo launchctl list | grep mdmsaas

# Check agent log:
tail -50 /var/log/mdm-agent.log

# Restart agent:
sudo launchctl unload /Library/LaunchDaemons/com.mdmsaas.agent.plist
sudo launchctl load /Library/LaunchDaemons/com.mdmsaas.agent.plist
```

---

## 8. Software Distribution Issues

### Package upload fails ("Failed to fetch")

1. **File size too large** — default nginx/reverse proxy limits may be lower than 4 GB.
   Check your Caddy/nginx config for `request_body` / `client_max_body_size`.

2. **Upload directory permissions**
   ```bash
   docker compose exec app ls -la /app/uploads/
   # Must be writable by the app user
   # Fix:
   docker compose exec app chown -R app:app /app/uploads
   ```

3. **Volume not mounted** — check `docker-compose.yml` has the uploads volume:
   ```yaml
   volumes:
     - uploads:/app/uploads
   ```
   And the service mounts it:
   ```yaml
   app:
     volumes:
       - uploads:/app/uploads
   ```

---

### Software install job fails (exit_code=1)

Check the job result for details:
```bash
docker compose exec -T db psql -U mdm mdmdb -c \
  "SELECT id, command, status, exit_code, result FROM script_jobs \
   WHERE status='failed' ORDER BY created_at DESC LIMIT 5;"
```

Common causes:
| Exit code | Cause | Fix |
|-----------|-------|-----|
| 1 | Wrong download URL or installer path | Verify the URL is reachable from the Mac |
| 2 | Package signature rejected by Gatekeeper | Use a signed/notarized package |
| 126 | Permission denied running installer | Script must run as root (bootstrap with sudo) |
| 127 | Command not found | Check installer path / hdiutil available |

**For `.dmg` packages** — the install script must mount the DMG and copy the `.app`:
```bash
hdiutil attach "/tmp/app.dmg" -nobrowse -quiet -mountpoint /tmp/mnt
cp -R /tmp/mnt/*.app /Applications/
hdiutil detach /tmp/mnt -quiet
```

**For `.pkg` packages:**
```bash
sudo installer -pkg "/tmp/package.pkg" -target /
```

---

### Self-service portal shows blank catalog

1. No packages uploaded yet — upload via dashboard → Software Packages
2. Check the portal token is valid:
   ```bash
   # Get a fresh agent token from dashboard → Device detail → Agent section
   ```
3. Check API response:
   ```bash
   curl -H "Authorization: Bearer <agent_token>" <server>/api/v1/portal/catalog
   ```

---

## 9. JIT Admin Access Issues

### User elevated but auto-revoke didn't fire

1. **Auto-revoke worker not running** — check app startup logs:
   ```bash
   docker compose logs app | grep -i "auto.revoke\|revoke"
   ```

2. **Clock skew** — server and device clocks differ significantly.
   ```bash
   date  # on Mac
   docker compose exec app date  # on server
   ```

3. **Check pending revocations:**
   ```bash
   docker compose exec -T db psql -U mdm mdmdb -c \
     "SELECT id, status, revoke_at, revoked_at FROM admin_access_requests \
      WHERE status='approved' AND revoke_at < NOW();"
   ```
   If rows appear here, the worker should have caught them. Restart the app.

---

### dseditgroup command fails

```bash
# On the Mac, test manually:
sudo dseditgroup -o edit -a <username> -t user admin
# Common error: "Record was not found" — username may differ from display name
# Get correct short name:
dscl . list /Users | grep -v "^_"
```

---

### User shows as admin but IsCurrentlyAdmin returns false

The `UserList` MDM command caches results. Queue a refresh:
- Dashboard → Device detail → Users tab → Refresh Users

---

## 10. Dashboard / API Issues

### Dashboard shows "Failed to fetch" for all API calls

1. **API URL misconfigured** — open dashboard Settings and verify the API URL.
2. **CORS error** — check browser console for CORS policy errors. The API must be reachable from the browser's origin.
3. **Token expired** — log out and log in again.

---

### Login returns 401

```bash
# Check user exists:
docker compose exec -T db psql -U mdm mdmdb -c \
  "SELECT email, role, is_active FROM users;"

# Reset password if needed:
docker compose exec -T app python3 -c "
from app.core.security import hash_password
print(hash_password('newpassword'))
"
# Then update in DB:
docker compose exec -T db psql -U mdm mdmdb -c \
  "UPDATE users SET hashed_password='<hash>' WHERE email='admin@example.com';"
```

---

### API returns 422 Unprocessable Entity

The request body doesn't match the expected schema. Check:
- `Content-Type: application/json` header is set
- Body is valid JSON
- All required fields are present

---

### API returns 500 Internal Server Error

Check app logs:
```bash
docker compose logs app --tail=50 | grep -i "error\|exception\|traceback"
```

---

## 11. Database Issues

### Alembic migration fails

```bash
# Check current migration state:
docker compose exec app alembic current

# Check migration history:
docker compose exec app alembic history

# If DB is ahead of migrations (manual schema changes):
docker compose exec app alembic stamp head

# Force to specific revision:
docker compose exec app alembic stamp <revision_id>
```

---

### "relation does not exist" error

The migration hasn't been applied:
```bash
docker compose exec app alembic upgrade head
```

---

### Database connection refused

```bash
# Check DB is running:
docker compose ps db

# Check connection:
docker compose exec -T db psql -U mdm mdmdb -c "SELECT 1;"

# Check DATABASE_URL in .env matches docker-compose service name:
# Should be: postgresql+asyncpg://mdm:mdm@db:5432/mdmdb
```

---

## 12. Docker / Infrastructure Issues

### Container exits immediately on start

```bash
docker compose logs app
# Common causes:
# - Missing environment variable
# - Database not ready yet (add depends_on healthcheck)
# - Port already in use
```

---

### Changes to Python code not reflected

The app container needs a restart to pick up code changes (it's not hot-reloading):
```bash
docker compose restart app
```

For Next.js dashboard — it hot-reloads automatically when running `npm run dev`.

---

### Port 8000 already in use

```bash
lsof -i :8000
# Kill the process or change the port in docker-compose.yml
```

---

### LocalStack SQS not working

```bash
# Check LocalStack is running:
docker compose ps localstack

# Test queue:
aws --endpoint-url=http://localhost:4566 sqs list-queues --region ap-south-1

# Recreate queue if missing:
aws --endpoint-url=http://localhost:4566 sqs create-queue \
  --queue-name mdm-commands --region ap-south-1
```

---

## 13. macOS Terminal / Shell Issues

### Command shows `dquote>` or `quote>` after pressing Enter

macOS Terminal with zsh converts typed `"` and `'` into smart quotes (`"` `"` `'` `'`) which the shell can't parse.

**Solutions:**
1. Use `-G -d param=value` syntax instead of quoting in URLs
2. Paste commands into a plain text editor first to strip smart quotes
3. Use iTerm2 instead of Terminal.app (fewer smart quote issues)
4. Disable smart quotes: System Settings → Keyboard → Text Input → uncheck "Use smart quotes"

---

### `zsh: no matches found` with `?` in URL

zsh treats `?` in unquoted strings as a glob wildcard.

**Wrong:**
```bash
curl https://example.com/api?auth=token   # zsh tries to glob this
```

**Right:**
```bash
curl -G -d auth=token https://example.com/api   # curl appends ?auth=token
# or quote the entire URL:
curl "https://example.com/api?auth=token"
```

---

### `curl: (56) Recv failure` from ngrok URL

ngrok shows a browser warning interstitial for non-browser clients. Pass the bypass header:
```bash
curl -H "ngrok-skip-browser-warning: 1" <url>
```

---

## 14. Useful Diagnostic Commands

### Check device status
```bash
docker compose exec -T db psql -U mdm mdmdb -c \
  "SELECT id, hostname, serial_number, os_version, status, last_checkin \
   FROM devices ORDER BY last_checkin DESC;"
```

### Check recent MDM commands
```bash
docker compose exec -T db psql -U mdm mdmdb -c \
  "SELECT command_uuid, command_type, status, queued_at, executed_at \
   FROM mdm_commands ORDER BY queued_at DESC LIMIT 20;"
```

### Check profiles on device (Mac)
```bash
sudo profiles list
sudo profiles list -verbose
```

### Check MDM enrollment status (Mac)
```bash
sudo profiles status -type enrollment
sudo /usr/libexec/mdmclient QueryDeviceInformation
```

### Force MDM check-in (Mac)
```bash
sudo /usr/libexec/mdmclient daemon
```

### Check agent status (Mac)
```bash
sudo launchctl list | grep mdmsaas
tail -100 /var/log/mdm-agent.log
```

### Check app logs live
```bash
docker compose logs app -f 2>/dev/null | grep -v warning
```

### Check SQS queue depth
```bash
aws --endpoint-url=http://localhost:4566 sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/mdm-commands \
  --attribute-names ApproximateNumberOfMessages
```

### Reset a specific command to retry
```bash
docker compose exec -T db psql -U mdm mdmdb -c \
  "UPDATE mdm_commands SET status='queued', executed_at=NULL \
   WHERE command_uuid='<uuid>';"
```

### Manually send APNs push to a device
```bash
docker compose exec -T app python3 - <<'EOF'
import asyncio, sys
sys.path.insert(0, '/app')
async def main():
    from app.db.base import AsyncSessionLocal
    from app.db.models import Device
    from app.mdm.apple.apns import send_mdm_push
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Device).where(Device.hostname.ilike('%<hostname>%')))
        device = result.scalar_one()
        await send_mdm_push(device.push_token, device.push_magic, device.push_topic)
        print(f"Push sent to {device.hostname}")
asyncio.run(main())
EOF
```

### Check tenant configuration
```bash
docker compose exec -T db psql -U mdm mdmdb -c \
  "SELECT id, name, slug, plan, status, apns_push_topic, \
          entra_tenant_id IS NOT NULL as has_entra \
   FROM tenants;"
```

---

*Last updated: April 2026*
