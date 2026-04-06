"""
Compliance evaluation engine.

Evaluates devices against ISO 27001 and PCI DSS policy templates.
Called automatically on every device check-in and on-demand via API.
"""
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from app.db.models import Device, CompliancePolicy, ComplianceResult, DeviceUpdate
import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in policy templates
# ---------------------------------------------------------------------------

ISO27001_RULES = {
    "filevault_required": True,          # A.10.1 — encryption at rest
    "firewall_required": True,           # A.13.1 — network controls
    "gatekeeper_required": True,         # A.12.5 — software installation control
    "max_checkin_age_hours": 48,         # A.12.4 — monitoring
    "critical_updates_allowed": 0,       # A.12.6 — vulnerability management
    "psso_required": False,              # A.9.4 — SSO/MFA (optional until token available)
    "screen_lock_required": True,        # A.11.2 — clear screen policy
}

PCI_DSS_RULES = {
    "filevault_required": True,          # Req 3.5 — protect stored data
    "firewall_required": True,           # Req 1 — network security controls
    "gatekeeper_required": True,         # Req 5 — anti-malware / software integrity
    "max_checkin_age_hours": 24,         # Req 10 — log and monitor
    "critical_updates_allowed": 0,       # Req 6.3 — security vulnerabilities
    "psso_required": False,              # Req 8 — identify and authenticate
    "screen_lock_required": True,        # Req 8.2 — session management
}

FRAMEWORK_TEMPLATES = {
    "iso27001": {
        "name": "ISO 27001",
        "description": "ISO/IEC 27001 information security controls for endpoint devices",
        "rules": ISO27001_RULES,
    },
    "pci_dss": {
        "name": "PCI DSS v4",
        "description": "PCI DSS v4.0 endpoint security requirements",
        "rules": PCI_DSS_RULES,
    },
}

# Human-readable labels for each control
CONTROL_LABELS = {
    "filevault_required": "FileVault encryption enabled",
    "firewall_required": "Firewall enabled",
    "gatekeeper_required": "Gatekeeper enabled",
    "max_checkin_age_hours": "Device checked in recently",
    "critical_updates_allowed": "No critical updates pending",
    "psso_required": "Platform SSO configured",
    "screen_lock_required": "Screen lock enabled",
}


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

async def evaluate_device(
    device: Device,
    policy: CompliancePolicy,
    db: AsyncSession,
) -> ComplianceResult:
    """
    Evaluate a single device against a policy.
    Returns an upserted ComplianceResult (not yet committed).
    """
    rules = policy.rules
    passing = []
    failing = []
    unknown = []

    for control, required in rules.items():
        label = CONTROL_LABELS.get(control, control)

        if control == "filevault_required" and required:
            if device.is_encrypted is None:
                unknown.append(label)
            elif device.is_encrypted:
                passing.append(label)
            else:
                failing.append(label)

        elif control == "firewall_required" and required:
            if device.firewall_enabled is None:
                unknown.append(label)
            elif device.firewall_enabled:
                passing.append(label)
            else:
                failing.append(label)

        elif control == "gatekeeper_required" and required:
            if device.gatekeeper_enabled is None:
                unknown.append(label)
            elif device.gatekeeper_enabled:
                passing.append(label)
            else:
                failing.append(label)

        elif control == "screen_lock_required" and required:
            if device.screen_lock_enabled is None:
                unknown.append(label)
            elif device.screen_lock_enabled:
                passing.append(label)
            else:
                failing.append(label)

        elif control == "max_checkin_age_hours":
            if device.last_checkin is None:
                unknown.append(label)
            else:
                age_hours = (datetime.utcnow() - device.last_checkin).total_seconds() / 3600
                if age_hours <= required:
                    passing.append(label)
                else:
                    failing.append(label)

        elif control == "critical_updates_allowed":
            count_result = await db.execute(
                select(func.count()).select_from(DeviceUpdate)
                .where(DeviceUpdate.device_id == device.id, DeviceUpdate.is_critical == True)
            )
            critical_count = count_result.scalar() or 0
            if critical_count <= required:
                passing.append(label)
            else:
                failing.append(label)

        elif control == "psso_required" and required:
            if device.psso_status == "registered":
                passing.append(label)
            elif device.psso_status == "not_configured":
                failing.append(label)
            else:
                unknown.append(label)

    if failing:
        status = "non_compliant"
    elif unknown and not passing:
        status = "unknown"
    else:
        status = "compliant"

    # Upsert result
    existing = await db.execute(
        select(ComplianceResult)
        .where(ComplianceResult.device_id == device.id, ComplianceResult.policy_id == policy.id)
    )
    result = existing.scalar_one_or_none()
    if result:
        result.status = status
        result.passing = passing
        result.failing = failing
        result.unknown = unknown
        result.checked_at = datetime.utcnow()
    else:
        result = ComplianceResult(
            device_id=device.id,
            policy_id=policy.id,
            tenant_id=device.tenant_id,
            status=status,
            passing=passing,
            failing=failing,
            unknown=unknown,
        )
        db.add(result)

    log.info("Compliance %s device=%s policy=%s failing=%s",
             status, device.id, policy.name, failing)
    return result


async def evaluate_device_all_policies(device: Device, db: AsyncSession) -> None:
    """Run all active policies for the device's tenant on check-in."""
    policies_result = await db.execute(
        select(CompliancePolicy)
        .where(CompliancePolicy.tenant_id == device.tenant_id, CompliancePolicy.is_active == True)
    )
    policies = policies_result.scalars().all()
    if not policies:
        return

    any_failing = False
    for policy in policies:
        result = await evaluate_device(device, policy, db)
        if result.status == "non_compliant":
            any_failing = True

    new_compliance = "non_compliant" if any_failing else "compliant"
    await db.execute(
        update(Device).where(Device.id == device.id).values(
            compliance_status=new_compliance,
            compliance_checked_at=datetime.utcnow(),
        )
    )


async def seed_default_policies(tenant_id: str, db: AsyncSession) -> list[CompliancePolicy]:
    """
    Create ISO 27001 and PCI DSS policies for a tenant if they don't exist yet.
    Called when tenant first accesses the compliance API.
    """
    created = []
    for framework, tmpl in FRAMEWORK_TEMPLATES.items():
        existing = await db.execute(
            select(CompliancePolicy)
            .where(CompliancePolicy.tenant_id == tenant_id, CompliancePolicy.framework == framework)
        )
        if existing.scalars().first():
            continue
        policy = CompliancePolicy(
            tenant_id=tenant_id,
            name=tmpl["name"],
            framework=framework,
            description=tmpl["description"],
            rules=tmpl["rules"],
        )
        db.add(policy)
        created.append(policy)
    return created
