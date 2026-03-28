"""
Seed script — creates a test tenant, user, and enrolled device.
Run: python scripts/seed_db.py
"""
import asyncio
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.models import Base, Tenant, User, Device
from app.core.security import hash_password

DATABASE_URL = "postgresql+asyncpg://mdm:mdm@localhost:5433/mdmdb"

TENANT_ID   = "11111111-1111-1111-1111-111111111111"
USER_ID     = "22222222-2222-2222-2222-222222222222"
DEVICE_ID   = "33333333-3333-3333-3333-333333333333"
DEVICE_UDID = "AAAA-BBBB-CCCC-DDDD-TEST"


async def seed():
    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with Session() as db:
        tenant = Tenant(
            id=TENANT_ID,
            name="Acme Corp (Test)",
            slug="acme-test",
            plan="starter",
            entra_tenant_id="your-entra-tenant-id",
            entra_client_id="your-entra-client-id",
        )
        db.add(tenant)

        user = User(
            id=USER_ID,
            tenant_id=TENANT_ID,
            email="admin@acme.com",
            hashed_password=hash_password("admin123"),
            role="owner",
        )
        db.add(user)

        device = Device(
            id=DEVICE_ID,
            tenant_id=TENANT_ID,
            udid=DEVICE_UDID,
            platform="macos",
            serial_number="C02TEST1234",
            model="MacBookPro18,3",
            os_version="14.3.1",
            hostname="acme-macbook",
            status="enrolled",
            # Fake APNs tokens for testing connect/checkin without real device
            push_token="aabbccddeeff" * 5 + "aabb",
            push_magic="test-push-magic-12345",
            push_topic="com.acme.mdm",
        )
        db.add(device)
        await db.commit()

    print("Seeded successfully!")
    print(f"  Tenant ID : {TENANT_ID}")
    print(f"  Login     : admin@acme.com / admin123")
    print(f"  Device ID : {DEVICE_ID}")
    print(f"  Device UDID: {DEVICE_UDID}")
    print()
    print("Test login:")
    print("  curl -X POST http://localhost:8000/api/v1/auth/login \\")
    print('    -H "Content-Type: application/json" \\')
    print('    -d \'{"email":"admin@acme.com","password":"admin123"}\'')

    await engine.dispose()


asyncio.run(seed())
