from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.errors import ApiError


def get_session(request: Request) -> Generator[Session, None, None]:
    engine = request.app.state.engine
    if engine is None:
        raise ApiError(503, "database_not_configured", "Supabase database is not configured")
    with Session(engine) as session:
        yield session