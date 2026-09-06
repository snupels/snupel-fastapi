from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.deps.auth import LoginUser, optional_user, require_admin, require_user
from app.models import SubmissionStatus
from app.schemas.common import Pagination
from app.schemas.stamp_submission import (
    AdminStampSubmissionResponse,
    CommunityFeedResponse,
    FeedCommentCreate,
    FeedCommentResponse,
    FeedEngagementResponse,
    FeedVisibilityUpdate,
    RejectSubmission,
    StampSubmissionCreate,
    StampSubmissionResponse,
    UploadUrlRequest,
    UploadUrlResponse,
)
from app.services.stamp_submission import get_stamp_submission_service

router = APIRouter(tags=["Stamp submissions"])


@router.post("/api/stamp-submissions/upload-url", response_model=UploadUrlResponse)
async def upload_url(
    body: UploadUrlRequest,
    actor: LoginUser = Depends(require_user),
    service=Depends(get_stamp_submission_service),
):
    return await service.upload_url(body, actor)


@router.post(
    "/api/stamp-submissions",
    response_model=StampSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit(
    body: StampSubmissionCreate,
    actor: LoginUser = Depends(require_user),
    service=Depends(get_stamp_submission_service),
):
    return await service.create(body, actor)


@router.get("/api/stamp-submissions", response_model=list[StampSubmissionResponse])
async def list_own(
    pagination: Annotated[Pagination, Depends()],
    actor: LoginUser = Depends(require_user),
    service=Depends(get_stamp_submission_service),
):
    return await service.list_user(
        actor, offset=pagination.offset, limit=pagination.size
    )


@router.patch(
    "/api/stamp-submissions/{item_id}/feed",
    response_model=StampSubmissionResponse,
)
async def update_feed_visibility(
    body: FeedVisibilityUpdate,
    item_id: int = Path(gt=0),
    actor: LoginUser = Depends(require_user),
    service=Depends(get_stamp_submission_service),
):
    return await service.update_feed_visibility(item_id, body, actor)


@router.get("/api/community-feed", response_model=list[CommunityFeedResponse])
async def community_feed(
    pagination: Annotated[Pagination, Depends()],
    actor: LoginUser | None = Depends(optional_user),
    service=Depends(get_stamp_submission_service),
):
    return await service.list_feed(
        user=actor, offset=pagination.offset, limit=pagination.size
    )


@router.get("/api/community-feed/me", response_model=list[CommunityFeedResponse])
async def own_community_feed(
    pagination: Annotated[Pagination, Depends()],
    actor: LoginUser = Depends(require_user),
    service=Depends(get_stamp_submission_service),
):
    return await service.list_feed(
        user=actor,
        offset=pagination.offset,
        limit=pagination.size,
    )


@router.post(
    "/api/community-feed/{item_id}/like",
    response_model=FeedEngagementResponse,
)
async def like_feed_post(
    item_id: int = Path(gt=0),
    actor: LoginUser = Depends(require_user),
    service=Depends(get_stamp_submission_service),
):
    return await service.update_like(item_id, actor, liked=True)


@router.delete(
    "/api/community-feed/{item_id}/like",
    response_model=FeedEngagementResponse,
)
async def unlike_feed_post(
    item_id: int = Path(gt=0),
    actor: LoginUser = Depends(require_user),
    service=Depends(get_stamp_submission_service),
):
    return await service.update_like(item_id, actor, liked=False)


@router.get(
    "/api/community-feed/{item_id}/comments",
    response_model=list[FeedCommentResponse],
)
async def feed_comments(
    pagination: Annotated[Pagination, Depends()],
    item_id: int = Path(gt=0),
    service=Depends(get_stamp_submission_service),
):
    return await service.list_comments(
        item_id, offset=pagination.offset, limit=pagination.size
    )


@router.post(
    "/api/community-feed/{item_id}/comments",
    response_model=FeedCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_feed_comment(
    body: FeedCommentCreate,
    item_id: int = Path(gt=0),
    actor: LoginUser = Depends(require_user),
    service=Depends(get_stamp_submission_service),
):
    return await service.add_comment(item_id, body.content, actor)


@router.get(
    "/api/admin/stamp-submissions",
    response_model=list[AdminStampSubmissionResponse],
)
async def list_pending(
    pagination: Annotated[Pagination, Depends()],
    submission_status: SubmissionStatus = Query(
        default=SubmissionStatus.pending, alias="status"
    ),
    _: LoginUser = Depends(require_admin),
    service=Depends(get_stamp_submission_service),
):
    return await service.list_admin(
        submission_status, offset=pagination.offset, limit=pagination.size
    )


@router.post(
    "/api/admin/stamp-submissions/{item_id}/approve",
    response_model=StampSubmissionResponse,
)
async def approve(
    item_id: int = Path(gt=0),
    actor: LoginUser = Depends(require_admin),
    service=Depends(get_stamp_submission_service),
):
    return await service.review(item_id, actor)


@router.post(
    "/api/admin/stamp-submissions/{item_id}/reject",
    response_model=StampSubmissionResponse,
)
async def reject(
    body: RejectSubmission,
    item_id: int = Path(gt=0),
    actor: LoginUser = Depends(require_admin),
    service=Depends(get_stamp_submission_service),
):
    return await service.review(item_id, actor, body.reason)
