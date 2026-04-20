"""
Compliance policy API.

GET  /compliance/policies              — list policies (seeds defaults on first call)
POST /compliance/policies              — create custom policy
GET  /compliance/policies/{id}         — get policy + per-device results
PUT  /compliance/policies/{id}         — update policy rules
DELETE /compliance/policies/{id}       — delete policy
POST /compliance/policies/{id}/evaluate — re-evaluate all devices now
GET  /compliance/summary               — fleet-wide compliance summary
GET  /compliance/devices/{device_id}   — all policy results for one device
GET  /compliance/export                — CSV export of all compliance results
"""
import csv
import io
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.db.base import get_db
from app.db.models import Device, CompliancePolicy, ComplianceResult, Tenant
from app.core.deps import get_current_tenant
from app.services.compliance import evaluate_device, evaluate_device_all_policies, seed_default_policies
import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix="/compliance")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PolicyRules(BaseModel):
    filevault_required: bool = True
    firewall_required: bool = True
    gatekeeper_required: bool = True
    max_checkin_age_hours: int = 48
    critical_updates_allowed: int = 0
    psso_required: bool = False
    screen_lock_required: bool = True


class CreatePolicyRequest(BaseModel):
    name: str
    framework: str = "custom"
    description: str | None = None
    rules: PolicyRules


class UpdatePolicyRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    rules: PolicyRules | None = None
    is_active: bool | None = None


class PolicyResponse(BaseModel):
    id: str
    name: str
    framework: str
    description: str | None
    rules: dict
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ComplianceResultResponse(BaseModel):
    id: str
    device_id: str
    policy_id: str
    status: str
    passing: list
    failing: list
    unknown: list
    checked_at: datetime

    model_config = {"from_attributes": True}


class PolicyDetailResponse(BaseModel):
    id: str
    name: str
    framework: str
    description: str | None
    rules: dict
    is_active: bool
    created_at: datetime
    results: list[ComplianceResultResponse]

    model_config = {"from_attributes": True}


class DeviceComplianceSummary(BaseModel):
    device_id: str
    hostname: str | None
    serial_number: str | None
    overall_status: str
    policy_results: list[ComplianceResultResponse]


class FleetSummary(BaseModel):
    total_devices: int
    compliant: int
    non_compliant: int
    unknown: int
    policies: list[PolicyResponse]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/policies", response_model=list[PolicyResponse])
