from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.container import Container
from app.domain.users.errors import InvalidToken

_bearer = HTTPBearer(auto_error=False)


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    container: Container = Depends(get_container),
) -> int:
    """The id of the signed-in user, taken from a verified bearer token."""
    if credentials is None:
        raise InvalidToken("Not authenticated")
    return container.auth.authenticate(credentials.credentials)
