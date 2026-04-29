"""文件说明：推理服务子包入口，导出异常类型和全局推理服务实例。"""

from .errors import InferenceCancelledError
from .service import InferenceService, inference_service

__all__ = ["InferenceCancelledError", "InferenceService", "inference_service"]