async def list_policies(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    # Seed ISO 27001 + PCI DSS defaults on first access
    new_policies = await seed_default_policies(tenant.id, db)
    if new_policies:
        await db.flush()

    result = await db.execute(
        select(CompliancePolicy)
        .where(CompliancePolicy.tenant_id == tenant.id)
        .order_by(CompliancePolicy.created_at)
    )
    return result.scalars().all()


@router.post("/policies", response_model=PolicyResponse, status_code=201)
async def create_policy(
    body: CreatePolicyRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    policy = CompliancePolicy(
        tenant_id=tenant.id,
        name=body.name,
        framework=body.framework,
        description=body.description,
        rules=body.rules.model_dump(),
    )
    db.add(policy)
    await db.flush()
    return policy


@router.get("/policies/{policy_id}", response_model=PolicyDetailResponse)
async def get_policy(
    policy_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CompliancePolicy)
        .where(CompliancePolicy.id == policy_id, CompliancePolicy.tenant_id == tenant.id)
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    results_q = await db.execute(
        select(ComplianceResult).where(ComplianceResult.policy_id == policy_id)
    )
    policy.results = results_q.scalars().all()
    return policy


@router.put("/policies/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: str,
    body: UpdatePolicyRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CompliancePolicy)
        .where(CompliancePolicy.id == policy_id, CompliancePolicy.tenant_id == tenant.id)
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    if body.name is not None:
        policy.name = body.name
    if body.description is not None:
        policy.description = body.description
    if body.rules is not None:
        policy.rules = body.rules.model_dump()
    if body.is_active is not None:
        policy.is_active = body.is_active
    return policy


@router.delete("/policies/{policy_id}", status_code=204)
async def delete_policy(
    policy_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CompliancePolicy)
        .where(CompliancePolicy.id == policy_id, CompliancePolicy.tenant_id == tenant.id)
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    await db.delete(policy)


@router.post("/policies/{policy_id}/evaluate", status_code=202)
async def evaluate_policy(
    policy_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CompliancePolicy)
        .where(CompliancePolicy.id == policy_id, CompliancePolicy.tenant_id == tenant.id)
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    devices_result = await db.execute(
        select(Device).where(Device.tenant_id == tenant.id, Device.status == "enrolled")
    )
    devices = devices_result.scalars().all()

    evaluated = 0
    for device in devices:
        await evaluate_device(device, policy, db)
        evaluated += 1

    return {"evaluated": evaluated, "policy": policy.name}


@router.get("/summary", response_model=FleetSummary)
async def fleet_summary(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    # Seed defaults if needed
    await seed_default_policies(tenant.id, db)
    await db.flush()

    devices_result = await db.execute(
        select(Device).where(Device.tenant_id == tenant.id, Device.status == "enrolled")
    )
    devices = devices_result.scalars().all()

    compliant = sum(1 for d in devices if d.compliance_status == "compliant")
    non_compliant = sum(1 for d in devices if d.compliance_status == "non_compliant")
    unknown = sum(1 for d in devices if d.compliance_status not in ("compliant", "non_compliant"))

    policies_result = await db.execute(
        select(CompliancePolicy).where(CompliancePolicy.tenant_id == tenant.id)
    )

    return FleetSummary(
        total_devices=len(devices),
        compliant=compliant,
        non_compliant=non_compliant,
        unknown=unknown,
        policies=policies_result.scalars().all(),
    )


@router.get("/export")
async def export_compliance_csv(
    policy_id: str | None = Query(None),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Stream a CSV of compliance results — one row per device × policy."""
    # Build query: join devices + policies + results
    q = (
        select(Device, CompliancePolicy, ComplianceResult)
        .join(ComplianceResult, ComplianceResult.device_id == Device.id)
        .join(CompliancePolicy, CompliancePolicy.id == ComplianceResult.policy_id)
        .where(Device.tenant_id == tenant.id, ComplianceResult.tenant_id == tenant.id)
    )
    if policy_id:
        q = q.where(CompliancePolicy.id == policy_id)
    result = await db.execute(q.order_by(Device.hostname, CompliancePolicy.name))
    rows = result.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "hostname", "serial_number", "platform", "os_version",
        "policy_name", "framework", "status",
        "passing_rules", "failing_rules", "unknown_rules", "checked_at",
    ])
    for device, policy, res in rows:
        writer.writerow([
            device.hostname or device.udid[:8],
            device.serial_number or "",
            device.platform,
            device.os_version or "",
            policy.name,
            policy.framework,
            res.status,
            "|".join(res.passing or []),
            "|".join(res.failing or []),
            "|".join(res.unknown or []),
            res.checked_at.isoformat() if res.checked_at else "",
        ])

    output.seek(0)
    filename = f"compliance_report_{tenant.slug}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/devices/{device_id}", response_model=DeviceComplianceSummary)
async def device_compliance(
    device_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    device_result = await db.execute(
        select(Device).where(Device.id == device_id, Device.tenant_id == tenant.id)
    )
    device = device_result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    results_result = await db.execute(
        select(ComplianceResult).where(
            ComplianceResult.device_id == device_id,
            ComplianceResult.tenant_id == tenant.id,
        )
    )
    results = results_result.scalars().all()

    return DeviceComplianceSummary(
        device_id=device.id,
        hostname=device.hostname,
        serial_number=device.serial_number,
        overall_status=device.compliance_status,
        policy_results=results,
    )
