import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, ForeignKey, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def new_uuid() -> str:
    return str(uuid.uuid4())


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default="starter")
    status: Mapped[str] = mapped_column(String(50), default="active")
    # APNs — stored as Secrets Manager ARNs in production
    apns_cert_arn: Mapped[str | None] = mapped_column(String(500))
    apns_key_arn: Mapped[str | None] = mapped_column(String(500))
    apns_push_topic: Mapped[str | None] = mapped_column(String(255))
    # Entra ID linkage
    entra_tenant_id: Mapped[str | None] = mapped_column(String(255))
    entra_client_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="tenant")
    devices: Mapped[list["Device"]] = relationship(back_populates="tenant")
    profiles: Mapped[list["Profile"]] = relationship(back_populates="tenant")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="admin")
    status: Mapped[str] = mapped_column(String(50), default="active")
    last_login: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # TOTP 2FA
    totp_secret: Mapped[str | None] = mapped_column(String(64))   # base32 TOTP secret
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    tenant: Mapped["Tenant"] = relationship(back_populates="users")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    udid: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(20), default="macos")  # macos | windows
    serial_number: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(255))
    os_version: Mapped[str | None] = mapped_column(String(100))
    hostname: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="enrolled")
    enroll_type: Mapped[str] = mapped_column(String(50), default="manual")
    assigned_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    # APNs tokens (from TokenUpdate checkin)
    push_token: Mapped[str | None] = mapped_column(Text)
    push_magic: Mapped[str | None] = mapped_column(String(255))
    push_topic: Mapped[str | None] = mapped_column(String(255))
    unlock_token: Mapped[str | None] = mapped_column(Text)
    # PSSO state
    psso_status: Mapped[str] = mapped_column(String(50), default="not_configured")
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_checkin: Mapped[datetime | None] = mapped_column(DateTime)
    # Security / compliance fields (populated from DeviceInformation)
    is_encrypted: Mapped[bool | None] = mapped_column(Boolean)
    is_supervised: Mapped[bool | None] = mapped_column(Boolean)
    firewall_enabled: Mapped[bool | None] = mapped_column(Boolean)
    gatekeeper_enabled: Mapped[bool | None] = mapped_column(Boolean)
    screen_lock_enabled: Mapped[bool | None] = mapped_column(Boolean)
    # Compliance
    compliance_status: Mapped[str] = mapped_column(String(50), default="unknown")
    compliance_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Management agent token (per-device, used by mdm_agent.py)
    agent_token: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="devices")
    commands: Mapped[list["MdmCommand"]] = relationship(back_populates="device")
    installed_apps: Mapped[list["InstalledApp"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    available_updates: Mapped[list["DeviceUpdate"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    device_users: Mapped[list["DeviceUser"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    script_jobs: Mapped[list["ScriptJob"]] = relationship(back_populates="device", cascade="all, delete-orphan")


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(100))  # extensiblesso | wifi | vpn | custom
    platform: Mapped[str] = mapped_column(String(20), default="macos")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    signed_xml: Mapped[str | None] = mapped_column(Text)  # cached signed .mobileconfig
    status: Mapped[str] = mapped_column(String(50), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    tenant: Mapped["Tenant"] = relationship(back_populates="profiles")
    assignments: Mapped[list["ProfileAssignment"]] = relationship(back_populates="profile")


class ProfileAssignment(Base):
    __tablename__ = "profile_assignments"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    profile_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("profiles.id"), nullable=False)
    target_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50))  # device | group
    assigned_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    profile: Mapped["Profile"] = relationship(back_populates="assignments")


class MdmCommand(Base):
    __tablename__ = "mdm_commands"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    device_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("devices.id"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    command_uuid: Mapped[str] = mapped_column(String(255), unique=True, default=new_uuid)
    command_type: Mapped[str] = mapped_column(String(100))  # InstallProfile | DeviceLock | etc.
    status: Mapped[str] = mapped_column(String(50), default="queued")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB)
    queued_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    executed_at: Mapped[datetime | None] = mapped_column(DateTime)

    device: Mapped["Device"] = relationship(back_populates="commands")


class EnrollmentToken(Base):
    __tablename__ = "enrollment_tokens"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(20), default="macos")
    enroll_type: Mapped[str] = mapped_column(String(50), default="manual")
    reusable: Mapped[bool] = mapped_column(Boolean, default=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    changes: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class InstalledApp(Base):
    __tablename__ = "installed_apps"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    device_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    bundle_id: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[str | None] = mapped_column(String(100))
    short_version: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str | None] = mapped_column(String(100))  # AppStore | Unknown
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    device: Mapped["Device"] = relationship(back_populates="installed_apps")


class DeviceUser(Base):
    __tablename__ = "device_users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    device_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    user_guid: Mapped[str | None] = mapped_column(String(255))
    short_name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_logged_in: Mapped[bool] = mapped_column(Boolean, default=False)
    has_secure_token: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    device: Mapped["Device"] = relationship(back_populates="device_users")


class DeviceUpdate(Base):
    __tablename__ = "device_updates"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    device_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    product_key: Mapped[str] = mapped_column(String(255), nullable=False)
    human_readable_name: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[str | None] = mapped_column(String(100))
    build: Mapped[str | None] = mapped_column(String(50))
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    is_config_data_only: Mapped[bool] = mapped_column(Boolean, default=False)
    restart_required: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_url: Mapped[str | None] = mapped_column(Text)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    device: Mapped["Device"] = relationship(back_populates="available_updates")


class AdminAccessRequest(Base):
    __tablename__ = "admin_access_requests"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("devices.id"), nullable=False, index=True)
    device_user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("device_users.id"), nullable=False)
    requested_by_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    approved_by_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending|approved|denied|revoked|expired
    reason: Mapped[str | None] = mapped_column(Text)
    duration_hours: Mapped[int] = mapped_column(Integer, default=1)
    requested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoke_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)

    device: Mapped["Device"] = relationship(foreign_keys=[device_id])
    device_user: Mapped["DeviceUser"] = relationship(foreign_keys=[device_user_id])
    requested_by: Mapped["User"] = relationship(foreign_keys=[requested_by_id])
    approved_by: Mapped["User | None"] = relationship(foreign_keys=[approved_by_id])


