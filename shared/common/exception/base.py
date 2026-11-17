from shared.common.exception.codes import ErrorCode


class AppException(Exception):
    default_code = ErrorCode.INTERNAL
    default_http_status = 500

    def __init__(
        self,
        message: str,
        code: ErrorCode | None = None,
        http_status: int | None = None,
    ):
        self.code = code if code is not None else self.default_code
        self.message = message
        self.http_status = http_status if http_status is not None else self.default_http_status
        super().__init__(message)


class BadRequestError(AppException):
    default_code = ErrorCode.BAD_REQUEST
    default_http_status = 400


class UnauthorizedError(AppException):
    default_code = ErrorCode.UNAUTHORIZED
    default_http_status = 401


class ForbiddenError(AppException):
    default_code = ErrorCode.FORBIDDEN
    default_http_status = 403


class NotFoundError(AppException):
    default_code = ErrorCode.NOT_FOUND
    default_http_status = 404


class InternalError(AppException):
    default_code = ErrorCode.INTERNAL
    default_http_status = 500


class LLMUnavailableError(AppException):
    default_code = ErrorCode.LLM_UNAVAILABLE
    default_http_status = 503
