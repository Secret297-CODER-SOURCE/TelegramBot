import re
from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeExpiredError,FloodWaitError,PhoneNumberInvalidError
from sqlalchemy import select
from db.sessions import get_db
from db.models import TelegramSession, User
from bot.logger import logger
import os
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

router = Router()
UPLOAD_PATH = "sessions/"
os.makedirs(UPLOAD_PATH, exist_ok=True)

class SessionStates(StatesGroup):
    waiting_for_api_id = State()
    waiting_for_api_hash = State()
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_password = State()

sessions_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Создать сессию")],
        [KeyboardButton(text="📂 Мои сессии")],
        [KeyboardButton(text="⬅ Назад")]
    ],
    resize_keyboard=True
)

@router.message(F.text == "👥 Сессии")
async def sessions_menu(message: types.Message, state: FSMContext):
    await state.set_state(SessionStates.waiting_for_api_id)  # Для совместимости с FSM
    await message.answer("👥 Меню сессий:", reply_markup=sessions_keyboard)

@router.message(F.text == "⬅ Назад")
async def back_to_main_menu(message: types.Message, state: FSMContext):
    from bot.handlers import main_keyboard
    await state.set_state(State())
    await message.answer("🔙 Возвращаюсь в главное меню", reply_markup=main_keyboard)

