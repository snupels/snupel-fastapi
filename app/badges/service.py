from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.service import CrudService

from .repository import BadgeRepository


def get_badge_service(session: Session = Depends(get_session)) -> CrudService:
    return CrudService(BadgeRepository(session), "Badge")

