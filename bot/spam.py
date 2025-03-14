import os
import asyncio
from aiogram import types
from telethon import TelegramClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from db.sessions import get_db
from db.models import TelegramSession

async def start_spam(message: types.Message):
    """ 📩 Запускает массовую рассылку """
    spam_text = message.text.strip()
    sent_count = 0
    failed_count = 0

    async for db in get_db():
        sessions = await db.execute(select(TelegramSession))
        sessions = sessions.scalars().all()

        if not sessions:
            await message.answer("⚠ Нет доступных аккаунтов для рассылки.")
            return

        for session in sessions:
            try:
                session_file_path = os.path.join("sessions/", session.session_file)
                client = TelegramClient(session_file_path, session.api_id, session.api_hash)
                await client.connect()

                if not await client.is_user_authorized():
                    failed_count += 1
                    await message.answer(f"🚫 Аккаунт {session.user_id} не авторизован.")
                    continue

                dialogs = await client.get_dialogs()
                groups = [dialog for dialog in dialogs if dialog.is_group]

                for group in groups:
                    try:
                        await client.send_message(group.id, spam_text)
                        sent_count += 1
                        await asyncio.sleep(2)  # Немного ждем между отправками
                    except Exception as e:
                        failed_count += 1
                        await message.answer(f"⚠ Ошибка при отправке в {group.title}: {e}")

            except Exception as e:
                failed_count += 1
                await message.answer(f"❌ Ошибка у аккаунта {session.user_id}: {e}")

    await message.answer(f"📊 Рассылка завершена:\n"
                         f"✅ Успешно отправлено: {sent_count}\n"
                         f"❌ Ошибки: {failed_count}")
