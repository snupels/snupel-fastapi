from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Response, status

from app.deps.auth import LoginUser, optional_user, require_admin, require_user
from app.schemas.common import Pagination

Access = Literal["public", "user", "admin"]


def create_crud_router(
    *,
    prefix: str,
    tag: str,
    create_model,
    patch_model,
    response_model,
    service_dependency,
    read_access: Access = "public",
    detail_access: Access | None = None,
    write_access: Access = "admin",
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag])
    dependencies = {"public": optional_user, "user": require_user, "admin": require_admin}
    read_actor = dependencies[read_access]
    detail_actor = dependencies[detail_access or read_access]
    write_actor = dependencies[write_access]

    @router.get("", response_model=list[response_model])
    async def list_items(
        pagination: Annotated[Pagination, Depends()],
        actor: LoginUser | None = Depends(read_actor),
        service: Any = Depends(service_dependency),
    ):
        return await service.list(actor, offset=pagination.offset, limit=pagination.size)

    @router.post("", response_model=response_model, status_code=status.HTTP_201_CREATED)
    async def create_item(
        body: create_model,
        actor: LoginUser | None = Depends(write_actor),
        service: Any = Depends(service_dependency),
    ):
        return await service.create(body, actor)

    @router.get("/{item_id}", response_model=response_model)
    async def get_item(
        item_id: int = Path(gt=0),
        actor: LoginUser | None = Depends(detail_actor),
        service: Any = Depends(service_dependency),
    ):
        return await service.get(item_id, actor)

    @router.patch("/{item_id}", response_model=response_model)
    async def update_item(
        body: patch_model,
        item_id: int = Path(gt=0),
        actor: LoginUser | None = Depends(write_actor),
        service: Any = Depends(service_dependency),
    ):
        return await service.update(item_id, body, actor)

    @router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def remove_item(
        item_id: int = Path(gt=0),
        actor: LoginUser | None = Depends(write_actor),
        service: Any = Depends(service_dependency),
    ) -> Response:
        await service.remove(item_id, actor)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
