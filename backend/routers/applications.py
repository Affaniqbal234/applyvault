from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models import Application, User
from schemas import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationUpdate,
    StatusEnum,
    StatsResponse,
)

router = APIRouter(prefix="/applications")


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    total_result = await db.execute(
        select(func.count()).where(Application.user_id == current_user.id)
    )
    total = total_result.scalar_one()

    counts_result = await db.execute(
        select(Application.status, func.count())
        .where(Application.user_id == current_user.id)
        .group_by(Application.status)
    )
    rows = counts_result.all()
    by_status = {s.value: 0 for s in StatusEnum}
    for row_status, count in rows:
        by_status[row_status] = count

    return StatsResponse(total=total, by_status=by_status)


@router.get("", response_model=list[ApplicationResponse])
async def list_applications(
    status: StatusEnum | None = None,
    search: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Application).where(Application.user_id == current_user.id)

    if status is not None:
        query = query.where(Application.status == status.value)

    if search is not None:
        query = query.where(
            or_(
                Application.company.ilike(f"%{search}%"),
                Application.role.ilike(f"%{search}%"),
            )
        )

    query = query.order_by(Application.date_applied.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ApplicationResponse)
async def create_application(
    body: ApplicationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    app = Application(
        user_id=current_user.id,
        company=body.company,
        role=body.role,
        date_applied=body.date_applied,
        status=body.status.value,
        notes=body.notes,
        url=body.url,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@router.patch("/{id}", response_model=ApplicationResponse)
async def update_application(
    id: int,
    body: ApplicationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Application).where(Application.id == id, Application.user_id == current_user.id)
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    updates = body.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] is not None:
        updates["status"] = updates["status"].value
    for field, value in updates.items():
        setattr(app, field, value)

    await db.commit()
    await db.refresh(app)
    return app


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Application).where(Application.id == id, Application.user_id == current_user.id)
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    await db.delete(app)
    await db.commit()
