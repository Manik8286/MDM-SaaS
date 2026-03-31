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
    # Compliance
    compliance_status: Mapped[str] = mapped_column(String(50), default="unknown")
    compliance_checked_at: Mapped[datetime | None] = mapped_column(DateTime)

    tenant: Mapped["Tenant"] = relationship(back_populates="devices")
    commands: Mapped[list["MdmCommand"]] = relationship(back_populates="device")
    installed_apps: Mapped[list["InstalledApp"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    available_updates: Mapped[list["DeviceUpdate"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    device_users: Mapped[list["DeviceUser"]] = relationship(back_populates="device", cascade="all, delete-orphan")


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
