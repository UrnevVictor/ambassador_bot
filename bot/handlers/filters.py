from aiogram import Router, types
from aiogram.filters import Command
from bot.services.sheets import get_all_requests

router = Router()

# /confirmed — показать подтверждённые заявки
@router.message(Command("confirmed"))
async def confirmed_requests(message: types.Message):
    rows = get_all_requests()
    confirmed = [r for r in rows if len(r) > 8 and r[8].strip().lower() in ("yes", "да", "подтверждено")] 

    if not confirmed:
        await message.answer("Нет подтверждённых заявок.")
        return

    text = "Подтверждённые заявки:\n\n"
    for r in confirmed:
        text += f"Аромат: {r[6]} | Линейка: {r[5]} | Контакт: {r[4]}\n"

    await message.answer(text)

# /unconfirmed — показать НЕ подтверждённые заявки
@router.message(Command("unconfirmed"))
async def unconfirmed_requests(message: types.Message):
    rows = get_all_requests()
    unconfirmed = [r for r in rows if len(r) > 8 and (r[8] == "" or r[8].strip().lower() in ("no", "нет", "не отгружено"))]

    if not unconfirmed:
        await message.answer("Все заявки подтверждены.")
        return

    text = "Неподтверждённые заявки:\n\n"
    for r in unconfirmed:
        text += f"Аромат: {r[6]} | Линейка: {r[5]} | Контакт: {r[4]}\n"

    await message.answer(text)

# /all — все заявки
@router.message(Command("all"))
async def all_requests(message: types.Message):
    rows = get_all_requests()
    if not rows:
        await message.answer("Заявок нет.")
        return

    text = "Все заявки:\n\n"
    for r in rows:
        text += f"Аромат: {r[6]} | Линейка: {r[5]} | Статус: {r[8] or '—'}\n"

    await message.answer(text)

# /by_line <название> — сортировка по линейке
@router.message(Command("by_line"))
async def by_line(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Укажи линейку. Пример: /by_line CLASSIC")
        return

    line = parts[1].strip().lower()
    rows = get_all_requests()
    filtered = [r for r in rows if r[5].strip().lower() == line]

    if not filtered:
        await message.answer("По этой линейке нет заявок.")
        return

    text = f"Заявки по линейке {parts[1]}:\n\n"
    for r in filtered:
        text += f"Аромат: {r[6]} | Контакт: {r[4]} | Статус: {r[8] or '—'}\n"

    await message.answer(text)

# /by_amb <имя> — сортировка по амбассадору
@router.message(Command("by_amb"))
async def by_amb(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Укажи имя амбассадора. Пример: /by_amb Виктор")
        return

    ambassador = parts[1].strip().lower()
    rows = get_all_requests()
    filtered = [r for r in rows if len(r) > 1 and r[1].strip().lower() == ambassador]

    if not filtered:
        await message.answer("По этому амбассадору нет заявок.")
        return

    text = f"Заявки амбассадора {parts[1]}:\n\n"
    for r in filtered:
        text += f"Заведение: {r[3]} | Адрес: {r[4]} | Линейка: {r[5]} | Аромат: {r[6]} | Статус: {r[8] or '—'}\n"

    await message.answer(text)
