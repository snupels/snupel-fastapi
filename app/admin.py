import os
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import func, select
from sqladmin import Admin, BaseView, ModelView, expose
from sqladmin.authentication import AuthenticationBackend
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import RedirectResponse

from .config import admins, production_secret
from .config.database import SessionLocal, engine
from .deps.auth import LoginUser, sign_access_token, verify_access_token
from .deps.rate_limit import RateLimiter
from .exceptions import ApiError
from .jobs.sync_tourism import sync_tourism
from .models import (
    Activity,
    ActivityCategory,
    Badge,
    CollectedBadge,
    CollectedStamp,
    Course,
    CourseStamp,
    Passport,
    SocialAccount,
    Stamp,
    StampSubmission,
    SubmissionStatus,
    User,
)
from .repositories.stamp import StampRepository
from .repositories.stamp_submission import StampSubmissionRepository
from .services.auth import password_hasher
from .services.mail import send_mail
from .services.stamp import StampService
from .services.stamp_submission import StampSubmissionService
from .services.storage import get_proof_storage

OTP_EXPIRES_IN = 600
OTP_RESEND_AFTER = 60
OTP_MAX_ATTEMPTS = 5


@dataclass
class PendingCode:
    digest: str
    expires_at: float
    sent_at: float
    attempts: int
    user_id: int


# ponytail: process-local OTP storage; move to Redis when running multiple API instances.
pending_codes: dict[str, PendingCode] = {}
admin_rate_limiter = RateLimiter(20)


class AdminAuth(AuthenticationBackend):
    def __init__(self, secret_key: str) -> None:
        super().__init__(
            secret_key,
            same_site="lax",
            https_only=os.getenv("ENVIRONMENT") == "production",
        )
        self.otp_key = secret_key.encode()

    def _digest(self, code: str) -> str:
        return hmac.new(self.otp_key, code.encode(), hashlib.sha256).hexdigest()

    async def login(self, request: Request) -> bool | RedirectResponse:
        client = getattr(request, "client", None)
        if not admin_rate_limiter.allow(client.host if client else "local"):
            return False
        form = await request.form()
        pending_email = request.session.get("pending_admin_email")
        if pending_email:
            return self._verify_code(request, pending_email, str(form.get("code", "")))

        email = str(form.get("username", "")).strip().lower()
        password = str(form.get("password", ""))
        if not password or email not in admins():
            return False

        async with SessionLocal() as session:
            user = await session.scalar(select(User).where(User.email == email))
        if not user or not user.password_hash:
            return False

        try:
            await run_in_threadpool(password_hasher.verify, user.password_hash, password)
        except (InvalidHashError, VerifyMismatchError):
            return False

        now = time.monotonic()
        pending = pending_codes.get(email)
        if pending and pending.expires_at > now:
            if pending.attempts >= OTP_MAX_ATTEMPTS:
                return False
            if now - pending.sent_at < OTP_RESEND_AFTER:
                request.session["pending_admin_email"] = email
                return RedirectResponse("/admin/login", status_code=302)

        code = f"{secrets.randbelow(1_000_000):06d}"
        await run_in_threadpool(
            send_mail,
            email,
            "Snupel 관리자 로그인 인증 코드",
            f"인증 코드는 {code}입니다. 10분 이내에 입력해 주세요.",
        )
        pending_codes[email] = PendingCode(
            digest=self._digest(code),
            expires_at=now + OTP_EXPIRES_IN,
            sent_at=now,
            attempts=pending.attempts if pending and pending.expires_at > now else 0,
            user_id=user.id,
        )
        request.session["pending_admin_email"] = email
        return RedirectResponse("/admin/login", status_code=302)

    def _verify_code(self, request: Request, email: str, code: str) -> bool:
        pending = pending_codes.get(email)
        if (
            not pending
            or email not in admins()
            or pending.expires_at <= time.monotonic()
            or pending.attempts >= OTP_MAX_ATTEMPTS
        ):
            pending_codes.pop(email, None)
            request.session.pop("pending_admin_email", None)
            return False

        pending.attempts += 1
        if not hmac.compare_digest(pending.digest, self._digest(code.strip())):
            return False

        request.session.pop("pending_admin_email", None)
        pending_codes.pop(email, None)
        request.session["token"] = sign_access_token(LoginUser(pending.user_id, email))[0]
        return True

    async def logout(self, request: Request) -> bool:
        pending_codes.pop(request.session.get("pending_admin_email", ""), None)
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("token")
        user = verify_access_token(token) if token else None
        return bool(user and user.email.lower() in admins())


class DefaultAdmin(ModelView):
    column_list = "__all__"
    page_size = 25
    can_export = False
    can_import = False


class UserAdmin(DefaultAdmin, model=User):
    # SQLAdmin's inherited '__all__' takes precedence over exclusion lists.
    column_list = [
        column.key for column in User.__table__.columns
        if column.key not in {"password_hash", "postal_code", "address", "address_detail"}
    ]
    column_details_exclude_list = [User.password_hash, User.postal_code, User.address, User.address_detail]
    form_excluded_columns = [User.password_hash, User.username, User.postal_code, User.address, User.address_detail]
    column_searchable_list = [User.email]


