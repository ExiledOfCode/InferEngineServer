from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class InferenceModelSelectRequest(BaseModel):
    model_id: str


class InferenceEngineOptionResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    enabled: bool
    default_enabled: bool
    requires_restart: bool = False
    supported: bool = True


class InferenceEngineOptionsResponse(BaseModel):
    current_model_id: Optional[str] = None
    current_model_name: Optional[str] = None
    current_model_family: Optional[str] = None
    running: bool = False
    ready: bool = False
    trace_enabled: bool = True
    warmup_on_model_switch: bool = True
    max_new_tokens: int = 128
    default_max_new_tokens: int = 128
    min_max_new_tokens: int = 16
    max_max_new_tokens: int = 2048
    runtime_options_path: Optional[str] = None
    options: List[InferenceEngineOptionResponse] = Field(default_factory=list)


class InferenceEngineOptionsUpdateRequest(BaseModel):
    options: Dict[str, bool] = Field(default_factory=dict)
    max_new_tokens: Optional[int] = None
