from fastapi import Depends
from sqlalchemy.orm import Session

from app.collected import CollectedService
from app.database import get_session

from .repository import CollectedStampRepository


def get_collected_stamp_service(session: Session = Depends(get_session)) -> CollectedService:
    return CollectedService(CollectedStampRepository(session), "Stamp")

