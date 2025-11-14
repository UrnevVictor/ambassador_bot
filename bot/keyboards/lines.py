from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.services.sheets import read_sheet


async def get_lines_keyboard(add_done: bool = False) -> InlineKeyboardMarkup:
    """
    Клавиатура с линейками на основе заголовка листа SKU.

    Ожидается структура листа SKU:
      - первая строка: названия линеек (Bliss, White Line, Black Line, Cigar Line)
      - ниже по столбцам — ароматы.

    callback_data для выбора линейки: line_<index>, где index — номер столбца (0,1,2,...).
    """
    try:
        rows = read_sheet("SKU")
    except Exception as e:
        print(f"[get_lines_keyboard] ERROR reading sheet: {e}")
        return InlineKeyboardMarkup(inline_keyboard=[])

    if not rows:
        return InlineKeyboardMarkup(inline_keyboard=[])

    header = rows[0]
    buttons = []

    for idx, line_name in enumerate(header):
        name = str(line_name).strip()
        if not name:
            continue
        buttons.append(
            [
                InlineKeyboardButton(
                    text=name,
                    callback_data=f"line_{idx}",
                )
            ]
        )

    if add_done:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="✅ Завершить выбор ароматов",
                    callback_data="lines_done",
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=buttons)
