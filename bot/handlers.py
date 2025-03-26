from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from bot.proxy_manager import manage_proxy
from bot.session_manager import request_api_id, list_sessions, sessions_menu
from bot.join import join_group
from bot.unsubscribe import show_unsubscribe_info, unsubscribe_group
from bot.check_subscription import check_subscription
from bot.spam import start_spam
from bot.logger import logger
from bot.admin_panel import router as admin_router
import random




router = Router()

class BotStates(StatesGroup):
    neutral = State()
    waiting_for_subscription_link = State()
    waiting_for_subscription_interval_range = State()
    waiting_for_unsubscription_link = State()
    waiting_for_unsubscribe_interval_range = State()
    waiting_for_unsubscribe_count = State()
    waiting_for_check_subscription_link = State()
    waiting_for_spam_message = State()
    confirmation_of_fsm_stop = State()

MAIN_ACTION_BUTTONS = [
    "👥 Сессии",
    "📩 Подписаться на группу",
    "🚫 Выйти из группы",
    "📢 Проверить подписку",
    "📨 Начать рассылку",
    "🛠 Админ-панель",
    "🌐 Управление прокси"
]

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👥 Сессии")],
        [KeyboardButton(text="📩 Подписаться на группу"), KeyboardButton(text="🚫 Выйти из группы")],
        [KeyboardButton(text="📢 Проверить подписку"), KeyboardButton(text="📨 Начать рассылку")],
        [KeyboardButton(text="🛠 Админ-панель"),KeyboardButton(text="🌐 Управление прокси")]
    ],
    resize_keyboard=True
)

command_handlers = {}

async def dispatch_command(command: str, message: types.Message, state: FSMContext):
    handler = command_handlers.get(command)
    if handler:
        await handler(message, state)
    else:
        await message.answer("Неизвестная команда.")

async def fsm_conflict_check(message: types.Message, state: FSMContext, conflict_buttons: list):
    if message.text not in conflict_buttons:
        return False
    current_state = await state.get_state()
    if not current_state:
        await state.set_state(BotStates.neutral)
        current_state = BotStates.neutral.state
    if current_state in [BotStates.neutral.state, BotStates.confirmation_of_fsm_stop.state]:
        return False
    await state.update_data(pending_command=message.text)
    await state.set_state(BotStates.confirmation_of_fsm_stop)
    await message.answer("⚠️ Ты уже выполняешь действие. Прервать и начать новое? Напиши 'да' или 'нет'.")
    return True

@router.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    await state.set_state(BotStates.neutral)
    await message.answer("👋 Привет! Выбери действие:", reply_markup=main_keyboard)
    logger.info(f"👤 {message.from_user.id} открыл меню")

@router.message(F.text == "👥 Сессии")
async def sessions_entrypoint(message: types.Message, state: FSMContext):
    if await fsm_conflict_check(message, state, MAIN_ACTION_BUTTONS):
        command_handlers["👥 Сессии"] = sessions_entrypoint
        return
    await sessions_menu(message, state)
command_handlers["👥 Сессии"] = sessions_entrypoint

@router.message(StateFilter(BotStates.confirmation_of_fsm_stop))
async def process_fsm_stop_confirmation(message: types.Message, state: FSMContext):
    response = message.text.strip().lower()
    data = await state.get_data()
    pending_command = data.get("pending_command")
    if response == 'да':
        await state.set_state(BotStates.neutral)
        if pending_command:
            await state.update_data(pending_command=None)
            await dispatch_command(pending_command, message, state)
        else:
            await message.answer("Нет отложенной команды.")
    elif response == 'нет':
        await message.answer("Окей, продолжай текущую операцию.")
    else:
        await message.answer("Напиши 'да' или 'нет'.")

# Регистрируем все основные хендлеры в словаре для отложенного вызова
@router.message(F.text == "➕ Создать сессию")
async def request_session_creation(message: types.Message, state: FSMContext):
    if await fsm_conflict_check(message, state, MAIN_ACTION_BUTTONS):
        # Сохраним отложенную команду для последующего вызова
        command_handlers["➕ Создать сессию"] = request_session_creation
        return
    await state.set_state(BotStates.neutral)
    await request_api_id(message, state)
command_handlers["➕ Создать сессию"] = request_session_creation