@router.message(F.text == "➕ Создать сессию")
async def request_api_id(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(SessionStates.waiting_for_api_id)
    await message.answer(
        "📌 Получить API ID и API HASH можно тут:\n"
        "🔗 [My Telegram Apps](https://my.telegram.org/apps)\n\n"
        "✏ Введите API ID:",
        parse_mode="Markdown"
    )

@router.message(StateFilter(SessionStates.waiting_for_api_id))
async def get_api_id(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("Введите корректное число для API_ID.")
        return
    await state.update_data(api_id=int(message.text.strip()))
    await state.set_state(SessionStates.waiting_for_api_hash)
    await message.answer("✏ Введите API HASH:")

@router.message(StateFilter(SessionStates.waiting_for_api_hash))
async def get_api_hash(message: types.Message, state: FSMContext):
    await state.update_data(api_hash=message.text.strip())
    await state.set_state(SessionStates.waiting_for_phone)
    await message.answer("📞 Введите номер телефона:")

@router.message(StateFilter(SessionStates.waiting_for_phone))
async def get_phone_number(message: types.Message, state: FSMContext):
    """ 🔹 Получаем номер телефона и отправляем SMS с кодом """
    phone = message.text.strip()
    if not phone.startswith("+") or not phone[1:].isdigit():
        await message.answer("❌ Введите корректный номер телефона (начинается с `+`).")
        return

    await state.update_data(phone=phone)
    data = await state.get_data()
    api_id = data["api_id"]
    api_hash = data["api_hash"]
    session_name = f"{phone.replace('+', '')}.session"
    session_path = os.path.join(UPLOAD_PATH, session_name)

    client = TelegramClient(session_path, api_id, api_hash)

    try:
        await client.connect()
        if not await client.is_user_authorized():
            logger.info(f"📨 Попытка отправки кода на {phone}...")

            # ✅ Отправляем код
            sent = await client.send_code_request(phone)

            # ✅ Проверяем, есть ли `phone_code_hash`
            if not sent.phone_code_hash:
                logger.error("❌ Telegram не вернул `phone_code_hash`, код НЕ отправлен.")
                await message.answer("❌ Ошибка: Telegram не вернул код подтверждения. Попробуйте снова.")
                return

            # ✅ Логируем `phone_code_hash`
            logger.info(f"📩 Код отправлен! `phone_code_hash`: {sent.phone_code_hash}")

            await state.update_data(phone_code_hash=sent.phone_code_hash)
            await state.set_state(SessionStates.waiting_for_code)
            await message.answer("📨 Код отправлен! Введите его:")

        else:
            await message.answer("✅ Сессия уже активна!")
            await client.disconnect()
            await state.clear()

    except FloodWaitError as e:
        await message.answer(f"⏳ Telegram временно заблокировал отправку кода. Повторите через {e.seconds} секунд.")
        logger.warning(f"❌ FloodWaitError: {e}")

    except PhoneNumberInvalidError:
        await message.answer("❌ Ошибка: Некорректный номер телефона. Проверьте номер и попробуйте снова.")

    except Exception as e:
        logger.error(f"❌ Ошибка отправки кода: {e}")
        await message.answer(f"❌ Ошибка: {e}\nПопробуйте позже или используйте другой номер.")
        await state.clear()

@router.message(StateFilter(SessionStates.waiting_for_code))
async def verify_code(message: types.Message, state: FSMContext):
    """ 🔹 Проверяем введённый код и сохраняем сессию """
    data = await state.get_data()

    if "phone_code_hash" not in data:
        await message.answer("❌ Ошибка: отсутствует `phone_code_hash`. Попробуйте запросить код заново.")
        await state.clear()
        return

    phone = data["phone"]
    api_id = data["api_id"]
    api_hash = data["api_hash"]
    phone_code_hash = data["phone_code_hash"]
    session_file = f"{phone.replace('+', '')}.session"
    session_path = os.path.join(UPLOAD_PATH, session_file)

    client = TelegramClient(session_path, api_id, api_hash)
    await client.connect()

    try:
        logger.info(f"📨 Попытка входа: phone={phone}, code={message.text.strip()}, phone_code_hash={phone_code_hash}")

        await client.sign_in(phone, code=message.text.strip(), phone_code_hash=phone_code_hash)
        await message.answer("✅ Сессия успешно создана!")

        async for db in get_db():
            user = await db.execute(select(User).where(User.id == message.from_user.id))
            user = user.scalars().first()

            if not user:
                new_user = User(id=message.from_user.id, telegram_id=message.from_user.id)
                db.add(new_user)
                await db.commit()

            session = TelegramSession(
                user_id=message.from_user.id,
                session_file=session_file,
                api_id=api_id,
                api_hash=api_hash
            )
            db.add(session)
            await db.commit()

        logger.info(f"🔹 Сессия создана для {phone}")
        await state.clear()

    except PhoneCodeExpiredError:
        logger.warning(f"❌ Код истёк для {phone}, запрашиваю новый...")

        sent = await client.send_code_request(phone)
        if not sent.phone_code_hash:
            logger.error("❌ Telegram не вернул новый `phone_code_hash`, код НЕ отправлен.")
            await message.answer("❌ Ошибка: Telegram не вернул новый код. Попробуйте снова.")
            return

        await state.update_data(phone_code_hash=sent.phone_code_hash)
        await message.answer("📨 Новый код отправлен. Введите его.")

    except SessionPasswordNeededError:
        await state.set_state(SessionStates.waiting_for_password)
        await message.answer("🔒 Аккаунт защищён паролем. Введите пароль:")

    except Exception as e:
        logger.error(f"❌ Ошибка входа: {e}")
        await message.answer(f"❌ Ошибка: {e}\nПопробуйте снова запросить код.")
        await state.clear()

    finally:
        await client.disconnect()

@router.message(StateFilter(SessionStates.waiting_for_password))
async def get_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    phone = data["phone"]
    api_id = data["api_id"]
    api_hash = data["api_hash"]
    session_path = os.path.join(UPLOAD_PATH, f"{phone.replace('+', '')}.session")

    client = TelegramClient(session_path, api_id, api_hash)

    try:
        await client.connect()
        await client.sign_in(password=message.text.strip())
        await message.answer("✅ Сессия успешно создана (с паролем)!")

        async for db in get_db():
            session = TelegramSession(
                user_id=message.from_user.id,
                session_file=f"{phone.replace('+', '')}.session",
                api_id=api_id,
                api_hash=api_hash
            )
            db.add(session)
            await db.commit()

        logger.info(f"🔹 Сессия с паролем создана для {phone}")
        await state.clear()

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
        await state.clear()

def escape_markdown(text: str) -> str:
    # Экранирование символов для Markdown V1
    escape_chars = r"\_*[]()~`>#+-=|{}.!"
    return re.sub(rf"([{re.escape(escape_chars)}])", r"\\\1", text)


async def list_sessions(message: types.Message):
    async for db in get_db():
        sessions = await db.execute(
            select(TelegramSession).where(TelegramSession.user_id == message.from_user.id)
        )
        sessions = sessions.scalars().all()

    if not sessions:
        await message.answer("❌ У вас нет сохранённых сессий.")
        return

    text = "📂 *Ваши сессии:*\n\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    for session in sessions:
        session_name = session.session_file.replace(".session", "")
        session_path = f"sessions/{session.session_file}"

        try:
            client = TelegramClient(session_path, session.api_id, session.api_hash)
            await client.connect()

            if not await client.is_user_authorized():
                user_display = "🔒 [Сессия не авторизована]"
            else:
                me = await client.get_me()
                user_display = f"(@{me.username})" if me.username else f"(ID: {me.id})"

            await client.disconnect()
        except Exception:
            user_display = "⚠ Ошибка загрузки"

        # Экранируем все переменные перед вставкой в Markdown
        safe_session_name = escape_markdown(session_name)
        safe_user_display = escape_markdown(user_display)

        text += f"🔹 {safe_session_name} {safe_user_display}\n"
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"🗑 Удалить {session_name}",
                callback_data=f"delete_session:{session.session_file}"
            )
        ])

    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(F.text == "📂 Мои сессии")
async def handle_list_sessions(message: types.Message):
    await list_sessions(message)

@router.callback_query(lambda c: c.data.startswith("delete_session:"))
async def delete_session(callback: types.CallbackQuery):
    session_file = callback.data.split(":")[1]
    async for db in get_db():
        session = await db.execute(select(TelegramSession).where(
            TelegramSession.user_id == callback.from_user.id,
            TelegramSession.session_file == session_file
        ))
        session = session.scalars().first()

        if not session:
            await callback.answer("❌ Сессия не найдена.", show_alert=True)
            return

        await db.delete(session)
        await db.commit()

        session_path = f"sessions/{session_file}"
        if os.path.exists(session_path):
            os.remove(session_path)

    await callback.message.answer(f"✅ Сессия {session_file} удалена.")
    await callback.answer()
