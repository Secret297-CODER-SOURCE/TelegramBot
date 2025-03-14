import os
from aiogram import types
from telethon import TelegramClient
from telethon.errors import ChatAdminRequiredError
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import ChannelParticipantsSearch
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from db.sessions import get_db
from db.models import TelegramSession

async def check_subscription(message: types.Message):
    """ 🔍 Проверяет, подписаны ли аккаунты на канал """
    group_link = message.text.strip()

    async for db in get_db():
        sessions = await db.execute(select(TelegramSession))
        sessions = sessions.scalars().all()

        if not sessions:
            await message.answer("⚠ Нет доступных аккаунтов для проверки.")
            return

        results = []
        for session in sessions:
            try:
                session_file_path = os.path.join("sessions/", session.session_file)
                client = TelegramClient(session_file_path, session.api_id, session.api_hash)
                await client.connect()

                if not await client.is_user_authorized():
                    await message.answer(f"🚫 Аккаунт {session.user_id} не авторизован.")
                    continue

                participant = await client(GetParticipantRequest(group_link, session.user_id))
                results.append(f"✅ **{session.user_id}** подписан")

            except ChatAdminRequiredError:
                results.append(f"🚫 **{session.user_id}** не подписан")
            except Exception as e:
                results.append(f"⚠ Ошибка у **{session.user_id}**: {e}")

        await message.answer("\n".join(results))
