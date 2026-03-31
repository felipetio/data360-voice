"""Chainlit SQLAlchemy data layer configuration."""

import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer

from app.config import settings


@cl.data_layer
def get_data_layer():
    """Register SQLAlchemy data layer for conversation persistence."""
    conninfo = settings.database_url
    # SQLAlchemy requires +asyncpg in the protocol for async support
    if conninfo and conninfo.startswith("postgresql://") and "+asyncpg" not in conninfo:
        conninfo = conninfo.replace("postgresql://", "postgresql+asyncpg://", 1)
    return SQLAlchemyDataLayer(conninfo=conninfo)
