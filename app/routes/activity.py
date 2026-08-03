from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.routes.base import create_crud_router

from app.schemas.activity import ActivityCreate, ActivityExploreResponse, ActivityPatch, ActivityResponse
from app.schemas.common import Pagination
from app.services.activity import get_activity_service

router = APIRouter()


@router.get("/api/sports", response_model=list[ActivityExploreResponse], tags=["Activities"])
async def explore_sports(
    pagination: Annotated[Pagination, Depends()],
    region: str | None = Query(default=None, max_length=100),
    sigun: str | None = Query(default=None, max_length=100),
    sport: str | None = Query(default=None, max_length=100),
    theme: str | None = Query(default=None, max_length=30),
    mission: bool | None = None,
    service=Depends(get_activity_service),
):
    return await service.explore(
        region=region,
        sigun=sigun,
        sport=sport,
        theme=theme,
        mission=mission,
        offset=pagination.offset,
        limit=pagination.size,
    )


@router.get("/api/events", response_model=list[ActivityExploreResponse], tags=["Activities"])
async def explore_events(
    pagination: Annotated[Pagination, Depends()],
    region: str | None = Query(default=None, max_length=100),
    sigun: str | None = Query(default=None, max_length=100),
    mission: bool | None = None,
    service=Depends(get_activity_service),
):
    return await service.explore(
        region=region,
        sigun=sigun,
        sport=None,
        theme=None,
        mission=mission,
        categories=("event", "festival"),
        offset=pagination.offset,
        limit=pagination.size,
    )


router.include_router(create_crud_router(
    prefix="/api/activities",
    tag="Activities",
    create_model=ActivityCreate,
    patch_model=ActivityPatch,
    response_model=ActivityResponse,
    service_dependency=get_activity_service,
))
