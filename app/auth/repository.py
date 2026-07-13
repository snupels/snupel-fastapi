from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SocialAccount, User


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_user_by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(User.email == email))

    def find_social_user(self, provider: str, provider_user_id: str) -> User | None:
        return self.session.scalar(
            select(User)
            .join(SocialAccount, SocialAccount.user_id == User.id)
            .where(
                SocialAccount.provider == provider,
                SocialAccount.provider_user_id == provider_user_id,
            )
        )

    def create_user(self, *, email: str, password_hash: str | None, birth_date=None, gender=None) -> User:
        user = User(
            email=email,
            password_hash=password_hash,
            birth_date=birth_date,
            gender=gender,
        )
        self.session.add(user)
        self.session.flush()
        self.session.refresh(user)
        return user

    def create_social_account(self, *, user_id: int, provider: str, provider_user_id: str) -> None:
        self.session.add(
            SocialAccount(
                user_id=user_id,
                provider=provider,
                provider_user_id=provider_user_id,
            )
        )
        self.session.flush()

