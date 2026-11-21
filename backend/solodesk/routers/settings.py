from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..deps import get_db
from ..models import Settings, SettingsIn

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings(db: Session = Depends(get_db)) -> Settings:
    return db.get(Settings, 1)


@router.put("")
def update_settings(body: SettingsIn, db: Session = Depends(get_db)) -> Settings:
    settings = db.get(Settings, 1)
    settings.sqlmodel_update(body.model_dump())
    db.commit()
    db.refresh(settings)
    return settings
