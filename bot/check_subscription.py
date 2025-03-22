import os
import asyncio
import random
from aiogram import types
from telethon import TelegramClient
from telethon.errors import ChatAdminRequiredError
from telethon.tl.functions.channels import GetParticipantRequest, LeaveChannelRequest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from db.sessions import get_db
from db.models import TelegramSession


async def check_subscription(message: types.Message):
    """ 🔍 Проверяет, сколько аккаунтов подписаны и сколько свободны для подписки """
    group_link = message.text.strip()

    async for db in get_db():
        sessions = await db.execute(select(TelegramSession))
        sessions = sessions.scalars().all()

        if not sessions:
            await message.answer("⚠ Нет доступных аккаунтов для проверки.")
            return

        subscribed = 0
        unsubscribed = 0
        for session in sessions:
            try:
                session_file_path = os.path.join("sessions/", session.session_file)
                client = TelegramClient(session_file_path, session.api_id, session.api_hash)
                await client.connect()

                if not await client.is_user_authorized():
                    continue

                await client(GetParticipantRequest(group_link, session.user_id))
                subscribed += 1
            except ChatAdminRequiredError:
                unsubscribed += 1
            except Exception as e:
                print(f"Ошибка у {session.user_id}: {e}")

        await message.answer(f"🟢 {unsubscribed} свободных для подписки.\n🔴 {subscribed} уже подписаны.")


async def unsubscribe_accounts(message: types.Message, count: int, interval: int, randomize: bool):
    """ 🔄 Отписывает аккаунты от канала с заданным интервалом """
    group_link = message.text.strip()

    async for db in get_db():
        sessions = await db.execute(select(TelegramSession))
        sessions = sessions.scalars().all()

        if not sessions:
            await message.answer("⚠ Нет доступных аккаунтов для отписки.")
            return

        unsubscribed_count = 0
        for session in sessions:
            if unsubscribed_count >= count:
                break
            try:
                session_file_path = os.path.join("sessions/", session.session_file)
                client = TelegramClient(session_file_path, session.api_id, session.api_hash)
                await client.connect()

                if not await client.is_user_authorized():
                    continue

                await client(LeaveChannelRequest(group_link))
                unsubscribed_count += 1
                await message.answer(f"🚀 {session.user_id} отписался!")

                wait_time = interval
                if randomize:
                    wait_time += random.randint(-10, 10)  # Рандомизация ±10 минут
                await asyncio.sleep(wait_time * 60)  # Интервал в минутах
            except Exception as e:
                await message.answer(f"⚠ Ошибка у {session.user_id}: {e}")

        await message.answer(f"✅ Отписано {unsubscribed_count} аккаунтов!")