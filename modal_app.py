import os

import modal

from app.modules.methods.forex_job import execute_forex_baseline_job


gpu_type = os.environ.get("MODAL_GPU_TYPE")
if not gpu_type:
    raise RuntimeError("Set MODAL_GPU_TYPE to a verified Modal GPU type before deployment")

app_name = os.environ.get("MODAL_APP_NAME", "scalar-lab")
function_name = os.environ.get("MODAL_FUNCTION_NAME", "execute-job")
worker_secret_name = os.environ.get(
    "MODAL_WORKER_SECRET_NAME", "scalar-lab-worker-secrets"
)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "huggingface_hub>=0.30,<1",
        "httpx>=0.28,<1",
        "joblib>=1.4,<2",
        "numpy>=1.26,<3",
        "pandas>=2.2,<3",
        "pyarrow>=18,<25",
        "scikit-learn>=1.6,<2",
    )
    .add_local_python_source("app")
)

app = modal.App(app_name)


@app.function(
    name=function_name,
    image=image,
    gpu=gpu_type,
    secrets=[modal.Secret.from_name(worker_secret_name)],
    timeout=3600,
    single_use_containers=True,
)
def execute_job(payload: dict[str, object]) -> dict[str, object]:
    return execute_forex_baseline_job(payload)