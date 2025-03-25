from sqlalchemy import Column
from sqlalchemy.ext.declarative import declarative_base
from db.models import TelegramSession  # Импорт всех моделей

Base = declarative_base()
proxy_type = Column(String, nullable=False)