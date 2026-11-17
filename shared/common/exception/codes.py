from enum import IntEnum


class ErrorCode(IntEnum):
    SUCCESS = 0
    BAD_REQUEST = 40000
    UNAUTHORIZED = 40100
    FORBIDDEN = 40300
    NOT_FOUND = 40400
    INTERNAL = 50000
    LLM_UNAVAILABLE = 50001
