from fastapi import APIRouter, Depends, Path, Query, status

from app.deps.auth import LoginUser, require_admin, require_user
from app.models import SubmissionStatus
from app.schemas.stamp_submission import (
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
    actor: LoginUser = Depends(require_user),
    service=Depends(get_stamp_submission_service),
):
    return await service.list_user(actor)


@router.get("/api/admin/stamp-submissions", response_model=list[StampSubmissionResponse])
async def list_pending(
    submission_status: SubmissionStatus = Query(
        default=SubmissionStatus.pending, alias="status"
    ),
    _: LoginUser = Depends(require_admin),
    service=Depends(get_stamp_submission_service),
):
    return await service.list_admin(submission_status)


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
