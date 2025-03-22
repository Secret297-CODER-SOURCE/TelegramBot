from sqlalchemy import Column, BigInteger, String, ForeignKey,Boolean
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, index=True)  # ✅ ИСПРАВЛЕНО НА BigInteger
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False)
    sessions = relationship("TelegramSession", back_populates="user")

class TelegramSession(Base):
    __tablename__ = "telegram_sessions"

    id = Column(BigInteger, primary_key=True, index=True)  # ✅ ИСПРАВЛЕНО НА BigInteger
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    api_id = Column(BigInteger, nullable=False)  # ✅ API_ID тоже лучше сделать BigInteger
    api_hash = Column(String, nullable=False)
    session_file = Column(String, nullable=False)

    user = relationship("User", back_populates="sessions")
class ProxySettings(Base):
    __tablename__ = "proxy_settings"

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    proxy_type = Column(String, nullable=False)  # socks5, socks4, http
    proxy_host = Column(String, nullable=False)
    proxy_port = Column(BigInteger, nullable=False)
    proxy_login = Column(String, nullable=True)
    proxy_password = Column(String, nullable=True)

    user = relationship("User")