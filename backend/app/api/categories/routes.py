from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.container import Container
from app.api.dependencies import get_container, get_current_user_id

router = APIRouter(prefix="/categories", tags=["categories"])


class CategoryOut(BaseModel):
    id: int
    name: str
    is_shared: bool


@router.get("", response_model=list[CategoryOut])
def list_categories(
    user_id: int = Depends(get_current_user_id), container: Container = Depends(get_container)
) -> list[CategoryOut]:
    return [CategoryOut(**vars(category)) for category in container.categories.list_all.execute(user_id)]
