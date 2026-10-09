from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_endpoints_report_liveness_and_unconfigured_database():
    app = create_app(Settings(_env_file=None))

    with TestClient(app) as client:
        live_response = client.get("/health/live")
        ready_response = client.get("/health/ready")

    assert live_response.status_code == 200
    assert live_response.json() == {"status": "alive"}
    assert ready_response.status_code == 503
    assert ready_response.json() == {"status": "not_ready", "database": "not_configured"}
    assert live_response.headers["X-Request-ID"]