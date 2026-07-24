from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


# asyncpg only understands `ssl` as a connect() kwarg, not the libpq-style
# `sslmode`/`channel_binding` query params Neon's copy-pasteable connection
# string uses - SQLAlchemy's asyncpg dialect forwards URL query params
# straight through, so `?sslmode=require` raises "connect() got an
# unexpected keyword argument 'sslmode'" (sqlalchemy/sqlalchemy#6275).
# Strip those out of the URL and pass SSL via connect_args instead, so a
# Neon connection string can be pasted in verbatim. Shared with
# alembic/env.py so migrations hit the same fix.
_SSL_QUERY_PARAMS = {"sslmode", "channel_binding", "ssl"}


def build_engine_url_and_connect_args(database_url: str) -> tuple[URL, dict]:
    url = make_url(database_url)
    connect_args: dict = {}
    if url.drivername.endswith("asyncpg") and any(p in url.query for p in _SSL_QUERY_PARAMS):
        url = url.difference_update_query(_SSL_QUERY_PARAMS)
        connect_args["ssl"] = True
    return url, connect_args


settings = get_settings()
_engine_url, _connect_args = build_engine_url_and_connect_args(settings.database_url)

engine = create_async_engine(_engine_url, pool_pre_ping=True, future=True, connect_args=_connect_args)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
