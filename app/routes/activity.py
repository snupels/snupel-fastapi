from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.routes.base import create_crud_router

from app.exceptions import ApiError
from app.models import ActivityCategory
from app.schemas.activity import (
    ActivityCreate,
    ActivityExploreResponse,
    ActivityMapResponse,
    ActivityPatch,
    ActivityResponse,
)
from app.schemas.common import Pagination
from app.services.activity import get_activity_service

router = APIRouter()


@router.get("/api/activities/map", response_model=list[ActivityMapResponse], tags=["Activities"])
async def map_activities(
    south: float = Query(ge=-90, le=90),
    west: float = Query(ge=-180, le=180),
    north: float = Query(ge=-90, le=90),
    east: float = Query(ge=-180, le=180),
    category: ActivityCategory | None = None,
    sport: str | None = Query(default=None, max_length=100),
    mission: bool | None = None,
    limit: int = Query(default=300, ge=1, le=500),
    service=Depends(get_activity_service),
):
    if south > north or west > east:
        raise ApiError(400, "bad_request", "Invalid map bounds.")
    return await service.map_items(
        south=south,
        west=west,
        north=north,
        east=east,
        category=category,
        sport=sport,
        mission=mission,
        limit=limit,
    )


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
