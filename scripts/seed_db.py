#!/usr/bin/env python3
"""
Seed a demo tenant + admin user into the local dev database.
Run after `docker compose up` is healthy:
    docker compose exec app python scripts/seed_db.py
"""
import asyncio
import sys
import os

# Allow running from repo root or inside the container
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.db.models import Base, Tenant, User
from app.core.security import hash_password

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://mdm:mdm@localhost:5433/mdmdb",
)

TENANT_NAME  = "Strativon Demo"
TENANT_SLUG  = "strativon"
ADMIN_EMAIL  = "admin@strativon.com"
ADMIN_PASS   = "Admin@1234"


async def seed():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        # Check if already seeded
        result = await session.execute(select(Tenant).where(Tenant.slug == TENANT_SLUG))
        tenant = result.scalar_one_or_none()

        if tenant:
            print(f"[seed] Tenant '{TENANT_SLUG}' already exists — skipping.")
        else:
            tenant = Tenant(
                name=TENANT_NAME,
                slug=TENANT_SLUG,
                plan="starter",
                status="active",
                apns_push_topic="com.apple.mgmt.External.89b84cf0-a26d-454e-8f74-e8954e2e4c6f",
            )
            session.add(tenant)
            await session.flush()  # get tenant.id
            print(f"[seed] Created tenant: {tenant.name} (id={tenant.id})")

        # Check if admin user exists
        result = await session.execute(select(User).where(User.email == ADMIN_EMAIL))
        user = result.scalar_one_or_none()

        if user:
            print(f"[seed] User '{ADMIN_EMAIL}' already exists — skipping.")
        else:
            user = User(
                tenant_id=tenant.id,
                email=ADMIN_EMAIL,
                hashed_password=hash_password(ADMIN_PASS),
                role="admin",
                status="active",
            )
            session.add(user)
            print(f"[seed] Created admin user: {ADMIN_EMAIL}")

        await session.commit()

    await engine.dispose()

    print()
    print("=" * 45)
    print("  Demo login credentials")
    print("=" * 45)
    print(f"  URL      : http://localhost:3000")
    print(f"  Email    : {ADMIN_EMAIL}")
    print(f"  Password : {ADMIN_PASS}")
    print("=" * 45)


if __name__ == "__main__":
    asyncio.run(seed())
