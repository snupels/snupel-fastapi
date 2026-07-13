from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SocialAccount, User


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_user_by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == email))

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
        self, *, email: str, password_hash: str | None, birth_date=None, gender=None
    ) -> User:
        user = User(
            email=email,
            password_hash=password_hash,
            birth_date=birth_date,
            gender=gender,
        )
        self.session.add(user)
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
