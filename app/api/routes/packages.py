"""
Software Package Management.

Admins upload PKG/DMG installers. The agent downloads them using the agent token.

POST   /packages              — upload a package (multipart, JWT auth)
GET    /packages              — list packages (JWT auth)
DELETE /packages/{id}         — delete package (JWT auth)
GET    /packages/{id}/download — download file (agent-token OR JWT auth)
"""
import os
import pathlib
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.base import get_db
from app.db.models import SoftwarePackage, Device, Tenant
from app.core.deps import get_current_tenant, get_current_user
from app.core.config import get_settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/packages")
bearer = HTTPBearer(auto_error=False)
settings = get_settings()

UPLOAD_DIR = pathlib.Path("/app/uploads/packages")
ALLOWED_EXTENSIONS = {".pkg", ".dmg"}
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4 GB


def _upload_dir(tenant_id: str) -> pathlib.Path:
    d = UPLOAD_DIR / tenant_id
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@router.post("")
async def upload_package(
    name: str = Form(...),
    version: str = Form(default=""),
    description: str = Form(default=""),
    file: UploadFile = File(...),
    tenant: Tenant = Depends(get_current_tenant),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    suffix = pathlib.Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only .pkg and .dmg files are allowed")

    pkg_id = __import__("uuid").uuid4().hex
    safe_name = f"{pkg_id}{suffix}"
    dest = _upload_dir(tenant.id) / safe_name

    size = 0
    with dest.open("wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_FILE_SIZE:
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File too large (max 4 GB)")
            f.write(chunk)

    pkg = SoftwarePackage(
        tenant_id=tenant.id,
        name=name,
        version=version or None,
        description=description or None,
        filename=file.filename,
        file_path=str(dest),
        file_size=size,
        pkg_type=suffix.lstrip("."),
        uploaded_by_id=user.id,
    )
    db.add(pkg)
    await db.flush()
    log.info("Package uploaded: %s (%d bytes) tenant=%s", name, size, tenant.id)
    return _pkg_response(pkg)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@router.get("")
async def list_packages(
    tenant: Tenant = Depends(get_current_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SoftwarePackage)
        .where(SoftwarePackage.tenant_id == tenant.id)
        .order_by(SoftwarePackage.uploaded_at.desc())
    )
    return [_pkg_response(p) for p in result.scalars().all()]


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

@router.delete("/{pkg_id}", status_code=204)
async def delete_package(
    pkg_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SoftwarePackage).where(
            SoftwarePackage.id == pkg_id,
            SoftwarePackage.tenant_id == tenant.id,
        )
    )
    pkg = result.scalar_one_or_none()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    pathlib.Path(pkg.file_path).unlink(missing_ok=True)
    await db.delete(pkg)


# ---------------------------------------------------------------------------
# Download — accepts agent token OR JWT
# ---------------------------------------------------------------------------

@router.get("/{pkg_id}/download")
async def download_package(
    pkg_id: str,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials

    # Try agent token first
    device_result = await db.execute(select(Device).where(Device.agent_token == token))
    device = device_result.scalar_one_or_none()

    if device:
        tenant_id = device.tenant_id
    else:
        # Fall back to JWT
        from app.core.security import decode_token
        from app.db.models import User
        try:
            payload = decode_token(token)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid token")
        user_result = await db.execute(select(User).where(User.id == payload["sub"]))
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        tenant_id = user.tenant_id

    result = await db.execute(
        select(SoftwarePackage).where(
            SoftwarePackage.id == pkg_id,
            SoftwarePackage.tenant_id == tenant_id,
        )
    )
    pkg = result.scalar_one_or_none()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")

    path = pathlib.Path(pkg.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=str(path),
        filename=pkg.filename,
        media_type="application/octet-stream",
    )


def _pkg_response(pkg: SoftwarePackage) -> dict:
    return {
        "id": pkg.id,
        "name": pkg.name,
        "version": pkg.version,
        "description": pkg.description,
        "filename": pkg.filename,
        "file_size": pkg.file_size,
        "pkg_type": pkg.pkg_type,
        "uploaded_at": pkg.uploaded_at.isoformat() if pkg.uploaded_at else None,
    }
