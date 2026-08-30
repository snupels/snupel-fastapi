from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Passport, PasswordResetCode, SocialAccount, User


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_user_by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == email))

    async def find_user_by_id(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def find_social_user(self, provider: str, provider_user_id: str) -> User | None:
        return await self.session.scalar(
            select(User)
            .join(SocialAccount, SocialAccount.user_id == User.id)
            .where(
                SocialAccount.provider == provider,
                SocialAccount.provider_user_id == provider_user_id,
            )
        )

    async def create_user(
        self,
        *,
        email: str,
        password_hash: str | None,
        birth_date=None,
        gender=None,
        nickname=None,
        phone_number=None,
        terms_agreed_at=None,
        privacy_agreed_at=None,
        marketing_email_agreed=False,
        marketing_sns_agreed=False,
    ) -> User:
        user = User(
            email=email,
            password_hash=password_hash,
            birth_date=birth_date,
            gender=gender,
            nickname=nickname,
            phone_number=phone_number,
            terms_agreed_at=terms_agreed_at,
            privacy_agreed_at=privacy_agreed_at,
            marketing_email_agreed=marketing_email_agreed,
            marketing_sns_agreed=marketing_sns_agreed,
        )
        self.session.add(user)
        await self.session.flush()
        self.session.add(Passport(user_id=user.id))
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def create_social_account(
        self, *, user_id: int, provider: str, provider_user_id: str
    ) -> None:
        self.session.add(
            SocialAccount(
                user_id=user_id,
                provider=provider,
                provider_user_id=provider_user_id,
            )
        )
        await self.session.flush()

    async def update_profile(self, user: User, **values) -> User:
        for key, value in values.items():
            setattr(user, key, value)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def create_reset_code(
        self, *, user_id: int, code_hash: str, expires_at: datetime
    ) -> PasswordResetCode:
        await self.session.execute(
            update(PasswordResetCode)
            .where(PasswordResetCode.user_id == user_id, PasswordResetCode.used_at.is_(None))
            .values(used_at=datetime.now())
        )
        row = PasswordResetCode(user_id=user_id, code_hash=code_hash, expires_at=expires_at)
        self.session.add(row)
        await self.session.flush()
        return row

    async def active_reset_code(self, user_id: int) -> PasswordResetCode | None:
        return await self.session.scalar(
            select(PasswordResetCode)
            .where(PasswordResetCode.user_id == user_id, PasswordResetCode.used_at.is_(None))
            .order_by(PasswordResetCode.id.desc())
        )

    async def reset_password(self, user: User, code: PasswordResetCode, password_hash: str) -> None:
        user.password_hash = password_hash
        code.used_at = datetime.now()
        await self.session.flush()
