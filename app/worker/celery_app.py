from app.adapters.queue.celery import create_celery_app
from app.core.config import get_settings

settings = get_settings()
if settings.redis_url is None:
    raise RuntimeError("Set REDIS_URL before starting Celery workers")

celery_app = create_celery_app(settings.redis_url.get_secret_value())