"""Tests for error handling utilities."""

import json
from io import StringIO

import pytest
from unittest.mock import patch
from datadog_api_client.exceptions import ApiException
from ddogctl.utils.error import handle_api_error
from ddogctl.utils.output import set_output_format
from ddogctl.utils.exit_codes import (
    AUTH_ERROR,
    GENERAL_ERROR,
    NOT_FOUND,
    RATE_LIMITED,
    SERVER_ERROR,
    VALIDATION_ERROR,
)


@pytest.fixture(autouse=True)
def reset_output_format():
    """Reset output format to table after each test."""
    set_output_format("table")
    yield
    set_output_format("table")


class TestHandleApiError:
    """Test suite for handle_api_error decorator."""

    @pytest.fixture
    def mock_console(self):
        """Mock rich Console for capturing retry output."""
        with patch("ddogctl.utils.error.console") as mock:
            yield mock

    @pytest.fixture
    def mock_emit_error(self):
        """Mock emit_error for capturing structured error calls."""
        with patch("ddogctl.utils.error.emit_error") as mock:
            yield mock

    @pytest.fixture
    def mock_sleep(self):
        """Mock time.sleep to avoid delays in tests."""
        with patch("ddogctl.utils.error.time.sleep") as mock:
            yield mock

    def test_successful_call_no_error(self, mock_emit_error):
        """Test that successful function calls work normally."""

        @handle_api_error
        def successful_func():
            return "success"

        result = successful_func()
        assert result == "success"
        mock_emit_error.assert_not_called()

    def test_successful_call_with_args_and_kwargs(self, mock_emit_error):
        """Test that decorator preserves function arguments."""

        @handle_api_error
        def func_with_args(a, b, c=None):
            return f"{a}-{b}-{c}"

        result = func_with_args("x", "y", c="z")
        assert result == "x-y-z"
        mock_emit_error.assert_not_called()

    def test_401_authentication_error(self, mock_emit_error):
        """Test that 401 errors trigger AUTH_FAILED emit_error and exit."""

        @handle_api_error
        def auth_error_func():
            raise ApiException(status=401, reason="Unauthorized")

        with pytest.raises(SystemExit) as exc_info:
            auth_error_func()

        assert exc_info.value.code == AUTH_ERROR
        mock_emit_error.assert_called_once_with(
            "AUTH_FAILED",
            401,
            "Authentication failed",
            "Check DD_PAT (expired?) or DD_API_KEY and DD_APP_KEY, or run ddogctl config init",
        )

    def test_403_permission_error(self, mock_emit_error):
        """Test that 403 errors trigger PERMISSION_DENIED emit_error and exit."""

        @handle_api_error
        def permission_error_func():
            raise ApiException(status=403, reason="Forbidden")

        with pytest.raises(SystemExit) as exc_info:
            permission_error_func()

        assert exc_info.value.code == AUTH_ERROR
        mock_emit_error.assert_called_once_with(
            "PERMISSION_DENIED",
            403,
            "Permission denied",
            "Check key or PAT scopes; intake endpoints (event post, service-check post) need DD_API_KEY",
        )

    def test_404_not_found_error(self, mock_emit_error, mock_sleep):
        """Test that 404 errors trigger NOT_FOUND emit_error and exit."""

        @handle_api_error
        def not_found_func():
            raise ApiException(status=404, reason="Not Found")

        with pytest.raises(SystemExit) as exc_info:
            not_found_func()

        assert exc_info.value.code == NOT_FOUND
        mock_sleep.assert_not_called()
        mock_emit_error.assert_called_once()
        call_args = mock_emit_error.call_args
        assert call_args[0][0] == "NOT_FOUND"
        assert call_args[0][1] == 404
        assert "not found" in call_args[0][2].lower()
        assert call_args[0][3] == "Verify the resource ID"

    def test_429_rate_limit_with_retry(self, mock_console, mock_emit_error, mock_sleep):
        """Test that 429 errors trigger retry with exponential backoff."""
        call_count = 0

        @handle_api_error
        def rate_limited_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ApiException(status=429, reason="Rate Limited")
            return "success"

        result = rate_limited_func()

        # Should succeed on third attempt
        assert result == "success"
        assert call_count == 3

        # Should have slept twice (before 2nd and 3rd attempts)
        assert mock_sleep.call_count == 2

        # Check exponential backoff: 1s * 2^0 = 1s, then 1s * 2^1 = 2s
        sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
        assert sleep_calls == [1.0, 2.0]

        # Retry messages go through console.print (not emit_error)
        assert mock_console.print.call_count >= 2
        print_calls = [c[0][0] for c in mock_console.print.call_args_list]
        rate_limit_warnings = [c for c in print_calls if "Rate limited" in c]
        assert len(rate_limit_warnings) == 2

        # emit_error should NOT be called (all retries succeeded)
        mock_emit_error.assert_not_called()

    def test_429_rate_limit_max_retries_exceeded(self, mock_emit_error, mock_sleep):
        """Test that 429 errors exit after max retries."""

        @handle_api_error
        def always_rate_limited():
            raise ApiException(status=429, reason="Rate Limited")

        with pytest.raises(SystemExit) as exc_info:
            always_rate_limited()

        assert exc_info.value.code == RATE_LIMITED

        # Should have attempted 3 times (initial + 2 retries)
        assert mock_sleep.call_count == 2

        # Final error should go through emit_error
        mock_emit_error.assert_called_once_with(
            "RATE_LIMITED",
            429,
            "Rate limited after retries",
            "Try again later or reduce request frequency",
        )

    def test_500_server_error_with_retry(self, mock_console, mock_emit_error, mock_sleep):
        """Test that 5xx errors trigger retry."""
        call_count = 0

        @handle_api_error
        def server_error_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ApiException(status=500, reason="Internal Server Error")
            return "success"

        result = server_error_func()

        # Should succeed on second attempt
        assert result == "success"
        assert call_count == 2

        # Should have slept once (before 2nd attempt)
        mock_sleep.assert_called_once_with(1.0)

        # Retry messages go through console.print
        print_calls = [c[0][0] for c in mock_console.print.call_args_list]
        server_error_warnings = [c for c in print_calls if "Server error" in c]
        assert len(server_error_warnings) >= 1

        # emit_error should NOT be called (retry succeeded)
        mock_emit_error.assert_not_called()

    def test_503_service_unavailable_retry(self, mock_emit_error, mock_sleep):
        """Test that 503 errors (5xx) trigger retry."""
        call_count = 0

        @handle_api_error
        def service_unavailable_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ApiException(status=503, reason="Service Unavailable")
            return "success"

        result = service_unavailable_func()
        assert result == "success"
        assert call_count == 2
        mock_emit_error.assert_not_called()

    def test_server_error_max_retries_exceeded(self, mock_emit_error, mock_sleep):
        """Test that server errors exit after max retries."""

        @handle_api_error
        def always_server_error():
            raise ApiException(status=500, reason="Internal Server Error")

        with pytest.raises(SystemExit) as exc_info:
            always_server_error()

        assert exc_info.value.code == SERVER_ERROR

        # Should have retried 3 times total
        assert mock_sleep.call_count == 2

        # Final error through emit_error
        mock_emit_error.assert_called_once()
        call_args = mock_emit_error.call_args
        assert call_args[0][0] == "SERVER_ERROR"
        assert call_args[0][1] == 500
        assert "Server error" in call_args[0][2]
        assert call_args[0][3] == "Datadog service issue, try again later"

    def test_400_client_error_no_retry(self, mock_emit_error, mock_sleep):
        """Test that 400 errors are treated as validation errors without retry."""

        @handle_api_error
        def bad_request_func():
            raise ApiException(status=400, reason="Bad Request")

        with pytest.raises(SystemExit) as exc_info:
            bad_request_func()

        assert exc_info.value.code == VALIDATION_ERROR

        # Should NOT retry
        mock_sleep.assert_not_called()

        # Should emit VALIDATION_ERROR
        mock_emit_error.assert_called_once()
        call_args = mock_emit_error.call_args
        assert call_args[0][0] == "VALIDATION_ERROR"
        assert call_args[0][1] == 400

    def test_generic_exception_handling(self, mock_emit_error):
        """Test that non-ApiException errors are caught and logged."""

        @handle_api_error
        def generic_error_func():
            raise RuntimeError("Something went wrong")

        with pytest.raises(SystemExit) as exc_info:
            generic_error_func()

        assert exc_info.value.code == GENERAL_ERROR

        mock_emit_error.assert_called_once()
        call_args = mock_emit_error.call_args
        assert call_args[0][0] == "UNEXPECTED_ERROR"
        assert call_args[0][1] == 0
        assert "Something went wrong" in call_args[0][2]

    def test_preserves_function_metadata(self):
        """Test that decorator preserves function name and docstring."""

        @handle_api_error
        def documented_func():
            """This is a test function."""
            return "test"

        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "This is a test function."

    def test_different_api_exception_messages(self, mock_emit_error):
        """Test that exception messages are included in error output."""

        @handle_api_error
        def custom_error_func():
            raise ApiException(
                status=400,
                reason="Bad Request",
            )

        with pytest.raises(SystemExit) as exc_info:
            custom_error_func()

        assert exc_info.value.code == VALIDATION_ERROR
        call_args = mock_emit_error.call_args
        assert call_args[0][1] == 400

    def test_multiple_function_applications(self, mock_emit_error):
        """Test that decorator can be applied to multiple functions."""

        @handle_api_error
        def func1():
            return "func1"

        @handle_api_error
        def func2():
            return "func2"

        assert func1() == "func1"
        assert func2() == "func2"

        mock_emit_error.assert_not_called()

    def test_nested_decorator_application(self, mock_emit_error):
        """Test behavior when decorator is used with other decorators."""

        def other_decorator(func):
            def wrapper(*args, **kwargs):
                return f"wrapped: {func(*args, **kwargs)}"

            return wrapper

        @handle_api_error
        @other_decorator
        def nested_func():
            return "test"

        result = nested_func()
        assert result == "wrapped: test"

    def test_retry_count_tracking(self, mock_console, mock_sleep):
        """Test that retry attempts are properly tracked in log messages."""
        call_count = 0

        @handle_api_error
        def intermittent_server_error():
            nonlocal call_count
            call_count += 1
            # Fail twice, succeed on third
            if call_count <= 2:
                raise ApiException(status=500, reason="Server Error")
            return "success"

        result = intermittent_server_error()
        assert result == "success"

        # Check that retry messages include attempt numbers
        print_calls = [c[0][0] for c in mock_console.print.call_args_list]
        retry_messages = [c for c in print_calls if "Retrying" in c]

        # Should have 2 retry messages (for attempts 1 and 2)
        assert len(retry_messages) == 2

        # First retry message should show (1/3)
        assert "(1/3)" in retry_messages[0]
        # Second retry message should show (2/3)
        assert "(2/3)" in retry_messages[1]

    def test_exception_with_no_status_attribute(self, mock_emit_error):
        """Test handling of exceptions that don't have a status attribute."""

        # Create a custom exception without status
        class CustomException(Exception):
            pass

        @handle_api_error
        def custom_exception_func():
            raise CustomException("Custom error")

        with pytest.raises(SystemExit) as exc_info:
            custom_exception_func()

        assert exc_info.value.code == GENERAL_ERROR

        # Should be caught as unexpected error via emit_error
        mock_emit_error.assert_called_once()
        call_args = mock_emit_error.call_args
        assert call_args[0][0] == "UNEXPECTED_ERROR"


