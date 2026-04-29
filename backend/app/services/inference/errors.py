"""文件说明：推理服务模块，封装 errors 相关的运行时逻辑并被 InferenceService 组合使用。"""

class InferenceCancelledError(Exception):
    pass
