import os
import re
import asyncio
from aiogram import Router, types
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError, UserNotParticipantError, UserBannedInChannelError,
    AuthKeyUnregisteredError, ChatWriteForbiddenError, ChannelPrivateError
)
from telethon.tl.functions.channels import LeaveChannelRequest, GetParticipantRequest
from telethon.tl.functions.messages import CheckChatInviteRequest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from db.sessions import get_db
from db.models import TelegramSession
from bot.logger import logger

router = Router()
SESSIONS_PATH = "sessions/"

# Регулярное выражение для валидных ссылок (поддерживает +invite_link)
VALID_LINK_REGEX = re.compile(r"https://t\.me/[\w+]+")

def extract_link(message: types.Message):
    """ Извлекает ссылку из текста, вложенного сообщения или предпросмотра """
    link = None
    if message.text:
        link = message.text.strip()
    elif message.reply_to_message and message.reply_to_message.text:
        link = message.reply_to_message.text.strip()
    elif message.entities:
        for entity in message.entities:
            if entity.type == "url":
                link = message.text[entity.offset:entity.offset + entity.length]
    if link:
        # Убираем параметры, например ?start=...
        link = re.sub(r"\?.*", "", link)
    return link if link and VALID_LINK_REGEX.match(link) else None

async def unsubscribe_group(message: types.Message, count, interval, randomize, random_range, group_link):
    """
    Отписывает указанное количество аккаунтов от группы/канала с заданными интервалами и рандомизацией.
    """
    await message.answer(f"🔍 Начинаю отписку {count} аккаунтов от {group_link}...")
    successful_unsubs = 0
    failed_unsubs = 0

    async for db in get_db():
        sessions_result = await db.execute(select(TelegramSession))
        sessions = sessions_result.scalars().all()

        if not sessions:
            await message.answer("⚠ Нет доступных аккаунтов для отписки.")
            return

        for session in sessions:
            if successful_unsubs >= count:
                break  # Завершаем, если достигли нужного количества отписок

            try:
                session_file_path = os.path.join(SESSIONS_PATH, session.session_file)
                if not os.path.exists(session_file_path):
                    failed_unsubs += 1
                    await message.answer(f"🚫 Файл сессии `{session.session_file}` не найден, пропускаем.")
                    continue

                client = TelegramClient(session_file_path, session.api_id, session.api_hash)
                await client.connect()

                if not await client.is_user_authorized():
                    try:
                        logger.warning(f"🔄 Аккаунт {session.user_id} не активен. Пробуем повторную авторизацию...")
                        await client.start()
                    except AuthKeyUnregisteredError:
                        failed_unsubs += 1
                        await db.execute(
                            TelegramSession.__table__.delete().where(TelegramSession.user_id == session.user_id)
                        )
                        await db.commit()
                        await message.answer(f"🚫 Сессия `{session.session_file}` устарела и удалена из базы.")
                        await client.disconnect()
                        continue

                # Выполняем выход из группы
                try:
                    await client(LeaveChannelRequest(group_link))
                    successful_unsubs += 1
                    user = await client.get_me()
                    username = user.username if user.username else user.first_name
                    await message.answer(f"✅ Аккаунт **{username}** отписался от {group_link}.")
                except UserNotParticipantError:
                    await message.answer(f"ℹ Аккаунт {session.user_id} не состоит в {group_link}, пропускаем.")
                except Exception as e:
                    failed_unsubs += 1
                    await message.answer(f"❌ Ошибка у аккаунта {session.user_id}: {e}")
                finally:
                    await client.disconnect()

                # Устанавливаем интервал перед следующей отпиской
                if successful_unsubs < count:
                    sleep_time = interval
                    if randomize:
                        sleep_time += random.randint(-random_range, random_range)
                        sleep_time = max(sleep_time, 0)  # Интервал не может быть отрицательным
                    await asyncio.sleep(sleep_time)

            except Exception as e:
                failed_unsubs += 1
                await message.answer(f"❌ Общая ошибка: {e}")

    await message.answer(
        f"📊 Отписка завершена:\n✅ Успешно: {successful_unsubs}\n❌ Ошибки: {failed_unsubs}"
    )


async def show_unsubscribe_info(message: types.Message):
    """
    Проверяет, сколько аккаунтов доступны для отписки от указанной группы.
    Функция использует extract_link для получения ссылки и затем для каждого аккаунта
    проверяет, состоит ли он в группе. Если да – увеличивает счётчик.
    """
    group_link = extract_link(message)
    if not group_link:
        await message.answer(
            "❌ Введите **корректную** ссылку на Telegram-группу для проверки отписки."
        )
        return

    async for db in get_db():
        sessions_result = await db.execute(select(TelegramSession))
        sessions = sessions_result.scalars().all()

        if not sessions:
            await message.answer("⚠️ Нет доступных аккаунтов для проверки отписки.")
            return

        unsubscribable = 0
        for session in sessions:
            try:
                session_file_path = os.path.join(SESSIONS_PATH, session.session_file)
                if not os.path.exists(session_file_path):
                    continue

                client = TelegramClient(session_file_path, session.api_id, session.api_hash)
                await client.connect()

                if not await client.is_user_authorized():
                    await client.disconnect()
                    continue

                # Если аккаунт состоит в группе, увеличиваем счётчик
                await client(GetParticipantRequest(group_link, 'me'))
                unsubscribable += 1
                await client.disconnect()

            except Exception:
                # Если произошла ошибка (например, аккаунт не состоит в группе) – пропускаем
                continue

        await message.answer(f"👥 Доступно для отписки: {unsubscribable} аккаунтов.")
