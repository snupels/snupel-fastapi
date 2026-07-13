from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Course
from app.repository import CrudRepository, dumped


class CourseRepository(CrudRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Course, self._values)

    @staticmethod
    def _values(body):
        values = dumped(body)
        if values.get("representative_image_url") is not None:
            values["representative_image_url"] = str(values["representative_image_url"])
        return values
