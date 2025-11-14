from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.services.sheets import read_sheet


async def get_sku_keyboard(
    line_index: str,
    selected: set[str] | None = None,
) -> InlineKeyboardMarkup:
    """
    Клавиатура с ароматами по выбранной линейке.

    Лист SKU:
      - первая строка: названия линеек (линии)
      - далее: в каждой колонке свои ароматы.

    line_index — индекс колонки (строка) из callback_data: line_<index>.

    При нажатии на аромат он помечается галочкой (мультивыбор).
    callback_data для SKU: sku_<название>

    Дополнительно добавляются кнопки:
      - ✅ Готово с этой линейкой (sku_done)
      - ⬅ Назад к линейкам (sku_back)
    """
    rows = read_sheet("SKU")
    if not rows:
        return InlineKeyboardMarkup(inline_keyboard=[])

    # безопасно парсим индекс колонки
    try:
        col = int(line_index)
    except (TypeError, ValueError):
        col = 0

    selected = selected or set()
    buttons: list[list[InlineKeyboardButton]] = []

    # пропускаем заголовок (первую строку с названиями линеек)
    for row in rows[1:]:
        if len(row) <= col:
            continue

        sku_name = str(row[col]).strip()

        # пропускаем пустые и технические значения, чтобы не ломать логику
        if not sku_name or sku_name.lower() in {"back", "sku_back", "назад", "⬅"}:
            continue

        key = sku_name[:20]  # безопасный короткий ключ, используется и в selected, и в callback_data

        text = f"✅ {sku_name}" if key in selected else sku_name

        buttons.append(
            [
                InlineKeyboardButton(
                    text=text,
                    callback_data=f"sku_{key}",
                )
            ]
        )

    # Управляющие кнопки по линейке
    buttons.append(
        [
            InlineKeyboardButton(
                text="✅ Готово с этой линейкой",
                callback_data="sku_done",
            )
        ]
    )
    buttons.append(
        [
            InlineKeyboardButton(
                text="⬅ Назад к линейкам",
                callback_data="sku_back",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)
