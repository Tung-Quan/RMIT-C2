from fastapi import APIRouter, Depends
from app.db import schemas
from app.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Tide identity"])

@router.get("/me", response_model=schemas.UserRead)
def me(current_user=Depends(get_current_user)):
    return current_user
