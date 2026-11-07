from app.domain.shared.errors import DomainError


class InvalidCategory(DomainError):
    default_message = "The category is not valid"


class CategoryAlreadyExists(DomainError):
    default_message = "A category with this name already exists"
