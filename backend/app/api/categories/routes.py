from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.api.container import Container
from app.api.dependencies import get_container, get_current_user_id

router = APIRouter(prefix="/categories", tags=["categories"])


class CategoryIn(BaseModel):
    name: str


class CategoryOut(BaseModel):
    id: int
    name: str
    is_shared: bool


@router.get("", response_model=list[CategoryOut])
def list_categories(
    user_id: int = Depends(get_current_user_id), container: Container = Depends(get_container)
) -> list[CategoryOut]:
    return [CategoryOut(**vars(category)) for category in container.categories.list_all(user_id)]


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    body: CategoryIn, user_id: int = Depends(get_current_user_id), container: Container = Depends(get_container)
) -> CategoryOut:
    return CategoryOut(**vars(container.categories.create(user_id, body.name)))
