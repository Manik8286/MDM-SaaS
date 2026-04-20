"""
Management Agent API.

The MDM agent (mdm_agent.py) running as a LaunchDaemon on enrolled Macs
authenticates with a per-device token and polls for pending script jobs.

GET  /agent/bootstrap/{device_id}   — returns a self-contained bash install script (JWT auth)
GET  /agent/jobs                    — poll for pending jobs (marks them running)
POST /agent/jobs/{job_id}/result    — report execution result
"""
import uuid as _uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from app.db.base import get_db
from app.db.models import Device, ScriptJob, Tenant, DeviceUser, new_uuid
from app.core.deps import get_current_tenant, get_current_user
from app.core.security import decode_token
from app.core.config import get_settings
import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix="/agent")
bearer = HTTPBearer()
settings = get_settings()


# ---------------------------------------------------------------------------
# Auth dependency — device authenticates via per-device agent_token
# ---------------------------------------------------------------------------

async def get_device_by_agent_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> Device:
    result = await db.execute(
        select(Device).where(Device.agent_token == credentials.credentials)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=401, detail="Invalid agent token")
    return device


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

import base64 as _base64

class AgentJobResponse(BaseModel):
    id: str
    command: str
    command_b64: str = ""
    label: str | None
    model_config = {"from_attributes": True}

    @classmethod
    def from_job(cls, job) -> "AgentJobResponse":
        return cls(
            id=job.id,
            command=job.command,
            command_b64=_base64.b64encode(job.command.encode()).decode(),
            label=job.label,
        )


class JobResultBody(BaseModel):
    exit_code: int
    stdout: str | None = None
    stderr: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/bootstrap/{device_id}", response_class=PlainTextResponse)
