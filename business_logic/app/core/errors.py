"""统一错误类型与错误码；detail 保持字符串以兼容现有前端。"""
from __future__ import annotations


class AppError(Exception):
    status = 400
    code = 'invalid_request'

    def __init__(self, detail: str, *, field: str | None = None):
        super().__init__(detail)
        self.detail = detail
        self.field = field


class ValidationError(AppError):
    status = 400
    code = 'invalid_request'


class AuthRequired(AppError):
    status = 401
    code = 'auth_required'


class Forbidden(AppError):
    status = 403
    code = 'forbidden'


class NotFound(AppError):
    status = 404
    code = 'not_found'


class RecordNotFound(NotFound):
    code = 'record_not_found'


class TaskNotFound(NotFound):
    code = 'task_not_found'


class Conflict(AppError):
    status = 409
    code = 'conflict'


class TaskFinished(Conflict):
    code = 'task_finished'


class InputUnavailable(Conflict):
    code = 'input_unavailable'


class PayloadTooLarge(AppError):
    status = 413
    code = 'payload_too_large'


class ServiceUnavailable(AppError):
    status = 503
    code = 'service_unavailable'
