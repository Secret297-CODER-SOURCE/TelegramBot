import os
import re
import asyncio
from aiogram import Router, types
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError, UserNotParticipantError, UserBannedInChannelError,
    AuthKeyUnregisteredError, ChatWriteForbiddenError, ChannelPrivateError
)
from telethon.tl.functions.channels import LeaveChannelRequest
from telethon.tl.functions.messages import CheckChatInviteRequest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from db.sessions import get_db
from db.models import TelegramSession
from bot.logger import logger

router = Router()
SESSIONS_PATH = "sessions/"

# 🔹 Регулярное выражение (поддерживает `+invite_link`)
VALID_LINK_REGEX = re.compile(r"https://t\.me/[\w+]+")


def extract_link(message: types.Message):
    """ 🔍 Извлекает ссылку из текста, вложенного сообщения или предпросмотра """
    link = None

    # 1️⃣ Проверяем текст сообщения
    if message.text:
        link = message.text.strip()

    # 2️⃣ Проверяем пересланное сообщение
    elif message.reply_to_message and message.reply_to_message.text:
        link = message.reply_to_message.text.strip()

    # 3️⃣ Проверяем вложенные ссылки (кнопки или предпросмотр)
    elif message.entities:
        for entity in message.entities:
            if entity.type == "url":
                link = message.text[entity.offset:entity.offset + entity.length]

    # Убираем мусор типа ?start=...
    if link:
        link = re.sub(r"\?.*", "", link)

    return link if link and VALID_LINK_REGEX.match(link) else None


async def unsubscribe_group(message: types.Message):
    """ 🚫 Отписывает все аккаунты от указанного канала (поддерживает закрытые и открытые группы) """
    group_link = extract_link(message)

    if not group_link:
        await message.answer(
            "❌ Введите **корректную** ссылку на Telegram-группу (пример: https://t.me/example_channel или https://t.me/+invite_link)")
        return

    await message.answer(f"🔍 Начинаю отписку аккаунтов от {group_link}...")

    successful_unsubs = 0
    failed_unsubs = 0

    async for db in get_db():
        sessions = await db.execute(select(TelegramSession))
        sessions = sessions.scalars().all()

        if not sessions:
            await message.answer("⚠ Нет доступных аккаунтов для отписки.")
            return

        for session in sessions:
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
                            TelegramSession.__table__.delete().where(TelegramSession.user_id == session.user_id))
                        await db.commit()
                        await message.answer(f"🚫 Сессия `{session.session_file}` устарела и удалена из базы.")
                        await client.disconnect()
                        continue

                # 🔥 Получаем username аккаунта
                try:
                    user = await client.get_me()
                    username = user.username if user.username else user.first_name
                except Exception as e:
                    logger.warning(f"⚠ Не удалось получить username: {e}")
                    username = "Неизвестный"

                # 📌 Определяем, это открытая группа, закрытая группа или закрытый канал
                try:
                    if "/+" in group_link:  # 🔥 Если закрытая группа или канал
                        invite_hash = group_link.split("/+")[-1]
                        invite_info = await client(CheckChatInviteRequest(invite_hash))
                        if invite_info.chat:
                            group_id = invite_info.chat.id
                        else:
                            raise ChannelPrivateError("Бот не имеет доступа к каналу")

                    else:  # 🔥 Если открытая группа или канал
                        group_id = group_link

                    # 🚫 Проверяем, можно ли выйти из канала
                    try:
                        await client(LeaveChannelRequest(group_id))
                        successful_unsubs += 1
                        await message.answer(f"✅ Аккаунт **{username}** отписался от {group_link}")

                    except UserNotParticipantError:
                        await message.answer(f"ℹ **{username}** не состоит в {group_link}, пропускаем.")

                except ChannelPrivateError:
                    failed_unsubs += 1
                    await message.answer(
                        f"🚫 **{username}** не может выйти из закрытого канала {group_link}, так как у него нет доступа.")

                except UserBannedInChannelError:
                    failed_unsubs += 1
                    await message.answer(f"🚫 **{username}** заблокирован в {group_link}, не может отписаться.")

                except ChatWriteForbiddenError:
                    failed_unsubs += 1
                    await message.answer(f"🚫 **{username}** не может выходить из {group_link}.")

                except FloodWaitError as e:
                    await message.answer(
                        f"⚠ **Telegram временно заблокировал выход для {username}.** Ждём {e.seconds} секунд...")
                    await asyncio.sleep(e.seconds)

                finally:
                    await client.disconnect()
                    await asyncio.sleep(5)  # Немного ждём между отписками

            except Exception as e:
                failed_unsubs += 1
                await message.answer(f"❌ Ошибка у аккаунта {session.user_id}: {e}")

    await message.answer(f"📊 Отписка завершена:\n"
                         f"✅ Успешно: {successful_unsubs}\n"
                         f"❌ Ошибки: {failed_unsubs}")