class SocialAccountAdmin(DefaultAdmin, model=SocialAccount):
    pass


class PassportAdmin(DefaultAdmin, model=Passport):
    name = "패스포트"
    name_plural = "패스포트"
    category = "사용자"
    column_list = [Passport.id, Passport.user_email, Passport.created_at]
    column_labels = {Passport.user_email: "사용자 이메일", Passport.created_at: "생성일"}


class ActivityAdmin(DefaultAdmin, model=Activity):
    name = "이벤트·축제"
    name_plural = "이벤트·축제"
    category = "콘텐츠"
    icon = "fa-solid fa-calendar-days"
    column_list = [
        Activity.id,
        Activity.place_name,
        Activity.sigun,
        Activity.starts_at,
        Activity.ends_at,
        Activity.is_active,
    ]
    column_labels = {
        Activity.place_name: "이름",
        Activity.sigun: "시군",
        Activity.starts_at: "시작일",
        Activity.ends_at: "종료일",
        Activity.is_active: "노출",
        "representative_image_url": "대표 이미지 URL",
        "sport_name": "종목",
        "region": "지역",
        "summary": "설명",
        "address": "주소",
        "source_url": "안내 URL",
        "latitude": "위도",
        "longitude": "경도",
    }
    column_searchable_list = [Activity.place_name, Activity.sigun, Activity.address]
    column_default_sort = (Activity.starts_at, True)
    form_columns = [
        "place_name",
        "summary",
        "representative_image_url",
        "sport_name",
        "region",
        "sigun",
        "address",
        "latitude",
        "longitude",
        "source_url",
        "starts_at",
        "ends_at",
        "is_active",
    ]

    def list_query(self, request: Request):
        return select(Activity).where(Activity.category == ActivityCategory.event)

    def count_query(self, request: Request):
        return select(func.count(Activity.id)).where(Activity.category == ActivityCategory.event)

    async def on_model_change(self, data, model, is_created: bool, request: Request) -> None:
        model.category = ActivityCategory.event
        if is_created:
            model.source = "admin"

    async def check_can_view_details(self, request: Request, model) -> bool:
        return bool(model and model.category == ActivityCategory.event)

    async def check_can_edit(self, request: Request, model) -> bool:
        return bool(model and model.category == ActivityCategory.event)

    async def check_can_delete(self, request: Request, model) -> bool:
        return bool(model and model.category == ActivityCategory.event)


class StampAdmin(DefaultAdmin, model=Stamp):
    column_list = [
        Stamp.id,
        Stamp.stamp_catalog_id,
        Stamp.description,
        Stamp.image_url,
        Stamp.created_at,
        Stamp.updated_at,
    ]


class StampSeedAdmin(BaseView):
    name = "Seed Stamps"

    @expose("/stamp-seed", methods=["GET", "POST"])
    async def seed(self, request: Request):
        result = None
        if request.method == "POST":
            async with SessionLocal() as session:
                result = await StampService(StampRepository(session)).seed_catalog()
                await session.commit()
        return await self.templates.TemplateResponse(
            request,
            "sqladmin/stamp_seed.html",
            {"result": result},
        )


class CollectedStampAdmin(DefaultAdmin, model=CollectedStamp):
    name = "사용자 스탬프"
    name_plural = "사용자 스탬프"
    category = "패스포트"
    icon = "fa-solid fa-stamp"
    column_list = [
        CollectedStamp.id,
        "passport",
        "stamp",
        CollectedStamp.activity_id,
        CollectedStamp.collected_at,
    ]
    column_labels = {
        "passport": "사용자 패스포트",
        "stamp": "스탬프",
        CollectedStamp.activity_id: "장소 ID",
        CollectedStamp.collected_at: "획득일",
    }
    form_columns = ["passport", "stamp", "collected_at"]
    form_ajax_refs = {
        "passport": {"fields": (Passport.user_email, Passport.id), "limit": 20},
        "stamp": {"fields": (Stamp.activity_label, Stamp.description), "limit": 20},
    }
    column_default_sort = (CollectedStamp.collected_at, True)


class TourismSyncAdmin(BaseView):
    name = "Sync Tourism"

    @expose("/tourism-sync", methods=["GET", "POST"])
    async def sync(self, request: Request):
        result = await sync_tourism() if request.method == "POST" else None
        return await self.templates.TemplateResponse(
            request,
            "sqladmin/tourism_sync.html",
            {"result": result},
        )


def _review_reason(decision: str, reason: str) -> str | None:
    if decision == "approve":
        return None
    if decision != "reject":
        raise ValueError("승인 또는 거절을 선택해 주세요.")
    reason = reason.strip()
    if not 1 <= len(reason) <= 1000:
        raise ValueError("거절 사유를 1~1000자로 입력해 주세요.")
    return reason


