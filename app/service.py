from .errors import ApiError


class CrudService:
    def __init__(self, repository, name: str) -> None:
        self.repository = repository
        self.name = name

    def list(self, _user=None):
        return self.repository.list()

    def get(self, item_id: int, _user=None):
        row = self.repository.get(item_id)
        if not row:
            raise ApiError(404, "not_found", f"{self.name} not found.")
        return row

    def create(self, body, _user=None):
        return self.repository.create(body)

    def update(self, item_id: int, body, user=None):
        return self.repository.update(self.get(item_id, user), body)

    def remove(self, item_id: int, user=None) -> None:
        self.repository.remove(self.get(item_id, user))

