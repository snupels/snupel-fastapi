from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session


class CrudRepository:
    def __init__(self, session: Session, model: type, values) -> None:
        self.session = session
        self.model = model
        self.values = values

    def list(self) -> list:
        return list(self.session.scalars(select(self.model).order_by(self.model.id)))

    def get(self, item_id: int):
        return self.session.get(self.model, item_id)

    def create(self, body):
        row = self.model(**self.values(body))
        self.session.add(row)
        self.session.flush()
        self.session.refresh(row)
        return row

    def update(self, row, body):
        for key, value in self.values(body).items():
            setattr(row, key, value)
        self.session.flush()
        self.session.refresh(row)
        return row

    def remove(self, row) -> None:
        self.session.delete(row)
        self.session.flush()


def dumped(body) -> dict[str, Any]:
    return body.model_dump(exclude_unset=True)

