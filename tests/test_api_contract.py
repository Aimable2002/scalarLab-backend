from app.main import create_app


def test_artifact_authorization_routes_are_registered():
    paths = create_app().openapi()["paths"]

    assert "/api/v1/workspaces/{workspace_id}/experiments" in paths
    assert "/api/v1/workspaces/{workspace_id}/experiments/{experiment_id}/runs" in paths
    assert "/api/v1/workspaces/{workspace_id}/jobs/{job_id}" in paths
    assert "/api/v1/workspaces/{workspace_id}/jobs/{job_id}/cancel" in paths
    assert "/api/v1/workspaces/{workspace_id}/jobs/{job_id}/logs" in paths
    assert "/api/v1/workspaces/{workspace_id}/artifacts/upload-authorizations" in paths
    assert "/api/v1/workspaces/{workspace_id}/artifacts/{artifact_id}/finalize" in paths
    assert "/api/v1/workspaces/{workspace_id}/artifacts/{artifact_id}/download-authorization" in paths