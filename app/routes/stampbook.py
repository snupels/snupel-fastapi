from fastapi import APIRouter, Depends, Query

from app.deps.auth import LoginUser, require_user
from app.schemas.stampbook import StampbookFilter, StampbookResponse
from app.services.stampbook import get_stampbook_service

router = APIRouter(prefix="/api/me", tags=["My page"])


@router.get("/stampbook", response_model=StampbookResponse)
async def stampbook(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=15, ge=1, le=100),
    status: StampbookFilter = Query(default=StampbookFilter.all),
    actor: LoginUser = Depends(require_user),
    service=Depends(get_stampbook_service),
):
    return await service.get(actor, status, page=page, size=size)
