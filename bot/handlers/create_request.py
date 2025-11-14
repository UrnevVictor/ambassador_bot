from bot.services.sheets import get_venues_by_ambassador
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)

EST_PAGE_SIZE = 10


def _get_ambassador_username(username: str | None, user_id: int) -> str | None:
    """
    Возвращаем username амбассадора в формате @username.
    Если username пустой, возвращаем None — в этом случае привязка по таблице невозможна.
    """
    if not username:
        return None
    return f"@{username}"


def get_establishments_for(username: str | None):
    """Получить список заведений, привязанных к амбассадору."""
    amb = _get_ambassador_username(username, 0)
    if not amb:
        return []
    return get_venues_by_ambassador(amb)

def build_establishments_keyboard(establishments, page: int = 0):
    start = page * EST_PAGE_SIZE
    end = start + EST_PAGE_SIZE
    page_items = establishments[start:end]

    buttons = [
        [InlineKeyboardButton(text=e, callback_data=f"est_{e}")]
        for e in page_items
    ]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⏮ Назад", callback_data=f"estpage_{page-1}"))
    if end < len(establishments):
        nav.append(InlineKeyboardButton(text="Вперёд ⏭", callback_data=f"estpage_{page+1}"))
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=buttons)

from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards.lines import get_lines_keyboard
from bot.keyboards.sku import get_sku_keyboard
from bot.services.sheets import append_row, get_chat_link, read_sheet
from bot.services.sheets import update_status
from datetime import datetime
from aiogram.utils.deep_linking import decode_payload
from aiogram.exceptions import TelegramBadRequest

router = Router()


def get_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🆕 Создать заявку")],
            # позже можно добавить "📋 Мои заявки"
        ],
        resize_keyboard=True,
    )

# сохраняем chat_id откуда нажали бота
@router.message(F.text.startswith("/start"))
async def catch_chat_id(message: types.Message, state: FSMContext):
    text = message.text.strip()

    # Обычный старт — показываем главное меню
    if text == "/start":
        await message.answer(
            "Привет! Выбери действие на клавиатуре ниже.",
            reply_markup=get_main_menu(),
        )
        return

    # Старт по deep-link с payload (для привязки чатов, если нужно)
    payload = message.text.replace("/start ", "").strip()
    try:
        chat_id = int(decode_payload(payload))
        await state.update_data(source_chat=chat_id)
    except Exception:
        pass

class RequestForm(StatesGroup):
    establishment = State()
    line = State()
    sku = State()
    person = State()
    contact = State()

# Разрешаем создавать заявки только в личке
def is_private(message: types.Message) -> bool:
    return message.chat.type == "private"


@router.message(F.text.in_({"/заявка", "🆕 Создать заявку"}))
async def start_request(message: types.Message, state: FSMContext):
    if message.chat.type != "private":
        return  # полностью молчим в группах

    # прячем клавиатуру меню, чтобы не нажимали "Создать заявку" повторно
    await message.answer("Начинаем заявку.", reply_markup=ReplyKeyboardRemove())
    await state.set_state(RequestForm.establishment)
    establishments = get_establishments_for(message.from_user.username)
    if establishments:
        await state.update_data(est_page=0, items={})
        keyboard = build_establishments_keyboard(establishments, 0)
        await message.answer("Выбери заведение:", reply_markup=keyboard)
    else:
        await message.answer("Название заведения?")

@router.message(RequestForm.establishment)
async def search_or_set_establishment(message: types.Message, state: FSMContext):
    establishments = get_establishments_for(message.from_user.username)
    query = message.text.strip().lower()

    # Если есть список заведений — делаем поиск
    if establishments:
        matched = [e for e in establishments if query in e.lower()]

        if len(matched) == 0:
            await message.answer("Ничего не найдено. Попробуй иначе.")
            return

        if len(matched) == 1:
            # Найдено одно — выбираем автоматически
            await state.update_data(establishment=matched[0])
            await state.set_state(RequestForm.line)
            await message.answer(
                "Выбери линейку (можно несколько):",
                reply_markup=await get_lines_keyboard(add_done=True),
            )
            return

        # Нашлось несколько — показываем варианты
        keyboard = build_establishments_keyboard(matched, 0)
        await state.update_data(est_page=0, est_search=matched)
        await message.answer("Найдено несколько вариантов:", reply_markup=keyboard)
        return

    # Если списка нет — работаем как раньше
    await state.update_data(establishment=message.text)
    await state.set_state(RequestForm.line)
    await message.answer(
        "Выбери линейку (можно несколько):",
        reply_markup=await get_lines_keyboard(add_done=True),
    )


