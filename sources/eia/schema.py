from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class EIARow(BaseModel):
    period: str
    respondent: str
    respondent_name: str = Field(alias="respondent-name")
    type: str
    type_name: str = Field(alias="type-name")
    value: str  # API returns strings — cast to float in normalize.py
    value_units: str = Field(alias="value-units")

    model_config = {"populate_by_name": True}


class EIAResponseBody(BaseModel):
    total: str
    date_format: str = Field(alias="dateFormat")
    frequency: str
    data: List[EIARow]
    description: str

    model_config = {"populate_by_name": True}


class EIARawResponse(BaseModel):
    response: EIAResponseBody
    warnings: Optional[List[dict]] = None

    model_config = {"populate_by_name": True}
