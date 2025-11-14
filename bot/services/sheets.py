from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import re
from bot.config import (
    SPREADSHEET_ID as TARGET_SPREADSHEET_ID,
    GOOGLE_SERVICE_FILE,
    SOURCE_SPREADSHEET_ID,
)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def _normalize_text(value: str) -> str:
    """Базовая нормализация строки: нижний регистр, ё→е, сжатие пробелов."""
    if not value:
        return ""
    value = value.strip().lower()
    value = value.replace("ё", "е")
    value = re.sub(r"\s+", " ", value)
    return value


def _normalize_address(address: str) -> str:
    """Упрощённая нормализация адреса, убираем лишние служебные слова."""
    if not address:
        return ""
    address = _normalize_text(address)
    # максимально простая очистка, без жёстких правил
    for junk in ["россия,", "рф,", "г.", "город", "россия", "рф"]:
        address = address.replace(junk, "")
    address = re.sub(r"\s+", " ", address)
    return address.strip()


def _normalize_venue_name(name: str, address: str | None = None) -> str:
    """Нормализованный ключ заведения: имя + (адрес) в одном формате."""
    base = _normalize_text(name)
    if address:
        norm_addr = _normalize_address(address)
    else:
        norm_addr = ""
    if norm_addr:
        return f"{base} ({norm_addr})"
    return base

def get_service():
    creds = Credentials.from_service_account_file(
        GOOGLE_SERVICE_FILE,
        scopes=SCOPES
    )
    service = build("sheets", "v4", credentials=creds)
    return service.spreadsheets()

def append_row(values: list, sheet_name="Заявки"):
    service = get_service()
    body = {"values": [values]}
    service.values().append(
        spreadsheetId=TARGET_SPREADSHEET_ID,
        range=f"{sheet_name}!A1",
        valueInputOption="USER_ENTERED",
        body=body
    ).execute()

def update_cell(row: int, column_letter: str, value, sheet_name="Заявки"):
    service = get_service()
    service.values().update(
        spreadsheetId=TARGET_SPREADSHEET_ID,
        range=f"{sheet_name}!{column_letter}{row}",
        valueInputOption="RAW",
        body={"values": [[value]]}
    ).execute()

def read_sheet(sheet_name: str, source: bool = False):
    service = get_service()
    spreadsheetId = SOURCE_SPREADSHEET_ID if source else TARGET_SPREADSHEET_ID
    result = service.values().get(
        spreadsheetId=spreadsheetId,
        range=f"{sheet_name}!A1:Z9999"
    ).execute()
    return result.get("values", [])


# New function: get_venues_by_ambassador
def get_venues_by_ambassador(ambassador_username: str, sheet_name: str = "Заведения"):
    """
    Возвращает список заведений, закреплённых за амбассадором, из РАБОЧЕЙ таблицы.

    Ожидаемый формат строки на листе `sheet_name`:
    0 - username амбассадора (@nickname)
    1 - название заведения (как показываем амбассадору)
    2 - адрес (опционально)
    3 - нормализованный ключ (опционально)
    """
    rows = read_sheet(sheet_name, source=False)
    venues: list[str] = []

    if not rows:
        return venues

    # пропускаем заголовок
    for row in rows[1:]:
        if len(row) < 2:
            continue
        if str(row[0]).strip().lower() == ambassador_username.strip().lower():
            venues.append(row[1])

    return venues

def get_venue_full(ambassador_username: str, venue_name: str, sheet_name: str = "Заведения"):
    """
    Возвращает полное описание заведения для амбассадора:
    (venue_name, address, normalized_key)

    Ищет строго по амбассадору и названию заведения.
    """
    rows = read_sheet(sheet_name, source=False)

    if not rows:
        return None

    # пропускаем заголовок
    for row in rows[1:]:
        if len(row) < 4:
            continue

        amb = str(row[0]).strip().lower()
        name = str(row[1]).strip()

        if amb == ambassador_username.strip().lower() and name == venue_name.strip():
            address = str(row[2]).strip() if len(row) > 2 else ""
            norm_key = str(row[3]).strip() if len(row) > 3 else ""
            return {
                "name": name,
                "address": address,
                "normalized_key": norm_key,
            }

    return None


def build_venues_from_source(
    source_sheet_name: str = "Ответы на форму (1)",
    target_sheet_name: str = "Заведения",
) -> int:
    """
    Считывает живую таблицу (SOURCE_SPREADSHEET_ID, лист `source_sheet_name`),
    собирает уникальные заведения по амбассадорам и записывает их
    в рабочую таблицу (TARGET_SPREADSHEET_ID, лист `target_sheet_name`).

    Ожидаемый формат исходного листа:
    B (индекс 1) - амбассадор (@username)
    D (индекс 3) - название заведения
    E (индекс 4) - адрес заведения

    В целевом листе формируем столбцы:
    A - ambassador_username
    B - venue_name
    C - address
    D - normalized_key
    """
    rows = read_sheet(source_sheet_name, source=True)
    if not rows:
        return 0

    # пропускаем первую строку как заголовок
    header_skipped = False
    venues_map: dict[tuple[str, str], tuple[str, str, str, str]] = {}

    for row in rows:
        if not header_skipped:
            header_skipped = True
            continue

        if len(row) <= 4:
            continue

        ambassador = str(row[1]).strip()
        venue_name = str(row[3]).strip()
        address = str(row[4]).strip()

        if not ambassador or not venue_name:
            continue

        norm_key = _normalize_venue_name(venue_name, address)
        map_key = (ambassador.lower(), norm_key)

        # храним только одну запись на ключ
        if map_key in venues_map:
            continue

        venues_map[map_key] = (ambassador, venue_name, address, norm_key)

    # готовим данные для записи
    data = [["ambassador_username", "venue_name", "address", "normalized_key"]]
    for _, record in venues_map.items():
        data.append(list(record))

    service = get_service()

    # очищаем целевой лист
    service.values().clear(
        spreadsheetId=TARGET_SPREADSHEET_ID,
        range=f"{target_sheet_name}!A1:Z9999",
    ).execute()

    # пишем новые данные
    service.values().update(
        spreadsheetId=TARGET_SPREADSHEET_ID,
        range=f"{target_sheet_name}!A1",
        valueInputOption="RAW",
        body={"values": data},
    ).execute()

    return len(data) - 1

