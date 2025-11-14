from aiogram import Router, types, F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from bot.services.sheets import read_sheet, update_cell


router = Router()

# Переменная для отслеживания процесса установки чата
pending_chat_setup = {}

# Кнопка "Подтвердить"
def confirm_keyboard(request_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подтверждено", callback_data=f"confirm_{request_id}")],
        [InlineKeyboardButton(text="Не отгружено", callback_data=f"reject_{request_id}")]
    ])

@router.callback_query(F.data.startswith("confirm_"))
async def confirm_request(callback: types.CallbackQuery):
    request_id = callback.data.split("_")[1]

    rows = read_sheet("Заявки")

    # Ищем нужную строку
    for index, row in enumerate(rows, start=1):
        if len(row) > 9 and row[9] == request_id:
            update_cell(index, "I", "Да", "Заявки")
            await callback.message.edit_text("Заявка подтверждена.")
            await callback.answer("Готово")
            return

    await callback.answer("Не найдено", show_alert=True)

@router.callback_query(F.data.startswith("reject_"))
async def reject_request(callback: types.CallbackQuery):
    request_id = callback.data.split("_")[1]

    rows = read_sheet("Заявки")

    for index, row in enumerate(rows, start=1):
        if len(row) > 9 and row[9] == request_id:
            update_cell(index, "I", "Нет", "Заявки")
            await callback.message.edit_text("Заявка отмечена как НЕ ОТГРУЖЕНА.")
            await callback.answer("Зафиксировано")
            return

    await callback.answer("Не найдено", show_alert=True)


# Обработчик команды /setchat
@router.message(commands=["setchat"])
async def set_chat_start(message: types.Message):
    await message.answer("Отправь мне *ID чата*, куда бот должен присылать заявки.\n\nЧтобы получить ID:\n1. Добавь бота в чат\n2. Напиши в чат любое сообщение\n3. Перешли это сообщение сюда", parse_mode="Markdown")
    pending_chat_setup[message.from_user.id] = True

# Обработчик для получения ID чата из пересланного сообщения
@router.message()
async def set_chat_finish(message: types.Message):
    user_id = message.from_user.id

    if user_id not in pending_chat_setup:
        return

    chat_id = None

    if message.forward_from_chat:
        chat_id = message.forward_from_chat.id
    elif message.chat:
        chat_id = message.chat.id

    if not chat_id:
        await message.answer("Не удалось определить ID. Перешли сообщение из нужного чата.")
        return

    # Временно сохраняем в файл (потом интегрируем в Google Sheets)
    with open("chat_links.txt", "a") as f:
        f.write(f"{user_id}:{chat_id}\n")

    await message.answer(f"Готово. Чат сохранён.\nID: `{chat_id}`", parse_mode="Markdown")

    del pending_chat_setup[user_id]