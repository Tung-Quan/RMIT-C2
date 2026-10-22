from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import models, schemas
from app.db.conflicts import raise_integrity_conflict
from app.db.database import get_db
from app.dependencies import require_company_owner_or_member, require_role

router = APIRouter(prefix="/companies", tags=["companies"])


@router.post("", response_model=schemas.CompanyRead, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: schemas.CompanyCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    existing = (
        db.query(models.Company).filter(models.Company.owner_user_id == current_user.id).first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a company profile",
        )

    company = models.Company(owner_user_id=current_user.id, **payload.model_dump())
    db.add(company)
    try:
        db.commit()
    except IntegrityError as exc:
        raise_integrity_conflict(
            db,
            exc,
            detail="You already have a company profile",
            entity_type="company",
            operation="create",
        )
    db.refresh(company)
    return company


@router.get("/me", response_model=schemas.CompanyRead)
def get_my_company(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    company = (
        db.query(models.Company).filter(models.Company.owner_user_id == current_user.id).first()
    )
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.put("/{company_id}", response_model=schemas.CompanyRead)
def update_company(
    company_id: int,
    payload: schemas.CompanyUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("hr", "admin")),
):
    company = require_company_owner_or_member(company_id, db, current_user)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(company, field, value)
    db.commit()
    db.refresh(company)
    return company
