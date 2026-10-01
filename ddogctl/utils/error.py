"""Error handling utilities with retry logic."""

from datadog_api_client.exceptions import ApiException
from rich.console import Console
import sys
import time
from functools import wraps
from ddogctl.utils.exit_codes import (
    AUTH_ERROR,
    GENERAL_ERROR,
    NOT_FOUND,
    RATE_LIMITED,
    SERVER_ERROR,
    VALIDATION_ERROR,
    exit_code_for_status,
)

from ddogctl.utils.output import emit_error

console = Console()


def handle_api_error(func):
    """Decorator for API error handling with retry logic."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        retries = 3
        retry_delay = 1.0

        for attempt in range(retries):
            try:
                return func(*args, **kwargs)
            except ApiException as e:
                if e.status == 401:
                    emit_error(
                        "AUTH_FAILED",
                        401,
                        "Authentication failed",
                        "Check DD_PAT (expired?) or DD_API_KEY and DD_APP_KEY, or run ddogctl config init",
                    )
                    sys.exit(AUTH_ERROR)
                elif e.status == 403:
                    emit_error(
                        "PERMISSION_DENIED",
                        403,
                        "Permission denied",
                        "Check key or PAT scopes; intake endpoints (event post, service-check post) need DD_API_KEY",
                    )
                    sys.exit(AUTH_ERROR)
                elif e.status == 404:
                    emit_error(
                        "NOT_FOUND",
                        404,
                        f"Resource not found: {e}",
                        "Verify the resource ID",
                    )
                    sys.exit(NOT_FOUND)
                elif e.status == 429:
                    # Rate limited - retry with exponential backoff
                    if attempt < retries - 1:
                        wait_time = retry_delay * (2**attempt)
                        console.print(f"[yellow]Rate limited. Retrying in {wait_time}s...[/yellow]")
                        time.sleep(wait_time)
                        continue
                    else:
                        emit_error(
                            "RATE_LIMITED",
                            429,
                            "Rate limited after retries",
                            "Try again later or reduce request frequency",
                        )
                        sys.exit(RATE_LIMITED)
                elif e.status >= 500:
                    # Server error - retry
                    if attempt < retries - 1:
                        console.print(
                            f"[yellow]Server error. Retrying ({attempt + 1}/{retries})...[/yellow]"
                        )
                        time.sleep(retry_delay)
                        continue
                    else:
                        emit_error(
                            "SERVER_ERROR",
                            e.status,
                            f"Server error: {e}",
                            "Datadog service issue, try again later",
                        )
                        sys.exit(SERVER_ERROR)
                elif e.status in (400, 422):
                    emit_error(
                        "VALIDATION_ERROR",
                        e.status,
                        f"Validation error ({e.status}): {e}",
                    )
                    sys.exit(VALIDATION_ERROR)
                else:
                    emit_error("API_ERROR", e.status, f"API error: {e}")
                    sys.exit(exit_code_for_status(e.status))
            except Exception as e:
                emit_error("UNEXPECTED_ERROR", 0, f"Unexpected error: {e}")
                sys.exit(GENERAL_ERROR)

    return wrapper
