from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.db.base import get_db
from app.db.models import User
from app.core.deps import get_current_user

router = APIRouter(prefix="/users")

ALLOWED_ROLES = ("admin", "owner")


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    status: str
    created_at: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_user(cls, u: User) -> "UserResponse":
        return cls(
            id=u.id,
            email=u.email,
            role=u.role,
            status=u.status,
            created_at=u.created_at.isoformat(),
        )


class InviteUserRequest(BaseModel):
    email: str
    role: str = "admin"


class UpdateUserRequest(BaseModel):
    role: str | None = None
    status: str | None = None


@router.get("", response_model=list[UserResponse])
async def list_users(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User)
        .where(User.tenant_id == current_user.tenant_id)
        .order_by(User.created_at)
    )
    return [UserResponse.from_orm_user(u) for u in result.scalars().all()]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: InviteUserRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(ALLOWED_ROLES)}")

    # Check for duplicate email within tenant
    existing = await db.execute(
        select(User).where(
            User.tenant_id == current_user.tenant_id,
            User.email == body.email.lower(),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A user with that email already exists")

    user = User(
        tenant_id=current_user.tenant_id,
        email=body.email.lower(),
        role=body.role,
        status="active",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserResponse.from_orm_user(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == current_user.tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent removing the last owner
    if body.role and user.role == "owner" and body.role != "owner":
        owners = await db.execute(
            select(User).where(
                User.tenant_id == current_user.tenant_id,
                User.role == "owner",
                User.status == "active",
            )
        )
        if len(owners.scalars().all()) <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last owner")

    if body.role:
        if body.role not in ALLOWED_ROLES:
            raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(ALLOWED_ROLES)}")
        user.role = body.role
    if body.status:
        if body.status not in ("active", "inactive"):
            raise HTTPException(status_code=400, detail="Status must be active or inactive")
        user.status = body.status

    await db.commit()
    await db.refresh(user)
    return UserResponse.from_orm_user(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == current_user.tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.delete(user)
    await db.commit()
