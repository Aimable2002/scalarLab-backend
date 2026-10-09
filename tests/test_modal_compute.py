from types import SimpleNamespace

import anyio
from functools import partial
from modal.exception import FunctionTimeoutError

from app.adapters.compute.modal import ModalCallState, ModalComputeAdapter
from app.core.config import Settings


class FakeFunction:
    def __init__(self, call):
        self.call = call
        self.payload = None

    def spawn(self, payload):
        self.payload = payload
        return self.call


class FakeCall:
    object_id = "fc-123"

    def __init__(self, output=None, error=None):
        self.output = output
        self.error = error
        self.cancelled = False

    def get(self, timeout=None):
        if self.error:
            raise self.error
        return self.output

    def cancel(self, terminate_containers=False):
        self.cancelled = terminate_containers

    @property
    def logs(self):
        return SimpleNamespace(tail=self.tail)

    async def tail(self, entries=100):
        yield SimpleNamespace(
            timestamp=SimpleNamespace(isoformat=lambda: "2026-10-09T00:00:00+00:00"),
            source="stdout",
            message="training started",
        )


def make_adapter(call):
    function = FakeFunction(call)
    adapter = ModalComputeAdapter(
        "scalar-lab", "execute-job", function_lookup=lambda app, name: function,
        call_lookup=lambda call_id: call,
    )
    return adapter, function


def test_modal_adapter_submits_and_tracks_a_call():
    call = FakeCall(output={"artifact_id": "model-1"})
    adapter, function = make_adapter(call)

    provider_job_id = adapter.submit({"job_id": "job-1"})
    result = adapter.status(provider_job_id)

    assert provider_job_id == "fc-123"
    assert function.payload == {"job_id": "job-1"}
    assert result.state == ModalCallState.SUCCEEDED
    assert result.output == {"artifact_id": "model-1"}


def test_modal_adapter_uses_configured_app_and_function_names():
    adapter = ModalComputeAdapter.from_settings(
        Settings(
            modal_app_name="scalar-lab",
            modal_function_name="execute-job",
            _env_file=None,
        )
    )

    assert adapter.app_name == "scalar-lab"
    assert adapter.function_name == "execute-job"


def test_modal_adapter_reports_running_and_can_cancel():
    call = FakeCall(error=TimeoutError())
    adapter, _ = make_adapter(call)

    result = adapter.status("fc-123")
    adapter.cancel("fc-123")

    assert result.state == ModalCallState.RUNNING
    assert call.cancelled is True


def test_modal_function_timeout_is_terminal():
    adapter, _ = make_adapter(FakeCall(error=FunctionTimeoutError("time limit exceeded")))

    result = adapter.status("fc-123")

    assert result.state == ModalCallState.TIMED_OUT


def test_modal_adapter_reads_bounded_tail_logs():
    adapter, _ = make_adapter(FakeCall())

    logs = anyio.run(partial(adapter.tail_logs, "fc-123", entries=10))

    assert logs == [
        {
            "timestamp": "2026-10-09T00:00:00+00:00",
            "source": "stdout",
            "message": "training started",
        }
    ]