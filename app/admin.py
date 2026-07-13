import os

from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import select
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from .auth.service import password_hasher
from .config import admins
from .database import SessionLocal, engine
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
    User,
)
from .security import LoginUser, sign_access_token, verify_access_token


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
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

        request.session["token"] = sign_access_token(LoginUser(user.id, user.email))[0]
        return True

    async def logout(self, request: Request) -> bool:
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
    pass


class CollectedStampAdmin(DefaultAdmin, model=CollectedStamp):
    pass


class BadgeAdmin(DefaultAdmin, model=Badge):
    pass


class CollectedBadgeAdmin(DefaultAdmin, model=CollectedBadge):
    pass


class CourseAdmin(DefaultAdmin, model=Course):
    pass


class CourseStampAdmin(DefaultAdmin, model=CourseStamp):
    pass


def setup_admin(app) -> Admin:
    secret = os.getenv("ADMIN_SESSION_SECRET") or os.getenv("JWT_SECRET")
    if not secret and os.getenv("ENVIRONMENT") == "production":
        raise RuntimeError("ADMIN_SESSION_SECRET or JWT_SECRET is required in production.")

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
        CollectedStampAdmin,
        BadgeAdmin,
        CollectedBadgeAdmin,
        CourseAdmin,
        CourseStampAdmin,
    ):
        admin.add_view(view)
    return admin
