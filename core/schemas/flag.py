from datetime import datetime
from pydantic import BaseModel


class FlagRead(BaseModel):
    id: int
    record_id: int
    flag_type: str
    severity: str
    detail: dict | None
    created_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: str | None

    model_config = {"from_attributes": True}


class FlagAcknowledge(BaseModel):
    note: str | None = None


class PaginatedFlags(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[FlagRead]