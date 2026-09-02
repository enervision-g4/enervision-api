from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Site
from app.schemas import SiteOut
from app.security import get_current_subject

router = APIRouter(prefix="/api/v1/sites", tags=["sites"])


@router.get("", response_model=list[SiteOut])
def list_sites(
    db: Session = Depends(get_db),
    _subject: str = Depends(get_current_subject),
):
    return db.scalars(select(Site)).all()


@router.get("/{site_id}", response_model=SiteOut)
def get_site(
    site_id: str,
    db: Session = Depends(get_db),
    _subject: str = Depends(get_current_subject),
):
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Site inexistant")
    return site
