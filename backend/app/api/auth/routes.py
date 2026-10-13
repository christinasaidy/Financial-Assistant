from fastapi import APIRouter, Depends, status

from app.api.auth.schemas import LoginBody, RegisterBody, TokenOut, UserOut
from app.api.container import Container
from app.api.dependencies import get_container, get_current_user_id
from app.application.auth.dtos import LoginRequest, RegisterRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserOut)
def register(body: RegisterBody, container: Container = Depends(get_container)) -> UserOut:
    user = container.auth.register(RegisterRequest(email=body.email, password=body.password))
    return UserOut(id=user.id, email=user.email)


@router.post("/login", response_model=TokenOut)
def login(body: LoginBody, container: Container = Depends(get_container)) -> TokenOut:
    result = container.auth.login(LoginRequest(email=body.email, password=body.password))
    return TokenOut(
        access_token=result.access_token,
        expires_in=result.expires_in,
        user=UserOut(id=result.user.id, email=result.user.email),
    )


@router.get("/me", response_model=UserOut)
def me(
    user_id: int = Depends(get_current_user_id), container: Container = Depends(get_container)
) -> UserOut:
    user = container.auth.get_current_user(user_id)
    return UserOut(id=user.id, email=user.email)
