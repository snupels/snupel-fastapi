from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .errors import ApiError
from .models import Passport
from .security import LoginUser


class CollectedRepository:
    def __init__(self, session, model, target_model, target_field: str) -> None:
        self.session = session
        self.model = model
        self.target_model = target_model
        self.target_field = target_field

    def list(self, user_id: int) -> list:
        statement = (
            select(self.model)
            .join(Passport, self.model.passport_id == Passport.id)
            .where(Passport.user_id == user_id)
            .order_by(self.model.id)
        )
        return list(self.session.scalars(statement))

    def get(self, item_id: int, user_id: int):
        return self.session.scalar(
            select(self.model)
            .join(Passport, self.model.passport_id == Passport.id)
            .where(self.model.id == item_id, Passport.user_id == user_id)
        )

    def passport_owned(self, passport_id: int, user_id: int) -> bool:
        return self.session.scalar(
            select(Passport.id).where(Passport.id == passport_id, Passport.user_id == user_id)
        ) is not None

    def target_exists(self, target_id: int) -> bool:
        return self.session.get(self.target_model, target_id) is not None

    def duplicate(self, passport_id: int, target_id: int, except_id: int = 0) -> bool:
        target = getattr(self.model, self.target_field)
        return self.session.scalar(
            select(self.model.id).where(
                self.model.passport_id == passport_id,
                target == target_id,
                self.model.id != except_id,
            )
        ) is not None

    def create(self, passport_id: int, target_id: int):
        row = self.model(passport_id=passport_id, **{self.target_field: target_id})
        self.session.add(row)
        self.session.flush()
        self.session.refresh(row)
        return row

    def update(self, row, passport_id: int, target_id: int):
        row.passport_id = passport_id
        setattr(row, self.target_field, target_id)
        self.session.flush()
        self.session.refresh(row)
        return row

    def remove(self, row) -> None:
        self.session.delete(row)
        self.session.flush()


class CollectedService:
    def __init__(self, repository: CollectedRepository, noun: str) -> None:
        self.repository = repository
        self.noun = noun

    @staticmethod
    def _user(user: LoginUser | None) -> LoginUser:
        if not user:
            raise ApiError(401, "unauthorized", "Login is required.")
        return user

    def _found(self, item_id: int, user: LoginUser):
        row = self.repository.get(item_id, user.id)
        if not row:
            raise ApiError(404, "not_found", f"Collected {self.noun.lower()} not found.")
        return row

    def _valid(self, passport_id: int, target_id: int, owner_id: int, except_id: int = 0):
        if not self.repository.passport_owned(passport_id, owner_id):
            raise ApiError(404, "not_found", "Passport not found.")
        if not self.repository.target_exists(target_id):
            raise ApiError(404, "not_found", f"{self.noun} not found.")
        if self.repository.duplicate(passport_id, target_id, except_id):
            raise ApiError(409, "conflict", f"{self.noun} already collected.")

    def list(self, user: LoginUser | None):
        return self.repository.list(self._user(user).id)

    def get(self, item_id: int, user: LoginUser | None):
        return self._found(item_id, self._user(user))

    def create(self, body, user: LoginUser | None):
        actor = self._user(user)
        target_id = getattr(body, self.repository.target_field)
        self._valid(body.passport_id, target_id, actor.id)
        try:
            return self.repository.create(body.passport_id, target_id)
        except IntegrityError as error:
            raise ApiError(409, "conflict", f"{self.noun} already collected.") from error

    def update(self, item_id: int, body, user: LoginUser | None):
        actor = self._user(user)
        row = self._found(item_id, actor)
        passport_id = body.passport_id if "passport_id" in body.model_fields_set else row.passport_id
        target_id = (
            getattr(body, self.repository.target_field)
            if self.repository.target_field in body.model_fields_set
            else getattr(row, self.repository.target_field)
        )
        self._valid(passport_id, target_id, actor.id, item_id)
        try:
            return self.repository.update(row, passport_id, target_id)
        except IntegrityError as error:
            raise ApiError(409, "conflict", f"{self.noun} already collected.") from error

    def remove(self, item_id: int, user: LoginUser | None) -> None:
        self.repository.remove(self._found(item_id, self._user(user)))

