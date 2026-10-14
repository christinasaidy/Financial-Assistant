from app.domain.shared.errors import DomainError


class BudgetNotFound(DomainError):
    default_message = "There is no budget for this category"


class InvalidBudget(DomainError):
    default_message = "The budget is not valid"
