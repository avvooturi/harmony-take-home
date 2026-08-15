from dataclasses import dataclass
from typing import Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..auth.service import AuthorizationService
from ..connectors.erp import ERPConnector
from ..models import AuditEvent, Employee


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    permission: str
    classification: str
    risk: str
    approval_required: bool
    input_schema: dict
    handler: Callable


class ToolRegistry:
    def __init__(self, db: Session):
        erp = ERPConnector(db)
        self.db = db
        self.tools = {
            "get_inventory": Tool("get_inventory", "Read projected inventory", "inventory.read", "READ", "LOW", False,
                                  {"part_id": "string"}, erp.inventory),
            "change_purchase_order_supplier": Tool("change_purchase_order_supplier", "Change a PO supplier", "purchase_order.write", "WRITE", "HIGH", True,
                                                   {"po_id": "string", "supplier_id": "string", "expected_version": "integer", "key": "string"}, erp.change_supplier),
        }

    def invoke(self, employee: Employee, name: str, args: dict, approved: bool = False, run_id: str | None = None) -> dict:
        tool = self.tools.get(name)
        if not tool:
            raise HTTPException(404, "Unknown tool")
        allowed = tool.permission in employee.permissions
        self.db.add(AuditEvent(run_id=run_id, employee_id=employee.id, event_type="TOOL_AUTHORIZATION",
                               details={"tool": name, "permission": tool.permission, "allowed": allowed}))
        self.db.commit()
        AuthorizationService.require(employee, tool.permission)
        if tool.approval_required and not approved:
            raise HTTPException(409, "Human approval required")
        return tool.handler(**args)
