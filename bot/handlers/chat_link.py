from aiogram import Router
from aiogram.types import ChatMemberUpdated

from bot.services.sheets import write_chat_link

router = Router()


@router.my_chat_member()
async def on_bot_added(event: ChatMemberUpdated):
    """
    Автоматическая привязка чата дистрибьютора.
    Срабатывает, когда бота добавляют в группу.
    """
    old = event.old_chat_member
    new = event.new_chat_member

    # бот был добавлен в чат
    if old.status in {"left", "kicked"} and new.status in {"member", "administrator"}:
        chat_id = event.chat.id

        # Кто добавил бота — это амбассадор
        username = event.from_user.username
        if not username:
            return

        ambassador = f"@{username}"

        # проверяем, что добавивший — сотрудник
        from bot.services.sheets import is_employee
        if not is_employee(ambassador):
            # не сотрудник — игнорируем
            return

        # сохраняем привязку
        write_chat_link(ambassador, chat_id)

        # отправляем подтверждение
        try:
            await event.bot.send_message(
                chat_id,
                f"Чат успешно привязан к амбассадору {ambassador}.\n"
                f"Заявки будут приходить сюда."
            )
        except:
            pass

from aiogram import types
from aiogram.filters import Command
@router.message(Command("bind"))
async def manual_bind(message: types.Message):
    """
    Ручная привязка чата командой /bind.
    Работает в группе, даже если Telegram не прислал my_chat_member.
    """
    # команда должна выполняться только в группе
    if message.chat.type not in {"group", "supergroup"}:
        await message.answer("Команда доступна только в группах.")
        return

    username = message.from_user.username
    if not username:
        return

    ambassador = f"@{username}"

    # проверяем, что это сотрудник
    from bot.services.sheets import is_employee, write_chat_link
    if not is_employee(ambassador):
        return

    chat_id = message.chat.id
    write_chat_link(ambassador, chat_id)

    await message.reply(
        f"Чат успешно привязан к амбассадору {ambassador}.\n"
        f"Заявки теперь будут приходить сюда."
    )