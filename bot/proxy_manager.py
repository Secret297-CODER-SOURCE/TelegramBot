from sqlalchemy.future import select
from db.models import ProxySettings
from db.sessions import get_db

from aiogram import types, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

import aiohttp
from aiohttp_socks import ProxyConnector

router = Router()

# FSM состояния
class ProxyStates(StatesGroup):
    waiting_for_proxy_data = State()
    waiting_for_proxy_deletion_id = State()

# Главное меню
@router.message(F.text == "🌐 Управление прокси")
async def manage_proxy(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить прокси")],
            [KeyboardButton(text="📄 Показать прокси")],
            [KeyboardButton(text="🔍 Проверить все прокси")],
            [KeyboardButton(text="❌ Удалить прокси")],
            [KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True
    )
    await state.clear()
    await message.answer("🌐 Меню управления прокси:", reply_markup=keyboard)

# Добавление прокси
@router.message(F.text == "➕ Добавить прокси")
async def add_proxy(message: types.Message, state: FSMContext):
    await state.set_state(ProxyStates.waiting_for_proxy_data)
    await message.answer(
        "🔌 Введите данные прокси в формате:\n<code>тип:ip:port:логин:пароль</code>\n"
        "Пример: <code>socks5:127.0.0.1:1080:user:pass</code>\n"
        "Если логина и пароля нет, используйте: <code>тип:ip:port</code>",
        parse_mode="HTML"
    )

@router.message(StateFilter(ProxyStates.waiting_for_proxy_data))
async def save_proxy(message: types.Message, state: FSMContext):
    parts = message.text.strip().split(":")
    if len(parts) not in [3, 5]:
        await message.answer("❌ Неверный формат. Используйте: <code>тип:ip:port:логин:пароль</code>", parse_mode="HTML")
        return

    proxy_type, host, port = parts[0], parts[1], int(parts[2])
    login = parts[3] if len(parts) == 5 else None
    password = parts[4] if len(parts) == 5 else None

    if proxy_type not in ["socks5", "socks4", "http"]:
        await message.answer("❌ Неверный тип прокси. Допустимые типы: socks5, socks4, http")
        return

    # Проверка прокси
    try:
        url = f"{proxy_type}://{login}:{password}@{host}:{port}" if login else f"{proxy_type}://{host}:{port}"
        connector = ProxyConnector.from_url(url)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get("http://example.com", timeout=aiohttp.ClientTimeout(total=7)):
                pass
    except Exception as e:
        await message.answer(f"❌ Прокси не работает: `{e}`", parse_mode="Markdown")
        return

    # Сохранение в БД
    async for db in get_db():
        db.add(ProxySettings(
            user_id=message.from_user.id,
            proxy_type=proxy_type,
            proxy_host=host,
            proxy_port=port,
            proxy_login=login,
            proxy_password=password
        ))
        await db.commit()

    await state.clear()
    await message.answer("✅ Прокси успешно добавлен и работает!")

# Просмотр прокси
@router.message(F.text == "📄 Показать прокси")
async def list_proxies(message: types.Message, state: FSMContext):
    async for db in get_db():
        proxies = await db.execute(
            select(ProxySettings).where(ProxySettings.user_id == message.from_user.id)
        )
        proxies = proxies.scalars().all()

    if not proxies:
        await message.answer("❌ У вас нет сохранённых прокси.")
        return

    text = "🌐 Ваши прокси:\n\n"
    for proxy in proxies:
        auth = f"{proxy.proxy_login}:{proxy.proxy_password}@" if proxy.proxy_login else ""
        text += f"🆔 {proxy.id}: {proxy.proxy_type}://{auth}{proxy.proxy_host}:{proxy.proxy_port}\n"
    await message.answer(text)

# Удаление прокси
@router.message(F.text == "❌ Удалить прокси")
async def delete_proxy_prompt(message: types.Message, state: FSMContext):
    async for db in get_db():
        proxies = await db.execute(
            select(ProxySettings).where(ProxySettings.user_id == message.from_user.id)
        )
        proxies = proxies.scalars().all()

    if not proxies:
        await message.answer("❌ У вас нет сохранённых прокси.")
        return

    buttons_per_page = 5
    page = 0
    await state.update_data(proxy_page=page, proxy_ids=[p.id for p in proxies])

    def get_markup(page, proxies_list):
        start = page * buttons_per_page
        end = start + buttons_per_page
        current_proxies = proxies_list[start:end]

        inline_keyboard = [
            [InlineKeyboardButton(
                text=f"🆗 {p.proxy_type}://{p.proxy_host}:{p.proxy_port}",
                callback_data=f"delete_proxy:{p.id}")]
            for p in current_proxies
        ]

        navigation = []
        total_pages = (len(proxies_list) - 1) // buttons_per_page + 1
        if page > 0:
            navigation.append(InlineKeyboardButton("⬅️ Назад", callback_data="proxy_prev"))
        if end < len(proxies_list):
            navigation.append(InlineKeyboardButton("➡️ Далее", callback_data="proxy_next"))
        if navigation:
            inline_keyboard.append(navigation)

        return InlineKeyboardMarkup(inline_keyboard=inline_keyboard), total_pages

    markup, total_pages = get_markup(page, proxies)
    await state.set_state(ProxyStates.waiting_for_proxy_deletion_id)
    await message.answer(
        f"🧹 Выберите прокси для удаления (страница {page + 1} из {total_pages}):",
        reply_markup=markup
    )

# Обработка callback-запросов для удаления
@router.callback_query(F.data.startswith("delete_proxy:"))
async def process_proxy_deletion(callback: types.CallbackQuery, state: FSMContext):
    proxy_id = int(callback.data.split(":")[1])
    async for db in get_db():
        proxy = await db.execute(
            select(ProxySettings).where(
                ProxySettings.user_id == callback.from_user.id,
                ProxySettings.id == proxy_id
            )
        )
        proxy = proxy.scalars().first()
        if not proxy:
            await callback.message.edit_text("❌ Прокси с таким ID не найден.")
            return
        await db.delete(proxy)
        await db.commit()

    await callback.message.edit_text(f"✅ Прокси с ID {proxy_id} успешно удалён!")
    await state.clear()

# Обработка пагинации
@router.callback_query(F.data.in_(["proxy_prev", "proxy_next"]))
async def process_pagination(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    page = data.get("proxy_page", 0)
    proxy_ids = data.get("proxy_ids", [])

    if callback.data == "proxy_prev" and page > 0:
        page -= 1
    elif callback.data == "proxy_next":
        page += 1

    await state.update_data(proxy_page=page)

    async for db in get_db():
        proxies = await db.execute(
            select(ProxySettings).where(ProxySettings.id.in_(proxy_ids))
        )
        proxies = proxies.scalars().all()

    def get_markup(page, proxies_list):
        start = page * buttons_per_page
        end = start + buttons_per_page
        current_proxies = proxies_list[start:end]

        inline_keyboard = [
            [InlineKeyboardButton(
                text=f"🆗 {p.proxy_type}://{p.proxy_host}:{p.proxy_port}",
                callback_data=f"delete_proxy:{p.id}")]
            for p in current_proxies
        ]

        navigation = []
        total_pages = (len(proxies_list) - 1) // buttons_per_page + 1
        if page > 0:
            navigation.append(InlineKeyboardButton("⬅️ Назад", callback_data="proxy_prev"))
        if end < len(proxies_list):
            navigation.append(InlineKeyboardButton("➡️ Далее", callback_data="proxy_next"))
        if navigation:
            inline_keyboard.append(navigation)

        return InlineKeyboardMarkup(inline_keyboard=inline_keyboard), total_pages

    buttons_per_page = 5
    markup, total_pages = get_markup(page, proxies)
    await callback.message.edit_text(
        f"🧹 Выберите прокси для удаления (страница {page + 1} из {total_pages}):",
        reply_markup=markup
    )
    await callback.answer()

# Проверка всех прокси
@router.message(F.text == "🔍 Проверить все прокси")
async def check_all_proxies(message: types.Message, state: FSMContext):
    async for db in get_db():
        proxies = await db.execute(
            select(ProxySettings).where(ProxySettings.user_id == message.from_user.id)
        )
        proxies = proxies.scalars().all()

    if not proxies:
        await message.answer("❌ У вас нет сохранённых прокси.")
        return

    await message.answer("🧪 Проверяю прокси... Подождите...")

    working, broken = [], []

    for proxy in proxies:
        try:
            url = f"{proxy.proxy_type}://{proxy.proxy_login}:{proxy.proxy_password}@{proxy.proxy_host}:{proxy.proxy_port}" if proxy.proxy_login else f"{proxy.proxy_type}://{proxy.proxy_host}:{proxy.proxy_port}"
            connector = ProxyConnector.from_url(url)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get("http://example.com", timeout=aiohttp.ClientTimeout(total=7)):
                    working.append(proxy.id)
        except Exception:
            broken.append(proxy.id)

    if working:
        working_text = "\n".join(
            [f"🆗 ID {proxy.id}: {proxy.proxy_type}://{proxy.proxy_host}:{proxy.proxy_port}" for proxy in proxies if proxy.id in working]
        )
    else:
        working_text = "нет"

    if broken:
        broken_text = "\n".join(
            [f"⛔️ ID {proxy.id}: {proxy.proxy_type}://{proxy.proxy_host}:{proxy.proxy_port}" for proxy in proxies if proxy.id in broken]
        )
    else:
        broken_text = "нет"

    summary = (
        "<b>📊 Проверка завершена:</b>\n\n"
        f"<b>✅ Рабочие:</b>\n{working_text}\n\n"
        f"<b>❌ Нерабочие:</b>\n{broken_text}"
    )
    await message.answer(summary, parse_mode="HTML")

# Удаление прокси через текстовый ввод (для совместимости)
@router.message(StateFilter(ProxyStates.waiting_for_proxy_deletion_id))
async def delete_proxy_text(message: types.Message, state: FSMContext):
    try:
        proxy_text = message.text.strip()
        if not proxy_text.startswith("Удалить ID "):
            await message.answer("❌ Неверный формат. Используйте кнопки или введите 'Удалить ID <номер>'.")
            return
        proxy_id = int(proxy_text.replace("Удалить ID ", ""))
        async for db in get_db():
            proxy = await db.execute(
                select(ProxySettings).where(
                    ProxySettings.user_id == message.from_user.id,
                    ProxySettings.id == proxy_id
                )
            )
            proxy = proxy.scalars().first()
            if not proxy:
                await message.answer("❌ Прокси с таким ID не найден.")
                return
            await db.delete(proxy)
            await db.commit()
            await message.answer("✅ Прокси удалён.")
    except Exception as e:
        await message.answer(f"❌ Ошибка при удалении: `{e}`", parse_mode="Markdown")
    finally:
        await state.clear()