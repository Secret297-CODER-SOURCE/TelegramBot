import os
import asyncio
from aiogram import types
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError, UserBannedInChannelError, UserAlreadyParticipantError,
    AuthKeyUnregisteredError, InviteRequestSentError, ChatWriteForbiddenError
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from sqlalchemy.future import select
from db.sessions import get_db
from db.models import TelegramSession
from bot.logger import logger

SESSIONS_PATH = "sessions/"

async def join_group(message: types.Message, group_link: str, interval: int):
    """
    Подписывает все аккаунты на указанную группу с заданным интервалом между подписками.
    Поддерживаются как открытые, так и закрытые группы.
    """
    if not group_link.startswith("https://t.me/"):
        await message.answer("❌ Введите корректную ссылку на Telegram-группу (пример: https://t.me/example_channel)")
        return

    await message.answer("🔍 Начинаю подписку аккаунтов...")

    successful_joins = 0
    failed_joins = 0

    async for db in get_db():
        sessions_result = await db.execute(select(TelegramSession))
        sessions = sessions_result.scalars().all()

        if not sessions:
            await message.answer("⚠ Нет доступных аккаунтов для подписки.")
            return

        for session in sessions:
            try:
                session_file_path = os.path.join(SESSIONS_PATH, session.session_file)
                if not os.path.exists(session_file_path):
                    failed_joins += 1
                    await message.answer(f"🚫 Файл сессии `{session.session_file}` не найден, пропускаем.")
                    continue

                client = TelegramClient(session_file_path, session.api_id, session.api_hash)
                await client.connect()

                if not await client.is_user_authorized():
                    try:
                        logger.warning(f"🔄 Аккаунт {session.user_id} не активен. Пробуем повторную авторизацию...")
                        await client.start()
                    except AuthKeyUnregisteredError:
                        failed_joins += 1
                        await db.execute(
                            TelegramSession.__table__.delete().where(TelegramSession.user_id == session.user_id)
                        )
                        await db.commit()
                        await message.answer(f"🚫 Сессия `{session.session_file}` устарела и удалена из базы.")
                        await client.disconnect()
                        continue

                # Обработка подписки на закрытые или открытые группы
                try:
                    # Если ссылка содержит "/+", считаем, что это закрытая группа
                    if "/+" in group_link:
                        invite_hash = group_link.split("/+")[-1]
                        await client(ImportChatInviteRequest(invite_hash))
                    else:
                        await client(JoinChannelRequest(group_link))

                    successful_joins += 1
                    await message.answer(f"✅ Аккаунт {session.user_id} подписался на {group_link}")
                except UserAlreadyParticipantError:
                    await message.answer(f"ℹ Аккаунт {session.user_id} уже подписан на {group_link}")
                except UserBannedInChannelError:
                    failed_joins += 1
                    await message.answer(f"🚫 Аккаунт {session.user_id} заблокирован в {group_link}, пропускаем.")
                except InviteRequestSentError:
                    failed_joins += 1
                    await message.answer(
                        f"📩 Аккаунт {session.user_id} отправил запрос на вступление в {group_link} (закрытая группа).")
                except ChatWriteForbiddenError:
                    failed_joins += 1
                    await message.answer(
                        f"🚫 Аккаунт {session.user_id} не может писать в {group_link}, подписка невозможна.")
                except FloodWaitError as e:
                    await message.answer(
                        f"⚠ Telegram временно заблокировал подписку для аккаунта {session.user_id}. Ждём {e.seconds} секунд...")
                    await asyncio.sleep(e.seconds)
            except Exception as e:
                failed_joins += 1
                await message.answer(f"❌ Ошибка у аккаунта {session.user_id}: {e}")
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass
                await asyncio.sleep(interval)  # Ждем между подписками, используя заданный интервал

    # Отправляем итоговую информацию о подписке
    await message.answer(f"📊 Подписка завершена:\n✅ Успешно: {successful_joins}\n❌ Ошибки: {failed_joins}")
    logger.info(f"Подписка завершена: {successful_joins} успешных, {failed_joins} ошибок")
