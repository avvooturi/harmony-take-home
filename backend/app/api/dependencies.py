from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Employee


def get_current_employee(
    x_employee_id: str = Header(default="emp-pm"), db: Session = Depends(get_db)
) -> Employee:
    employee = db.get(Employee, x_employee_id)
    if not employee:
        raise HTTPException(status_code=401, detail="Unknown demo employee")
    return employee