def get_all_requests(sheet_name: str = "Заявки"):
    """Возвращает все строки из указанного листа, кроме строки заголовков.

    Внимание: структура листа может меняться.
    Сейчас предполагается формат:
      0 - дата
      1 - амбассадор (user)
      2 - chat_id дистрибьютора
      3 - заведение
      4 - имя контакта (с кем вёлся диалог)
      5 - контакт (телефон/Telegram)
      6..N-3 - колонки по линейкам (в ячейках ароматы через запятую)
      N-2 - статус ("" / "YES" / "NO")
      N-1 - message_id
    """
    values = read_sheet(sheet_name)

    if not values:
        return []

    cleaned = []
    for row in values:
        # пропускаем возможную строку заголовков
        if row and str(row[0]).strip().lower() in ("дата", "date"):
            continue
        cleaned.append(row)

    return cleaned

def update_status(message_id, status, sheet_name: str = "Заявки"):
    rows = read_sheet(sheet_name)
    service = get_service()

    for idx, row in enumerate(rows, start=1):
        if not row:
            continue

        last_index = len(row) - 1
        msg_index = last_index

        # последняя колонка хранит message_id, предпоследняя - статус
        if msg_index < 1:
            continue

        if str(row[msg_index]) == str(message_id):
            status_index = last_index - 1

            # вычисляем букву колонки по индексу (поддержка до Z)
            col_letter = chr(ord("A") + status_index)
            service.values().update(
                spreadsheetId=TARGET_SPREADSHEET_ID,
                range=f"{sheet_name}!{col_letter}{idx}",
                valueInputOption="RAW",
                body={"values": [[status]]}
            ).execute()
            break

def save_chat_link(ambassador_username: str, chat_id: int, sheet_name: str = "Чаты"):
    """
    Сохраняет связку амбассадор → chat_id.
    Если амбассадор уже есть — перезаписываем chat_id.
    """
    service = get_service()

    # читаем текущий лист
    rows = read_sheet(sheet_name)
    updated = False
    new_rows = []

    if not rows:
        rows = [["ambassador_username", "chat_id"]]

    # пробегаем строки, ищем амбассадора
    for row in rows:
        if len(row) >= 1 and row[0].strip().lower() == ambassador_username.strip().lower():
            new_rows.append([ambassador_username, str(chat_id)])
            updated = True
        else:
            new_rows.append(row)

    # если не найден — добавляем
    if not updated:
        new_rows.append([ambassador_username, str(chat_id)])

    # очищаем лист
    service.values().clear(
        spreadsheetId=TARGET_SPREADSHEET_ID,
        range=f"{sheet_name}!A1:Z9999",
    ).execute()

    # записываем заново
    service.values().update(
        spreadsheetId=TARGET_SPREADSHEET_ID,
        range=f"{sheet_name}!A1",
        valueInputOption="RAW",
        body={"values": new_rows},
    ).execute()


def get_chat_link(ambassador_username: str, sheet_name: str = "Чаты") -> str | None:
    """
    Возвращает chat_id, привязанный к амбассадору.
    """
    rows = read_sheet(sheet_name)

    if not rows:
        return None

    # пропускаем заголовок
    for row in rows[1:]:
        if len(row) >= 2 and row[0].strip().lower() == ambassador_username.strip().lower():
            return row[1]

    return None

def write_chat_link(ambassador_username: str, chat_id: int, sheet_name: str = "Чаты"):
    """
    Обёртка над save_chat_link для совместимости.
    """
    return save_chat_link(ambassador_username, chat_id, sheet_name)

def is_employee(username: str, sheet_name: str = "Сотрудники") -> bool:
    """
    Проверяет, есть ли username в списке сотрудников.
    Лист должен иметь формат:
        A: username (например: @viktor)
    """
    rows = read_sheet(sheet_name)

    if not rows:
        return False

    # пропускаем заголовок
    for row in rows[1:]:
        if len(row) == 0:
            continue

        if row[0].strip().lower() == username.strip().lower():
            return True

    return False

if __name__ == "__main__":
    # Утилита для ручной синхронизации заведений из живой таблицы.
    try:
        count = build_venues_from_source()
        print(f"VENUES SYNC DONE, rows: {count}")
    except Exception as e:
        print("ERROR:", e)
