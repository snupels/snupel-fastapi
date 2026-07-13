from sqlalchemy.orm import Session

from app.models import Activity
from app.repository import CrudRepository, dumped


class ActivityRepository(CrudRepository):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Activity, self._values)

    @staticmethod
    def _values(body):
        values = dumped(body)
        if values.get("representative_image_url") is not None:
            values["representative_image_url"] = str(values["representative_image_url"])
        return values