class SubmissionReviewAdmin(BaseView):
    name = "제출 검토"
    category = "패스포트"
    icon = "fa-solid fa-camera"

    @expose("/submission-review", methods=["GET", "POST"], identity="submission-review")
    async def review(self, request: Request):
        error = None
        if request.method == "POST":
            try:
                form = await request.form()
                item_id = int(str(form.get("submission_id", "")))
                reason = _review_reason(
                    str(form.get("decision", "")), str(form.get("rejection_reason", ""))
                )
                actor = verify_access_token(request.session.get("token", ""))
                if not actor:
                    return RedirectResponse("/admin/login", status_code=302)
                async with SessionLocal() as session:
                    service = StampSubmissionService(
                        StampSubmissionRepository(session), get_proof_storage()
                    )
                    await service.review(item_id, actor, reason)
                    await session.commit()
                message = "제출을 승인했습니다." if reason is None else "제출을 거절했습니다."
                return RedirectResponse(
                    "/admin/submission-review?" + urlencode({"message": message}),
                    status_code=303,
                )
            except (ApiError, ValueError) as exc:
                error = exc.message if isinstance(exc, ApiError) else str(exc)

        async with SessionLocal() as session:
            # ponytail: one-page queue; paginate if pending reviews routinely exceed 100.
            submissions = await StampSubmissionService(
                StampSubmissionRepository(session), get_proof_storage()
            ).list_admin(SubmissionStatus.pending, limit=100)
        return await self.templates.TemplateResponse(
            request,
            "sqladmin/submission_review.html",
            {
                "submissions": submissions,
                "error": error,
                "message": request.query_params.get("message"),
            },
        )


class StampSubmissionAdmin(DefaultAdmin, model=StampSubmission):
    name = "제출 내역"
    name_plural = "제출 내역"
    category = "패스포트"
    can_create = False
    can_edit = False
    can_delete = False
    column_list = [
        StampSubmission.id,
        StampSubmission.passport_id,
        StampSubmission.stamp_id,
        StampSubmission.status,
        StampSubmission.reviewer_id,
        StampSubmission.reviewed_at,
        StampSubmission.rejection_reason,
    ]
    column_labels = {
        StampSubmission.passport_id: "패스포트 ID",
        StampSubmission.stamp_id: "스탬프 ID",
        StampSubmission.status: "상태",
        StampSubmission.reviewer_id: "검토자 ID",
        StampSubmission.reviewed_at: "검토일",
        StampSubmission.rejection_reason: "거절 사유",
    }
    column_default_sort = (StampSubmission.id, True)


class BadgeAdmin(DefaultAdmin, model=Badge):
    pass


class CollectedBadgeAdmin(DefaultAdmin, model=CollectedBadge):
    pass


class CourseAdmin(DefaultAdmin, model=Course):
    name = "패스포트 미션"
    name_plural = "패스포트 미션"
    category = "패스포트"
    icon = "fa-solid fa-route"
    column_list = [
        Course.id,
        Course.title,
        Course.theme,
        Course.sport_name,
        Course.is_published,
        Course.updated_at,
    ]
    column_labels = {
        Course.title: "미션명",
        Course.theme: "테마",
        Course.sport_name: "종목",
        Course.is_published: "공개",
        Course.updated_at: "수정일",
        "category": "분류",
        "recommended_companion": "추천 동행",
        "representative_image_url": "대표 이미지 URL",
        "estimated_duration_minutes": "예상 소요 시간(분)",
        "description": "설명",
    }
    column_searchable_list = [Course.title, Course.description]
    column_default_sort = (Course.updated_at, True)
    form_columns = [
        "title",
        "description",
        "theme",
        "category",
        "sport_name",
        "recommended_companion",
        "estimated_duration_minutes",
        "representative_image_url",
        "is_published",
    ]


class CourseStampAdmin(DefaultAdmin, model=CourseStamp):
    name = "미션 장소"
    name_plural = "미션 장소"
    category = "패스포트"
    icon = "fa-solid fa-location-dot"
    column_list = [CourseStamp.id, "course", "stamp", CourseStamp.position]
    column_labels = {
        "course": "패스포트 미션",
        "stamp": "스탬프 장소",
        CourseStamp.position: "순서",
    }
    form_columns = ["course", "stamp", "position"]
    form_ajax_refs = {
        "course": {"fields": (Course.title, Course.sport_name), "limit": 20},
        "stamp": {"fields": (Stamp.activity_label, Stamp.description), "limit": 20},
    }


def setup_admin(app) -> Admin:
    production_secret("JWT_SECRET", os.getenv("JWT_SECRET"))
    secret = os.getenv("ADMIN_SESSION_SECRET") or os.getenv("JWT_SECRET")
    production_secret("ADMIN_SESSION_SECRET or JWT_SECRET", secret)

    admin = Admin(
        app,
        engine,
        title="Snupel 운영자 도구",
        authentication_backend=AdminAuth(secret or "development-only-secret"),
    )
    for view in (
        UserAdmin,
        SocialAccountAdmin,
        PassportAdmin,
        ActivityAdmin,
        StampAdmin,
        StampSeedAdmin,
        CollectedStampAdmin,
        TourismSyncAdmin,
        SubmissionReviewAdmin,
        StampSubmissionAdmin,
        BadgeAdmin,
        CollectedBadgeAdmin,
        CourseAdmin,
        CourseStampAdmin,
    ):
        admin.add_view(view)
    return admin
