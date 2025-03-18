from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from bot.session_manager import request_api_id, list_sessions  # ✅ Импортируем просмотр сессий
from bot.join import join_group
from bot.unsubscribe import unsubscribe_group
from bot.check_subscription import check_subscription
from bot.spam import start_spam
from bot.logger import logger

router = Router()

# 🔹 Определяем состояния FSM
class BotStates(StatesGroup):
    waiting_for_subscription_link = State()
    waiting_for_unsubscription_link = State()
    waiting_for_check_subscription_link = State()
    waiting_for_spam_message = State()
    waiting_for_session_deletion = State()  # ✅ Добавлено состояние удаления сессий

# 🔹 Главное меню с кнопками
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Создать сессию"),KeyboardButton(text="📂 Мои сессии")], # ✅ Новая кнопка просмотра сессий
        [KeyboardButton(text="📩 Подписаться на группу"), KeyboardButton(text="🚫 Выйти из группы")],
        [KeyboardButton(text="📢 Проверить подписку"), KeyboardButton(text="📨 Начать рассылку")],
        [KeyboardButton(text="🌐 Управление прокси")]
    ],
    resize_keyboard=True
)

@router.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    """ 🔹 Команда /start - Отправляет главное меню """
    await state.clear()
    await message.answer("👋 Привет! Выбери действие:", reply_markup=main_keyboard)
    logger.info(f"👤 {message.from_user.id} открыл меню")

# 📌 Создание сессии
@router.message(F.text == "➕ Создать сессию")
async def request_session_creation(message: types.Message, state: FSMContext):
    """ 🔹 Обработчик кнопки "Создать сессию" """
    await state.clear()
    await request_api_id(message, state)
    logger.info(f"👤 {message.from_user.id} начал создание сессии")

# 📌 Просмотр сессий
@router.message(F.text == "📂 Мои сессии")
async def show_sessions(message: types.Message):
    """ 🔹 Отображает список активных сессий """
    await list_sessions(message)

# 📌 Подписка
@router.message(F.text == "📩 Подписаться на группу")
async def request_group_join(message: types.Message, state: FSMContext):
    """ 🔹 Запрашиваем ссылку для подписки """
    await state.clear()
    await state.set_state(BotStates.waiting_for_subscription_link)
    await message.answer("🔗 Введите ссылку на Telegram-группу для подписки:")

@router.message(StateFilter(BotStates.waiting_for_subscription_link))
async def process_group_join(message: types.Message, state: FSMContext):
    """ 🔹 Подписывает аккаунты на указанную группу """
    await join_group(message)
    await state.clear()
    logger.info(f"👤 {message.from_user.id} подписался на {message.text}")

# 📌 Отписка
@router.message(F.text == "🚫 Выйти из группы")
async def request_group_leave(message: types.Message, state: FSMContext):
    """ 🔹 Запрашиваем ссылку для отписки """
    await state.clear()
    await state.set_state(BotStates.waiting_for_unsubscription_link)
    await message.answer("🔗 Введите ссылку на Telegram-группу, от которой хотите отписаться:")

@router.message(StateFilter(BotStates.waiting_for_unsubscription_link))
async def process_unsubscribe_request(message: types.Message, state: FSMContext):
    """ 🔹 Отписывает аккаунты от указанной группы """
    await unsubscribe_group(message)
    await state.clear()
    logger.info(f"👤 {message.from_user.id} отписался от {message.text}")

# 📌 Проверка подписки
@router.message(F.text == "📢 Проверить подписку")
async def request_subscription_check(message: types.Message, state: FSMContext):
    """ 🔹 Запрашиваем ссылку для проверки подписки """
    await state.clear()
    await state.set_state(BotStates.waiting_for_check_subscription_link)
    await message.answer("🔗 Введите ссылку на Telegram-группу для проверки подписки:")

@router.message(StateFilter(BotStates.waiting_for_check_subscription_link))
async def process_subscription_check(message: types.Message, state: FSMContext):
    """ 🔹 Проверяет подписку аккаунтов на указанную группу """
    await check_subscription(message)
    await state.clear()
    logger.info(f"👤 {message.from_user.id} проверил подписку на {message.text}")

# 📌 Рассылка
@router.message(F.text == "📨 Начать рассылку")
async def request_spam_start(message: types.Message, state: FSMContext):
    """ 🔹 Запрашиваем текст для рассылки """
    await state.clear()
    await state.set_state(BotStates.waiting_for_spam_message)
    await message.answer("✉️ Введите текст рассылки:")

@router.message(StateFilter(BotStates.waiting_for_spam_message))
async def process_spam_start(message: types.Message, state: FSMContext):
    """ 🔹 Запускает рассылку по всем группам """
    await start_spam(message)
    await state.clear()
    logger.info(f"👤 {message.from_user.id} запустил рассылку: {message.text}")

# 📌 Управление прокси
@router.message( F.text   == "🌐 Управление прокси")
async def manage_proxy(message: types.Message, state: FSMContext):
    """ 🔹 Открываем меню управления прокси """
    await state.clear()
    await message.answer("🔧 Управление прокси пока в разработке.")
