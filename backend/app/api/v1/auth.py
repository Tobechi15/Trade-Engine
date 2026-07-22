from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth.jwt import create_access_token
from app.config import Settings, get_settings
from app.schemas.common import ok

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/token")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(), settings: Settings = Depends(get_settings)
):
    if form_data.username != settings.operator_username or form_data.password != settings.operator_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(settings, subject=form_data.username)
    return ok({"access_token": token, "token_type": "bearer"})
