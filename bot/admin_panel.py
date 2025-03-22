from aiogram import Router, types, F
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from sqlalchemy import select, update
from db.sessions import get_db
from db.models import User

router = Router()

class AdminPanelStates(StatesGroup):
    setting_online_schedule = State()
    setting_random_online = State()
    granting_admin_rights = State()
    revoking_admin_rights = State()

# Проверка, админ ли пользователь
async def is_admin_user(user_id: int) -> bool:
    async for db in get_db():
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        return user and user.is_admin

# Кнопка "Админ-панель"
@router.message(F.text == "🛠 Админ-панель")
async def admin_panel_menu(message: types.Message):
    if not await is_admin_user(message.from_user.id):
        await message.answer("🚫 У вас нет доступа к админ-панели.")
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚙ Настройки онлайна"), KeyboardButton(text="🎲 Рандомизация онлайна")],
            [KeyboardButton(text="👤 Выдать права админа"), KeyboardButton(text="🚫 Забрать права админа")],
            [KeyboardButton(text="⬅ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("🛠 Добро пожаловать в админ-панель", reply_markup=keyboard)

# 🔹 Выдача прав админа
@router.message(F.text == "👤 Выдать права админа")
async def grant_admin_rights(message: types.Message, state: FSMContext):
    await state.set_state(AdminPanelStates.granting_admin_rights)
    await message.answer("🔐 Введите Telegram ID пользователя, которому хотите выдать права администратора:")

@router.message(AdminPanelStates.granting_admin_rights)
async def save_admin_id(message: types.Message, state: FSMContext):
    telegram_id = message.text.strip()
    if not telegram_id.isdigit():
        await message.answer("❌ Введите корректный Telegram ID.")
        return

    async for db in get_db():
        result = await db.execute(select(User).where(User.telegram_id == int(telegram_id)))
        user = result.scalar_one_or_none()
        if user:
            user.is_admin = True
            await db.commit()
            await message.answer(f"✅ Пользователь {telegram_id} теперь администратор!")
        else:
            await message.answer("❌ Пользователь не найден в базе.")

    await state.clear()


# 🔹 Забрать права админа
@router.message(F.text == "🚫 Забрать права админа")
async def revoke_admin_rights(message: types.Message, state: FSMContext):
    await state.set_state(AdminPanelStates.revoking_admin_rights)
    await message.answer("✂️ Введите Telegram ID пользователя, у которого хотите забрать права администратора:")

@router.message(AdminPanelStates.revoking_admin_rights)
async def remove_admin(message: types.Message, state: FSMContext):
    telegram_id = message.text.strip()
    if not telegram_id.isdigit():
        await message.answer("❌ Введите корректный Telegram ID.")
        return

    async for db in get_db():
        result = await db.execute(select(User).where(User.telegram_id == int(telegram_id)))
        user = result.scalar_one_or_none()
        if user and user.is_admin:
            user.is_admin = False
            await db.commit()
            await message.answer(f"❎ Пользователь {telegram_id} больше не администратор.")
        else:
            await message.answer("❌ Пользователь не найден или не является админом.")

    await state.clear()

# Назад в главное меню
@router.message(F.text == "⬅ Назад")
async def back_to_main_menu(message: types.Message):
    from bot.handlers import main_keyboard
    await message.answer("🔙 Возвращаюсь в главное меню", reply_markup=main_keyboard)
