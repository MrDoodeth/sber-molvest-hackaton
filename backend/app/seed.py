import asyncio

from app.core.config import Settings
from app.core.database import create_database
from app.services.seeds import seed_defaults


async def _main() -> None:
    settings = Settings()
    engine, session_factory = create_database(settings.database_url)
    try:
        await seed_defaults(session_factory)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