class CompliancePolicy(Base):
    __tablename__ = "compliance_policies"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    framework: Mapped[str] = mapped_column(String(50), default="custom")  # iso27001 | pci_dss | custom
    description: Mapped[str | None] = mapped_column(Text)
    rules: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    results: Mapped[list["ComplianceResult"]] = relationship(back_populates="policy", cascade="all, delete-orphan")


class ComplianceResult(Base):
    __tablename__ = "compliance_results"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    device_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("compliance_policies.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="unknown")  # compliant | non_compliant | unknown
    passing: Mapped[list] = mapped_column(JSONB, default=list)
    failing: Mapped[list] = mapped_column(JSONB, default=list)
    unknown: Mapped[list] = mapped_column(JSONB, default=list)
    checked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    policy: Mapped["CompliancePolicy"] = relationship(back_populates="results")


class ScriptJob(Base):
    __tablename__ = "script_jobs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("devices.id"), nullable=False, index=True)
    command: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)  # pending|running|completed|failed
    exit_code: Mapped[int | None] = mapped_column(Integer)
    stdout: Mapped[str | None] = mapped_column(Text)
    stderr: Mapped[str | None] = mapped_column(Text)
    queued_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))

    device: Mapped["Device"] = relationship(back_populates="script_jobs", foreign_keys=[device_id])


class SoftwarePackage(Base):
    __tablename__ = "software_packages"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer)
    pkg_type: Mapped[str] = mapped_column(String(10), default="pkg")  # pkg | dmg
    uploaded_by_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SoftwareRequest(Base):
    __tablename__ = "software_requests"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("devices.id"), nullable=False, index=True)
    requester_name: Mapped[str] = mapped_column(String(255), nullable=False)  # local username
    software_name: Mapped[str] = mapped_column(String(255), nullable=False)
    software_pkg_url: Mapped[str | None] = mapped_column(Text)  # direct .pkg download URL
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)  # pending|approved|rejected|installing|completed|failed
    reviewed_by_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    script_job_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("script_jobs.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    device: Mapped["Device"] = relationship(foreign_keys=[device_id])


class RevokedToken(Base):
    """JWT blocklist — one row per logged-out token, cleaned up after expiry."""
    __tablename__ = "revoked_tokens"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DeviceGroup(Base):
    __tablename__ = "device_groups"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str] = mapped_column(String(20), default="#6366f1")  # UI badge color
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    members: Mapped[list["DeviceGroupMember"]] = relationship(back_populates="group", cascade="all, delete-orphan")


class DeviceGroupMember(Base):
    __tablename__ = "device_group_members"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    group_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("device_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    group: Mapped["DeviceGroup"] = relationship(back_populates="members")
    device: Mapped["Device"] = relationship()


class ProfileVersion(Base):
    __tablename__ = "profile_versions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    profile_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    changed_by_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    change_note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    profile: Mapped["Profile"] = relationship()
