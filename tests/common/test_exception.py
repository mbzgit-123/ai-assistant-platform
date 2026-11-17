import pytest

from shared.common.exception.base import AppException, InternalError, NotFoundError
from shared.common.exception.codes import ErrorCode


def test_error_code_values():
    assert ErrorCode.SUCCESS == 0
    assert ErrorCode.NOT_FOUND == 40400
    assert ErrorCode.INTERNAL == 50000


def test_not_found_defaults():
    e = NotFoundError("chapter not found")
    assert e.code == ErrorCode.NOT_FOUND
    assert e.message == "chapter not found"
    assert e.http_status == 404


def test_is_exception():
    with pytest.raises(AppException):
        raise InternalError("boom")