@router.callback_query(RequestForm.line, F.data.startswith("line_"))
async def set_line(callback: types.CallbackQuery, state: FSMContext):
    # line_id здесь — индекс колонки в листе SKU
    line_id = callback.data.replace("line_", "")
    data = await state.get_data()
    items = data.get("items") or {}
    selected_for_line = set(items.get(line_id, []))

    print(f"[set_line] user={callback.from_user.id} line={line_id}")
    await state.update_data(current_line_id=line_id, items=items)
    await state.set_state(RequestForm.sku)
    await callback.message.edit_text(
        "Выбери ароматы в этой линейке (можно несколько):",
        reply_markup=await get_sku_keyboard(line_id, selected_for_line),
    )


@router.callback_query(RequestForm.line, F.data == "lines_done")
async def lines_done(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    items = data.get("items") or {}

    if not items:
        await callback.answer(
            "Ты ещё не выбрал ни одного аромата.", show_alert=True
        )
        return

    await state.set_state(RequestForm.person)
    await callback.message.edit_text("С кем вёлся диалог? Укажи имя.")



@router.callback_query(F.data == "sku_done")
async def sku_done(callback: types.CallbackQuery, state: FSMContext):
    """Завершить выбор ароматов в текущей линейке и вернуться к списку линеек."""
    data = await state.get_data()
    line_id = data.get("current_line_id")

    if not line_id:
        await callback.answer("Сначала выбери линейку.", show_alert=True)
        return

    # Ничего не ломаем — просто возвращаемся к выбору линеек
    await state.set_state(RequestForm.line)
    await state.update_data(current_line_id=None)

    try:
        await callback.message.edit_text(
            "Выбери линейку (можно несколько) или нажми «Завершить выбор ароматов».",
            reply_markup=await get_lines_keyboard(add_done=True)
        )
    except TelegramBadRequest:
        await callback.message.answer(
            "Выбери линейку (можно несколько) или нажми «Завершить выбор ароматов».",
            reply_markup=await get_lines_keyboard(add_done=True)
        )

    await callback.answer()


@router.callback_query(F.data == "sku_back")
async def back_to_lines(callback: types.CallbackQuery, state: FSMContext):
    """Возврат к списку линеек."""
    print(f"[back_to_lines] from_user={callback.from_user.id}")
    await callback.answer()

    await state.set_state(RequestForm.line)
    await state.update_data(current_line_id=None)

    text = "Выбери линейку (можно несколько) или нажми «Завершить выбор ароматов»."

    try:
        await callback.message.edit_text(
            text,
            reply_markup=await get_lines_keyboard(add_done=True)
        )
    except TelegramBadRequest:
        await callback.message.answer(
            text,
            reply_markup=await get_lines_keyboard(add_done=True)
        )

# RE-INSERT toggle_sku handler immediately after back_to_lines
@router.callback_query(F.data.startswith("sku_"))
async def toggle_sku(callback: types.CallbackQuery, state: FSMContext):
    print("CALLBACK RAW:", callback.data)
    print("MESSAGE_ID:", callback.message.message_id)
    print("FROM CHAT:", callback.message.chat.id)
    """Вкл/выкл аромат в выбранной линейке (галочка)."""
    sku = callback.data.replace("sku_", "")
    # игнорируем служебные кнопки
    if sku in {"back", "done"}:
        return
    data = await state.get_data()
    line_id = data.get("current_line_id")

    if not line_id:
        await callback.answer("Сначала выбери линейку.")
        return

    items = data.get("items") or {}
    current = set(items.get(line_id, []))

    if sku in current:
        current.remove(sku)
    else:
        current.add(sku)

    items[line_id] = list(current)
    await state.update_data(items=items)

    print(f"[toggle_sku] user={callback.from_user.id} line={line_id} items={current}")
    try:
        await callback.message.edit_reply_markup(
            reply_markup=await get_sku_keyboard(line_id, current)
        )
    except TelegramBadRequest as exc:
        print(f"[toggle_sku] TelegramBadRequest: {exc}")
        pass
    await callback.answer()


@router.message(RequestForm.sku)
async def search_sku(message: types.Message, state: FSMContext):
    """Поиск аромата по введённому тексту в текущей линейке."""
    query = message.text.strip().lower()
    if not query:
        await message.answer("Напиши часть названия аромата.")
        return

    data = await state.get_data()
    line_id = data.get("current_line_id")
    if not line_id:
        await message.answer("Сначала выбери линейку.")
        return

    try:
        col = int(line_id)
    except (TypeError, ValueError):
        col = 0

    rows = read_sheet("SKU")
    if not rows:
        await message.answer("Не могу прочитать список ароматов.")
        return

    items = data.get("items") or {}
    selected = set(items.get(line_id, []))

    found: list[str] = []
    for row in rows[1:]:
        if len(row) <= col:
            continue
        name = str(row[col]).strip()
        if not name:
            continue
        if query in name.lower():
            found.append(name)

    if not found:
        await message.answer("Ничего не найдено, попробуй иначе.")
        return

    buttons = []
    for name in found:
        text = f"✅ {name}" if name in selected else name
        buttons.append(
            [InlineKeyboardButton(text=text, callback_data=f"sku_{name}")]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                text="⬅ Назад к линейкам", callback_data="sku_back"
            )
        ]
    )

    await message.answer(
        "Нашёл такие ароматы, выбери нужные:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.message(RequestForm.person)
async def set_person(message: types.Message, state: FSMContext):
    await state.update_data(person=message.text.strip())
    await state.set_state(RequestForm.contact)
    await message.answer("Контакт (телефон или ссылка на Telegram):")

@router.message(RequestForm.contact)
async def finish_request(message: types.Message, state: FSMContext):
    data = await state.get_data()

    # Проверка: заявки могут создавать только сотрудники
    from bot.services.sheets import is_employee

    username = message.from_user.username
    ambassador = f"@{username}" if username else None

    if not ambassador or not is_employee(ambassador):
        await message.answer(
            "У тебя нет прав создавать заявки. Обратись к руководителю.",
            reply_markup=get_main_menu(),
        )
        await state.clear()
        return

    date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user = message.from_user.full_name
    chat_id = message.chat.id
    msg_id = message.message_id

    ambassador_username = _get_ambassador_username(
        message.from_user.username, message.from_user.id
    )
    dest_chat = (
        get_chat_link(ambassador_username) if ambassador_username is not None else None
    )
    if not dest_chat:
        await message.answer(
            "Ошибка: у тебя не привязан чат дистрибьютора в листе 'Амбассадоры'.",
            reply_markup=get_main_menu(),
        )
        await state.clear()
        return

    # Собираем колонки по линейкам из заголовка листа SKU:
    # в каждой ячейке список ароматов через запятую.
    sku_sheet = read_sheet("SKU")
    header = sku_sheet[0] if sku_sheet else []
    line_order: list[tuple[str, str]] = []
    for idx, line_name in enumerate(header):
        name = str(line_name).strip()
        if not name:
            continue
        line_order.append((str(idx), name))  # (line_index, line_name)

    items = data.get("items") or {}

    # Базовые колонки
    row_values = [
        date,
        user,
        dest_chat if dest_chat else chat_id,
        data["establishment"],
        data.get("person") or "",
        message.text,  # контакт
    ]

    # Далее по каждой линейке колонка с ароматами через запятую
    description_lines = []
    for line_id, line_name in line_order:
        line_items = items.get(line_id, [])
        if line_items:
            cell_value = ", ".join(line_items)
            row_values.append(cell_value)
            description_lines.append(f"{line_name}: {cell_value}")
        else:
            row_values.append("")

    # Статус и message_id в конце строки
    row_values.append("")      # статус (пока пустой)
    row_values.append(msg_id)  # message_id

    append_row(row_values)

    await message.answer(
        "Заявка создана и отправлена в таблицу.",
        reply_markup=get_main_menu(),
    )

    # Текст заявки для чата дистрибьютора
    details_text = "\n".join(description_lines) if description_lines else "—"

    await message.bot.send_message(
        chat_id=int(dest_chat),
        text=(
            f"Заявка от {user}\n"
            f"Заведение: {data['establishment']}\n"
            f"Ароматы:\n{details_text}\n"
            f"С кем вёлся диалог: {data.get('person') or '—'}\n"
            f"Контакт: {message.text}"
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтверждено", callback_data="confirm"),
                InlineKeyboardButton(text="❌ Не отгружено", callback_data="reject")
            ]
        ])
    )

    await state.clear()

