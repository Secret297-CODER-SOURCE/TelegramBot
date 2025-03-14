from sqlalchemy.ext.asyncio import AsyncSession,async_sessionmaker, create_async_engine
from config import Config

engine = create_async_engine(Config.DATABASE_URL, echo=True)
async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with async_session() as session:
        yield session
