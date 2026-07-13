from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_session
from app.errors import ApiError
from app.security import LoginUser

from .repository import PassportRepository


class PassportService:
    def __init__(self, repository: PassportRepository) -> None:
        self.repository = repository

    @staticmethod
    def _user(user: LoginUser | None) -> LoginUser:
        if not user:
            raise ApiError(401, "unauthorized", "Login is required.")
        return user

    def _found(self, item_id: int, user: LoginUser):
        row = self.repository.get(item_id, user.id)
        if not row:
            raise ApiError(404, "not_found", "Passport not found.")
        return row

    def list(self, user: LoginUser | None):
        return self.repository.list(self._user(user).id)

    def get(self, item_id: int, user: LoginUser | None):
        return self._found(item_id, self._user(user))

    def create(self, body, user: LoginUser | None):
        actor = self._user(user)
        if body.user_id != actor.id:
            raise ApiError(403, "forbidden", "A passport can only belong to you.")
        if self.repository.get_by_user(actor.id):
            raise ApiError(409, "conflict", "Passport already exists.")
        try:
            return self.repository.create(actor.id)
        except IntegrityError as error:
            raise ApiError(409, "conflict", "Passport already exists.") from error

    def update(self, item_id: int, body, user: LoginUser | None):
        actor = self._user(user)
        if body.user_id != actor.id:
            raise ApiError(403, "forbidden", "A passport can only belong to you.")
        return self._found(item_id, actor)

    def remove(self, item_id: int, user: LoginUser | None) -> None:
        self.repository.remove(self._found(item_id, self._user(user)))


def get_passport_service(session: Session = Depends(get_session)) -> PassportService:
    return PassportService(PassportRepository(session))