# Обработка подтверждения заявки
@router.callback_query(F.data == "confirm")
async def confirm_request(callback: types.CallbackQuery):
    text = callback.message.text
    await callback.answer("Подтверждено", show_alert=False)
    update_status(callback.message.message_id, "YES")
    await callback.message.edit_text(text + "\n\n✅ Подтверждено")

# Обработка отказа (не отгружено)
@router.callback_query(F.data == "reject")
async def reject_request(callback: types.CallbackQuery):
    text = callback.message.text
    await callback.answer("Отмечено как не отгружено", show_alert=False)
    update_status(callback.message.message_id, "NO")
    await callback.message.edit_text(text + "\n\n❌ Не отгружено")

@router.callback_query(F.data.startswith("est_"))
async def choose_establishment(callback: types.CallbackQuery, state: FSMContext):
    est = callback.data.replace("est_", "")
    await state.update_data(establishment=est, items={})
    await state.set_state(RequestForm.line)
    await callback.message.edit_text(
        "Выбери линейку (можно несколько):",
        reply_markup=await get_lines_keyboard(add_done=True),
    )

@router.callback_query(F.data.startswith("estpage_"))
async def paginate_establishments(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.replace("estpage_", ""))
    data = await state.get_data()
    establishments = data.get("est_search") or get_establishments_for(
        callback.from_user.username
    )
    await state.update_data(est_page=page)
    keyboard = build_establishments_keyboard(establishments, page)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