async def get_bootstrap_script(
    device_id: str,
    request: "Request",
    auth: str | None = Query(default=None, description="JWT token as query param (alternative to Bearer header)"),
    db: AsyncSession = Depends(get_db),
):
    # Accept JWT via ?auth= query param (no -H needed → avoids shell quote issues)
    # or fall back to Bearer header via standard deps
    from app.db.models import User
    from sqlalchemy import select as _select

    token_str = auth
    if not token_str:
        # Try Authorization header
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token_str = auth_header[7:]
    if not token_str:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        payload = decode_token(token_str)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(_select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="User not found")

    result = await db.execute(_select(Tenant).where(Tenant.id == user.tenant_id, Tenant.status == "active"))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=403, detail="Tenant not active")
    """
    Return a self-contained bash script that installs the MDM agent on a Mac.
    Admin runs: curl -sSL <url> -H "Authorization: Bearer <jwt>" | sudo bash
    No pkgbuild, no pkg file needed.
    """
    result = await db.execute(
        select(Device).where(Device.id == device_id, Device.tenant_id == tenant.id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Lazily generate agent token
    if not device.agent_token:
        token = str(_uuid.uuid4())
        await db.execute(
            update(Device).where(Device.id == device.id).values(agent_token=token)
        )
        await db.flush()
        device.agent_token = token

    # Use the URL the request came in on (ngrok, production domain, etc.)
    # so the agent config points to a reachable server, not localhost.
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    forwarded_host = request.headers.get("x-forwarded-host", "") or request.headers.get("host", "")
    if forwarded_proto and forwarded_host:
        server_url = f"{forwarded_proto}://{forwarded_host}"
    else:
        server_url = str(request.base_url).rstrip("/")
    agent_token = device.agent_token

    # Read the bash agent source to embed inline
    import pathlib
    agent_src_path = pathlib.Path(__file__).parent.parent.parent.parent / "scripts" / "mdm_agent.sh"
    agent_src = agent_src_path.read_text() if agent_src_path.exists() else ""

    script = f"""#!/bin/bash
# MDM Agent Bootstrap — device {device_id}
# Run as root: curl -sSL <url> -H "Authorization: Bearer <jwt>" | sudo bash
set -euo pipefail

echo "[MDM Agent] Installing..."

mkdir -p /Library/MDMAgent
mkdir -p /Library/LaunchDaemons

# Write bash agent (no Python/Xcode dependency)
cat > /Library/MDMAgent/agent.sh << 'AGENTEOF'
{agent_src}
AGENTEOF

# Write device config
cat > /Library/MDMAgent/config.json << 'CFGEOF'
{{"server_url": "{server_url}", "agent_token": "{agent_token}"}}
CFGEOF

# Write LaunchDaemon plist
cat > /Library/LaunchDaemons/com.mdmsaas.agent.plist << 'PLISTEOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.mdmsaas.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Library/MDMAgent/agent.sh</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>/var/log/mdm-agent.log</string>
    <key>StandardErrorPath</key><string>/var/log/mdm-agent.log</string>
    <key>ThrottleInterval</key><integer>30</integer>
</dict>
</plist>
PLISTEOF

# Set permissions
chown -R root:wheel /Library/MDMAgent
chmod 755 /Library/MDMAgent
chmod 755 /Library/MDMAgent/agent.sh
chmod 600 /Library/MDMAgent/config.json
chown root:wheel /Library/LaunchDaemons/com.mdmsaas.agent.plist
chmod 644 /Library/LaunchDaemons/com.mdmsaas.agent.plist

# Reload daemon (unload first in case reinstalling)
launchctl unload /Library/LaunchDaemons/com.mdmsaas.agent.plist 2>/dev/null || true
launchctl load /Library/LaunchDaemons/com.mdmsaas.agent.plist

echo "[MDM Agent] Installed. Logs: tail -f /var/log/mdm-agent.log"
"""
    return PlainTextResponse(content=script, media_type="text/plain")


@router.get("/jobs", response_model=list[AgentJobResponse])
async def poll_jobs(
    device: Device = Depends(get_device_by_agent_token),
    db: AsyncSession = Depends(get_db),
):
    """Return pending jobs and atomically mark them as running."""
    result = await db.execute(
        select(ScriptJob)
        .where(
            ScriptJob.device_id == device.id,
            ScriptJob.tenant_id == device.tenant_id,
            ScriptJob.status == "pending",
        )
        .with_for_update(skip_locked=True)
        .limit(10)
    )
    jobs = result.scalars().all()
    for job in jobs:
        job.status = "running"
    await db.flush()
    if jobs:
        log.info("Agent poll: %d jobs dispatched to device %s", len(jobs), device.id)
    return [AgentJobResponse.from_job(j) for j in jobs]


@router.post("/jobs/{job_id}/result")
async def post_job_result(
    job_id: str,
    body: JobResultBody,
    device: Device = Depends(get_device_by_agent_token),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScriptJob).where(
            ScriptJob.id == job_id,
            ScriptJob.device_id == device.id,
            ScriptJob.tenant_id == device.tenant_id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.status = "completed" if body.exit_code == 0 else "failed"
    job.exit_code = body.exit_code
    job.stdout = (body.stdout or "")[:65536]  # cap at 64KB
    job.stderr = (body.stderr or "")[:65536]
    job.completed_at = datetime.utcnow()

    log.info("Job %s label=%s exit_code=%d device=%s", job.id, job.label, body.exit_code, device.id)
    if body.exit_code != 0 and body.stderr:
        log.warning("Job %s stderr: %s", job.id, body.stderr[:500])

    return {"id": job.id, "status": job.status}


# ---------------------------------------------------------------------------
# Local user reporting — agent sends list of macOS local accounts each poll
# ---------------------------------------------------------------------------

class AgentUserEntry(BaseModel):
    short_name: str
    full_name: str | None = None
    is_admin: bool = False
    is_logged_in: bool = False
    has_secure_token: bool = False


@router.post("/users")
async def report_users(
    users: list[AgentUserEntry],
    device: Device = Depends(get_device_by_agent_token),
    db: AsyncSession = Depends(get_db),
):
    """
    Called by the agent each poll cycle with the list of local macOS users.
    Upserts DeviceUser records so the portal can match Entra logins to devices.
    """
    existing_result = await db.execute(
        select(DeviceUser).where(DeviceUser.device_id == device.id)
    )
    existing = {u.short_name: u for u in existing_result.scalars().all()}

    for entry in users:
        if entry.short_name in existing:
            u = existing[entry.short_name]
            u.full_name = entry.full_name or u.full_name
            u.is_admin = entry.is_admin
            u.is_logged_in = entry.is_logged_in
            u.has_secure_token = entry.has_secure_token
        else:
            db.add(DeviceUser(
                id=new_uuid(),
                tenant_id=device.tenant_id,
                device_id=device.id,
                short_name=entry.short_name,
                full_name=entry.full_name,
                is_admin=entry.is_admin,
                is_logged_in=entry.is_logged_in,
                has_secure_token=entry.has_secure_token,
            ))

    await db.commit()
    log.info("Agent user report: %d users on device %s", len(users), device.id)
    return {"synced": len(users)}
