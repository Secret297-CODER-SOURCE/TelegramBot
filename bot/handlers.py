from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from bot.session_manager import request_api_id, list_sessions
from bot.join import join_group
from bot.unsubscribe import show_unsubscribe_info, unsubscribe_group
from bot.check_subscription import check_subscription
from bot.spam import start_spam
from bot.logger import logger
import random
import asyncio
from bot.admin_panel import router as admin_router

router = Router()

class BotStates(StatesGroup):
    waiting_for_subscription_link = State()
    waiting_for_subscription_interval_range = State()
    waiting_for_unsubscription_link = State()
    waiting_for_unsubscribe_interval_range = State()
    waiting_for_unsubscribe_count = State()
    waiting_for_randomization_choice = State()
    waiting_for_random_range = State()
    waiting_for_check_subscription_link = State()
    waiting_for_spam_message = State()

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Создать сессию"), KeyboardButton(text="📂 Мои сессии")],
        [KeyboardButton(text="📩 Подписаться на группу"), KeyboardButton(text="🚫 Выйти из группы")],
        [KeyboardButton(text="📢 Проверить подписку"), KeyboardButton(text="📨 Начать рассылку")],
        [KeyboardButton(text="🛠 Админ-панель")],[KeyboardButton(text="🌐 Управление прокси")]
    ],
    resize_keyboard=True
)

@router.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("👋 Привет! Выбери действие:", reply_markup=main_keyboard)
    logger.info(f"👤 {message.from_user.id} открыл меню")

@router.message(F.text == "➕ Создать сессию")
async def request_session_creation(message: types.Message, state: FSMContext):
    await state.clear()
    await request_api_id(message, state)

@router.message(F.text == "📂 Мои сессии")
async def show_sessions(message: types.Message):
    await list_sessions(message)

@router.message(F.text == "📩 Подписаться на группу")
async def request_group_join(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(BotStates.waiting_for_subscription_link)
    await message.answer("🔗 Введите ссылку на Telegram-группу для подписки:")

@router.message(StateFilter(BotStates.waiting_for_subscription_link))
async def process_group_join(message: types.Message, state: FSMContext):
    group_link = message.text.strip()
    await state.update_data(group_link=group_link)
    await state.set_state(BotStates.waiting_for_subscription_interval_range)
    await message.answer("⏳ Введите диапазон интервалов между подписками (в формате 'мин-мах', в минутах):")

@router.message(StateFilter(BotStates.waiting_for_subscription_interval_range))
async def process_subscription_interval_range(message: types.Message, state: FSMContext):
    try:
        min_interval, max_interval = map(int, message.text.split('-'))
        if min_interval > max_interval:
            raise ValueError
    except ValueError:
        await message.answer("Введите корректный диапазон в формате 'мин-мах', где мин <= мах.")
        return
    data = await state.get_data()
    group_link = data.get("group_link")
    interval = random.randint(min_interval, max_interval) * 60  # интервал в секундах
    await join_group(message, group_link=group_link, interval=interval)
    await message.answer(f"✅ Подписка на {group_link} запущена с интервалом {interval // 60} минут (случайное значение из диапазона).")
    await state.clear()

@router.message(F.text == "🚫 Выйти из группы")
async def request_group_leave(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(BotStates.waiting_for_unsubscription_link)
    await message.answer("🔗 Введите ссылку на Telegram-группу для отписки:")

@router.message(StateFilter(BotStates.waiting_for_unsubscription_link))
async def process_unsubscribe_link(message: types.Message, state: FSMContext):
    group_link = message.text.strip()
    await state.update_data(group_link=group_link)
    await show_unsubscribe_info(message)
    await message.answer("⏳ Введите диапазон интервалов между отписками (в формате 'мин-мах', в минутах):")
    await state.set_state(BotStates.waiting_for_unsubscribe_interval_range)

@router.message(StateFilter(BotStates.waiting_for_unsubscribe_interval_range))
async def process_unsubscribe_interval_range(message: types.Message, state: FSMContext):
    try:
        min_interval, max_interval = map(int, message.text.split('-'))
        if min_interval > max_interval:
            raise ValueError
    except ValueError:
        await message.answer("Введите корректный диапазон в формате 'мин-мах', где мин ≤ мах.")
        return

    interval = random.randint(min_interval, max_interval) * 60  # перевод в секунды
    await state.update_data(interval=interval)
    await message.answer("📊 Введите количество аккаунтов для отписки:")
    await state.set_state(BotStates.waiting_for_unsubscribe_count)

@router.message(StateFilter(BotStates.waiting_for_unsubscribe_count))
async def process_unsubscribe_count(message: types.Message, state: FSMContext):
    try:
        count = int(message.text.strip())
        if count <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите корректное количество аккаунтов (положительное число).")
        return

    data = await state.get_data()
    group_link = data.get("group_link")
    interval = data.get("interval")

    # Вызываем функцию отписки без рандомизации
    await unsubscribe_group(message, count, interval, randomize=False, random_range=0, group_link=group_link)
    await message.answer(f"✅ Отписано {count} аккаунтов от группы {group_link}.")
    await state.clear()



@router.message(F.text == "📢 Проверить подписку")
async def request_check_subscription(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(BotStates.waiting_for_check_subscription_link)
    await message.answer("🔗 Введите ссылку на группу для проверки подписки:")

@router.message(StateFilter(BotStates.waiting_for_check_subscription_link))
async def process_check_subscription(message: types.Message, state: FSMContext):
    group_link = message.text.strip()
    await check_subscription(message, group_link)
    await state.clear()

@router.message(F.text == "📨 Начать рассылку")
async def start_spam_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(BotStates.waiting_for_spam_message)
    await message.answer("💬 Введите текст сообщения для рассылки:")

@router.message(StateFilter(BotStates.waiting_for_spam_message))
async def process_spam_message(message: types.Message, state: FSMContext):
    await start_spam(message, message.text.strip())
    await state.clear()
