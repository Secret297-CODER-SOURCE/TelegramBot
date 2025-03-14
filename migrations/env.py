import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from db.models import Base  # Импортируй свои модели

# Читаем конфигурацию Alembic
config = context.config

# Настраиваем логирование
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Указываем метадату моделей
target_metadata = Base.metadata

# Создаем асинхронный движок
def get_async_engine():
    return async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

# Функция для запуска миграций в асинхронном режиме
async def run_migrations_online():
    connectable = get_async_engine()

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

# Функция для выполнения миграций
def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )
    with context.begin_transaction():
        context.run_migrations()

# Запускаем асинхронные миграции
asyncio.run(run_migrations_online())
