from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class OperatorChoiceResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    supported: bool = True
    default_selected: bool = False


class OperatorGroupResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    selected: str
    default_selected: Optional[str] = None
    requires_restart: bool = True
    choices: List[OperatorChoiceResponse] = Field(default_factory=list)


class OperatorOptionsResponse(BaseModel):
    running: bool = False
    ready: bool = False
    runtime_options_path: Optional[str] = None
    groups: List[OperatorGroupResponse] = Field(default_factory=list)


class OperatorOptionsUpdateRequest(BaseModel):
    operators: Dict[str, str] = Field(default_factory=dict)
