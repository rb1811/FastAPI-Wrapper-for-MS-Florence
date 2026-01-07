import os
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from app.logging_config import get_logger

logger = get_logger(__name__)

_db_initialized = False

async def init_db(db_url: str):
    """Initializes the database schema if not already done."""
    global _db_initialized
    if _db_initialized: 
        return
    
    # Masking password for logs
    display_url = db_url.split('@')[-1] if '@' in db_url else db_url
    logger.info("Initializing database schema", db_url=display_url)
    
    commands = [
        """CREATE TABLE IF NOT EXISTS users ("id" UUID PRIMARY KEY, "identifier" TEXT NOT NULL UNIQUE, "metadata" JSONB NOT NULL, "createdAt" TEXT);""",
        """CREATE TABLE IF NOT EXISTS threads ("id" UUID PRIMARY KEY, "createdAt" TEXT, "name" TEXT, "userId" UUID, "userIdentifier" TEXT, "tags" TEXT[], "metadata" JSONB, FOREIGN KEY ("userId") REFERENCES users("id") ON DELETE CASCADE);""",
        """CREATE TABLE IF NOT EXISTS steps ( "id" UUID PRIMARY KEY, "name" TEXT NOT NULL, "type" TEXT NOT NULL, "threadId" UUID NOT NULL, "parentId" UUID, "streaming" BOOLEAN NOT NULL, "waitForResult" BOOLEAN, "isError" BOOLEAN, "metadata" JSONB, "input" TEXT, "output" TEXT, "createdAt" TEXT, "start" TEXT, "end" TEXT, "generation" JSONB, "showInput" TEXT, "language" TEXT, "indent" INTEGER, "waitForAnswer" BOOLEAN DEFAULT FALSE, "defaultOpen" BOOLEAN DEFAULT FALSE, FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE );""",
        """CREATE TABLE IF NOT EXISTS elements ("id" UUID PRIMARY KEY, "threadId" UUID, "type" TEXT, "url" TEXT, "chainlitKey" TEXT, "name" TEXT NOT NULL, "display" TEXT, "objectKey" TEXT, "size" TEXT, "page" INTEGER, "language" TEXT, "forId" UUID, "mime" TEXT, "metadata" JSONB, FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE);""",
        """CREATE TABLE IF NOT EXISTS feedbacks ("id" UUID PRIMARY KEY, "forId" UUID NOT NULL, "threadId" UUID NOT NULL, "value" INTEGER NOT NULL, "comment" TEXT);"""
    ]
    
    engine = create_async_engine(db_url)
    try:
        async with engine.begin() as conn:
            for cmd in commands: 
                await conn.execute(text(cmd))
        _db_initialized = True
        logger.info("Database schema verified/initialized successfully ✅")
    except Exception as e:
        logger.exception("Database initialization failed", error=str(e))
        raise e
    finally:
        await engine.dispose()

def get_data_layer(storage_client):
    """Factory function to create the SQLAlchemy data layer."""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        logger.info("Configuring SQLAlchemy Data Layer")
        # Initialize DB synchronously for Chainlit's data_layer hook
        asyncio.run(init_db(database_url))
        return SQLAlchemyDataLayer(conninfo=database_url, storage_provider=storage_client)
    
    logger.warning("DATABASE_URL not found, running without persistence")
    return None