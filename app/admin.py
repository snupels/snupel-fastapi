import os
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import select
from sqladmin import Admin, BaseView, ModelView, expose
from sqladmin.authentication import AuthenticationBackend
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import RedirectResponse

from .config import admins, production_secret
from .config.database import SessionLocal, engine
from .deps.auth import LoginUser, sign_access_token, verify_access_token
from .deps.rate_limit import RateLimiter
from .jobs.sync_tourism import sync_tourism
from .models import (
    Activity,
    Badge,
    CollectedBadge,
    CollectedStamp,
    Course,
    CourseStamp,
    Passport,
    SocialAccount,
    Stamp,
    StampSubmission,
    User,
)
from .repositories.stamp import StampRepository
from .services.auth import password_hasher
from .services.mail import send_mail
from .services.stamp import StampService

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


class UserAdmin(DefaultAdmin, model=User):
    column_exclude_list = [User.password_hash]
    column_details_exclude_list = [User.password_hash]
    form_excluded_columns = [User.password_hash]
    column_searchable_list = [User.email]


class SocialAccountAdmin(DefaultAdmin, model=SocialAccount):
    pass


class PassportAdmin(DefaultAdmin, model=Passport):
    pass


class ActivityAdmin(DefaultAdmin, model=Activity):
    pass


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
    form_excluded_columns = [CollectedStamp.activity_id]


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


class StampSubmissionAdmin(DefaultAdmin, model=StampSubmission):
    can_create = False
    can_edit = False
    can_delete = False


class BadgeAdmin(DefaultAdmin, model=Badge):
    pass


class CollectedBadgeAdmin(DefaultAdmin, model=CollectedBadge):
    pass


class CourseAdmin(DefaultAdmin, model=Course):
    pass


class CourseStampAdmin(DefaultAdmin, model=CourseStamp):
    pass


def setup_admin(app) -> Admin:
    production_secret("JWT_SECRET", os.getenv("JWT_SECRET"))
    secret = os.getenv("ADMIN_SESSION_SECRET") or os.getenv("JWT_SECRET")
    production_secret("ADMIN_SESSION_SECRET or JWT_SECRET", secret)

    admin = Admin(
        app,
        engine,
        title="Snupel Admin",
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
        StampSubmissionAdmin,
        BadgeAdmin,
        CollectedBadgeAdmin,
        CourseAdmin,
        CourseStampAdmin,
    ):
        admin.add_view(view)
    return admin