class TestHandleApiErrorJsonMode:
    """Test that handle_api_error produces structured JSON in JSON mode."""

    @pytest.fixture
    def mock_sleep(self):
        """Mock time.sleep to avoid delays in tests."""
        with patch("ddogctl.utils.error.time.sleep") as mock:
            yield mock

    def test_401_json_output(self):
        """Test 401 error produces JSON on stderr in JSON mode."""
        set_output_format("json")

        @handle_api_error
        def auth_error():
            raise ApiException(status=401, reason="Unauthorized")

        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with pytest.raises(SystemExit) as exc_info:
                auth_error()

        assert exc_info.value.code == AUTH_ERROR
        data = json.loads(mock_stderr.getvalue())
        assert data["error"] is True
        assert data["code"] == "AUTH_FAILED"
        assert data["status"] == 401
        assert (
            data["hint"]
            == "Check DD_PAT (expired?) or DD_API_KEY and DD_APP_KEY, or run ddogctl config init"
        )

    def test_403_json_output(self):
        """Test 403 error produces JSON on stderr in JSON mode."""
        set_output_format("json")

        @handle_api_error
        def perm_error():
            raise ApiException(status=403, reason="Forbidden")

        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with pytest.raises(SystemExit) as exc_info:
                perm_error()

        assert exc_info.value.code == AUTH_ERROR
        data = json.loads(mock_stderr.getvalue())
        assert data["code"] == "PERMISSION_DENIED"
        assert data["status"] == 403

    def test_404_json_output(self):
        """Test 404 error produces JSON on stderr in JSON mode."""
        set_output_format("json")

        @handle_api_error
        def not_found_error():
            raise ApiException(status=404, reason="Not Found")

        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with pytest.raises(SystemExit) as exc_info:
                not_found_error()

        assert exc_info.value.code == NOT_FOUND
        data = json.loads(mock_stderr.getvalue())
        assert data["code"] == "NOT_FOUND"
        assert data["status"] == 404
        assert data["hint"] == "Verify the resource ID"

    def test_429_exhausted_json_output(self, mock_sleep):
        """Test 429 after max retries produces JSON on stderr."""
        set_output_format("json")

        @handle_api_error
        def rate_limited():
            raise ApiException(status=429, reason="Rate Limited")

        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with pytest.raises(SystemExit) as exc_info:
                rate_limited()

        assert exc_info.value.code == RATE_LIMITED
        data = json.loads(mock_stderr.getvalue())
        assert data["code"] == "RATE_LIMITED"
        assert data["status"] == 429

    def test_500_exhausted_json_output(self, mock_sleep):
        """Test 500 after max retries produces JSON on stderr."""
        set_output_format("json")

        @handle_api_error
        def server_error():
            raise ApiException(status=500, reason="Internal Server Error")

        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with pytest.raises(SystemExit) as exc_info:
                server_error()

        assert exc_info.value.code == SERVER_ERROR
        data = json.loads(mock_stderr.getvalue())
        assert data["code"] == "SERVER_ERROR"
        assert data["status"] == 500

    def test_unexpected_error_json_output(self):
        """Test unexpected error produces JSON on stderr."""
        set_output_format("json")

        @handle_api_error
        def unexpected():
            raise RuntimeError("boom")

        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with pytest.raises(SystemExit) as exc_info:
                unexpected()

        assert exc_info.value.code == GENERAL_ERROR
        data = json.loads(mock_stderr.getvalue())
        assert data["code"] == "UNEXPECTED_ERROR"
        assert data["status"] == 0
        assert "boom" in data["message"]
