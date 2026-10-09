from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from modal import Function, FunctionCall
from modal.exception import (
    ConnectionError as ModalConnectionError,
    ExecutionError,
    FunctionTimeoutError,
    OutputExpiredError,
    TimeoutError as ModalTimeoutError,
    UserCodeException,
)

from app.core.config import Settings


class ModalCallState(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    LOST = "lost"


@dataclass(frozen=True)
class ModalCallResult:
    state: ModalCallState
    output: Any = None


class ComputeProviderUnavailable(Exception):
    pass


class ModalComputeAdapter:
    def __init__(
        self,
        app_name: str,
        function_name: str,
        function_lookup: Any = Function.from_name,
        call_lookup: Any = FunctionCall.from_id,
    ) -> None:
        if not app_name or not function_name:
            raise ValueError("Modal app and deployed function names are required")
        self.app_name = app_name
        self.function_name = function_name
        self.function_lookup = function_lookup
        self.call_lookup = call_lookup

    @classmethod
    def from_settings(cls, settings: Settings) -> "ModalComputeAdapter":
        if settings.modal_app_name is None or settings.modal_function_name is None:
            raise ValueError("MODAL_APP_NAME and MODAL_FUNCTION_NAME are required")
        return cls(settings.modal_app_name, settings.modal_function_name)

    def submit(self, payload: dict[str, Any]) -> str:
        try:
            function = self.function_lookup(self.app_name, self.function_name)
            call = function.spawn(payload)
        except ModalConnectionError as error:
            raise ComputeProviderUnavailable("Modal is unavailable") from error
        return call.object_id

    def status(self, provider_job_id: str) -> ModalCallResult:
        try:
            output = self.call_lookup(provider_job_id).get(timeout=0)
        except FunctionTimeoutError:
            return ModalCallResult(ModalCallState.TIMED_OUT)
        except OutputExpiredError:
            return ModalCallResult(ModalCallState.LOST)
        except (TimeoutError, ModalTimeoutError):
            return ModalCallResult(ModalCallState.RUNNING)
        except (ExecutionError, UserCodeException):
            return ModalCallResult(ModalCallState.FAILED)
        except ModalConnectionError as error:
            raise ComputeProviderUnavailable("Modal is unavailable") from error
        return ModalCallResult(ModalCallState.SUCCEEDED, output)

    def cancel(self, provider_job_id: str) -> None:
        try:
            self.call_lookup(provider_job_id).cancel(terminate_containers=True)
        except ModalConnectionError as error:
            raise ComputeProviderUnavailable("Modal is unavailable") from error

    async def tail_logs(self, provider_job_id: str, entries: int = 100) -> list[dict[str, str]]:
        if not 1 <= entries <= 500:
            raise ValueError("entries must be between 1 and 500")
        try:
            call = self.call_lookup(provider_job_id)
            result = []
            async for log_entry in call.logs.tail(entries=entries):
                result.append(
                    {
                        "timestamp": log_entry.timestamp.isoformat(),
                        "source": log_entry.source,
                        "message": log_entry.message,
                    }
                )
            return result
        except ModalConnectionError as error:
            raise ComputeProviderUnavailable("Modal is unavailable") from error