@router.message(F.text == "📂 Мои сессии")
async def show_sessions(message: types.Message, state: FSMContext):
    if await fsm_conflict_check(message, state, MAIN_ACTION_BUTTONS):
        command_handlers["📂 Мои сессии"] = show_sessions
        return
    await list_sessions(message)
command_handlers["📂 Мои сессии"] = show_sessions

@router.message(F.text == "📩 Подписаться на группу")
async def request_group_join(message: types.Message, state: FSMContext):
    if await fsm_conflict_check(message, state, MAIN_ACTION_BUTTONS):
        command_handlers["📩 Подписаться на группу"] = request_group_join
        return
    await state.set_state(BotStates.waiting_for_subscription_link)
    await message.answer("🔗 Введите ссылку на Telegram-группу для подписки:")
command_handlers["📩 Подписаться на группу"] = request_group_join

@router.message(F.text == "🚫 Выйти из группы")
async def request_group_leave(message: types.Message, state: FSMContext):
    if await fsm_conflict_check(message, state, MAIN_ACTION_BUTTONS):
        command_handlers["🚫 Выйти из группы"] = request_group_leave
        return
    await state.set_state(BotStates.waiting_for_unsubscription_link)
    await message.answer("🔗 Введите ссылку на Telegram-группу для отписки:")
command_handlers["🚫 Выйти из группы"] = request_group_leave

@router.message(F.text == "📢 Проверить подписку")
async def request_check_subscription(message: types.Message, state: FSMContext):
    if await fsm_conflict_check(message, state, MAIN_ACTION_BUTTONS):
        command_handlers["📢 Проверить подписку"] = request_check_subscription
        return
    await state.set_state(BotStates.waiting_for_check_subscription_link)
    await message.answer("🔗 Введите ссылку на группу для проверки подписки:")
command_handlers["📢 Проверить подписку"] = request_check_subscription

@router.message(F.text == "📨 Начать рассылку")
async def start_spam_handler(message: types.Message, state: FSMContext):
    if await fsm_conflict_check(message, state, MAIN_ACTION_BUTTONS):
        command_handlers["📨 Начать рассылку"] = start_spam_handler
        return
    await state.set_state(BotStates.waiting_for_spam_message)
    await message.answer("💬 Введите текст сообщения для рассылки:")
command_handlers["📨 Начать рассылку"] = start_spam_handler

@router.message(F.text == "🛠 Админ-панель")
async def admin_panel(message: types.Message, state: FSMContext):
    if await fsm_conflict_check(message, state, MAIN_ACTION_BUTTONS):
        command_handlers["🛠 Админ-панель"] = admin_panel
        return
    await state.set_state(BotStates.neutral)
    # Здесь должна быть логика для админ-панели
    await message.answer("🔧 Админ-панель: выберите действие...", reply_markup=main_keyboard)
command_handlers["🛠 Админ-панель"] = admin_panel

@router.message(F.text == "🌐 Управление прокси")
async def proxy_entrypoint(message: types.Message, state: FSMContext):
    if await fsm_conflict_check(message, state, MAIN_ACTION_BUTTONS):
        command_handlers["🌐 Управление прокси"] = proxy_entrypoint
        return
    await manage_proxy(message, state)
command_handlers["🌐 Управление прокси"] = proxy_entrypoint

# Далее идут обработчики для продолжения диалога, например:
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
    interval = random.randint(min_interval, max_interval) * 60
    await join_group(message, group_link=group_link, interval=interval)
    await message.answer(f"✅ Подписка на {group_link} запущена с интервалом {interval // 60} минут.")
    await state.set_state(BotStates.neutral)

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
    interval = random.randint(min_interval, max_interval) * 60
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
    await unsubscribe_group(message, count, interval, randomize=False, random_range=0, group_link=group_link)
    await message.answer(f"✅ Отписано {count} аккаунтов от группы {group_link}.")
    await state.set_state(BotStates.neutral)

@router.message(StateFilter(BotStates.waiting_for_check_subscription_link))
async def process_check_subscription(message: types.Message, state: FSMContext):
    group_link = message.text.strip()
    await check_subscription(message, group_link)
    await state.set_state(BotStates.neutral)

@router.message(StateFilter(BotStates.waiting_for_spam_message))
async def process_spam_message(message: types.Message, state: FSMContext):
    await start_spam(message, message.text.strip())
    await state.set_state(BotStates.neutral)
