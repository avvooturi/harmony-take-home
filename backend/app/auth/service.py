from fastapi import HTTPException
from ..models import Employee


class AuthorizationService:
    @staticmethod
    def require(employee: Employee, permission: str) -> None:
        if permission not in employee.permissions:
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")
