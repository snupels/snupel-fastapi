from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Passport


class PassportRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, user_id: int) -> list[Passport]:
        return list(self.session.scalars(select(Passport).where(Passport.user_id == user_id)))

    def get(self, item_id: int, user_id: int) -> Passport | None:
        return self.session.scalar(
            select(Passport).where(Passport.id == item_id, Passport.user_id == user_id)
        )

    def get_by_user(self, user_id: int) -> Passport | None:
        return self.session.scalar(select(Passport).where(Passport.user_id == user_id))

    def create(self, user_id: int) -> Passport:
        row = Passport(user_id=user_id)
        self.session.add(row)
        self.session.flush()
        self.session.refresh(row)
        return row

    def remove(self, row: Passport) -> None:
        self.session.delete(row)
        self.session.flush()

