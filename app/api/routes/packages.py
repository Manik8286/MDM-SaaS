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
import tempfile
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, RedirectResponse
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

# file_path values for S3-backed packages are stored as "s3://<bucket>/<key>"
# so existing rows (local paths, no scheme) keep working after this is
# enabled — storage mode is a deployment setting, not a per-row choice.
_S3_PREFIX = "s3://"


def _upload_dir(tenant_id: str) -> pathlib.Path:
    d = UPLOAD_DIR / tenant_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _s3_client():
    import boto3
    return boto3.client("s3", region_name=settings.aws_region)


def _s3_key(tenant_id: str, safe_name: str) -> str:
    return f"packages/{tenant_id}/{safe_name}"


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

    pkg_id = uuid.uuid4().hex
    safe_name = f"{pkg_id}{suffix}"

    size = 0
    if settings.packages_s3_bucket:
        tmp = tempfile.NamedTemporaryFile(delete=False)
        try:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise HTTPException(status_code=413, detail="File too large (max 4 GB)")
                tmp.write(chunk)
            tmp.close()
            key = _s3_key(tenant.id, safe_name)
            _s3_client().upload_file(tmp.name, settings.packages_s3_bucket, key)
            file_path = f"{_S3_PREFIX}{settings.packages_s3_bucket}/{key}"
        finally:
            tmp.close()
            os.unlink(tmp.name)
    else:
        dest = _upload_dir(tenant.id) / safe_name
        with dest.open("wb") as f:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    dest.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="File too large (max 4 GB)")
                f.write(chunk)
        file_path = str(dest)

    pkg = SoftwarePackage(
        tenant_id=tenant.id,
        name=name,
        version=version or None,
        description=description or None,
        filename=file.filename,
        file_path=file_path,
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
    if pkg.file_path.startswith(_S3_PREFIX):
        bucket, _, key = pkg.file_path[len(_S3_PREFIX):].partition("/")
        _s3_client().delete_object(Bucket=bucket, Key=key)
    else:
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

    if pkg.file_path.startswith(_S3_PREFIX):
        bucket, _, key = pkg.file_path[len(_S3_PREFIX):].partition("/")
        url = _s3_client().generate_presigned_url(
            "get_object",
            Params={
                "Bucket": bucket,
                "Key": key,
                "ResponseContentDisposition": f'attachment; filename="{pkg.filename}"',
                "ResponseContentType": "application/octet-stream",
            },
            ExpiresIn=300,
        )
        return RedirectResponse(url)

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
