from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.database import Order, OrderRepository
from bot.keyboards import (
    admin_order_keyboard,
    manager_input_keyboard,
    manager_panel_keyboard,
    manager_remove_keyboard,
    payment_keyboard,
    receipt_review_keyboard,
    stars_keyboard,
)

router = Router(name=__name__)


class Purchase(StatesGroup):
    custom_amount = State()
    payment = State()
    receipt = State()
    recipient = State()


class AdminPanel(StatesGroup):
    waiting_manager_id = State()
    waiting_price = State()
    waiting_presets = State()
    waiting_payment_details = State()
    waiting_limits = State()


def calculate_total(stars: int, price_per_star: Decimal) -> Decimal:
    return (Decimal(stars) * price_per_star).quantize(Decimal("0.01"))


def format_money(amount: Decimal) -> str:
    return f"{amount:,.2f}".replace(",", " ").replace(".", ",")


def normalize_username(value: str) -> str | None:
    username = value.strip()
    if username.startswith("https://t.me/"):
        username = username.removeprefix("https://t.me/")
    username = username.lstrip("@").strip()
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", username) is None:
        return None
    return f"@{username}"


async def show_catalog(
    message: Message,
    state: FSMContext,
    config: Config,
    orders: OrderRepository,
    *,
    viewer_id: int | None = None,
) -> None:
    await state.clear()
    current_user_id = viewer_id if viewer_id is not None else message.from_user.id
    price = orders.get_price_per_star(config.price_per_star_rub)
    presets = orders.get_star_presets()
    await message.answer(
        "<b>Покупка Telegram Stars ⭐</b>\n\n"
        "Выберите количество звёзд или введите своё.\n"
        f"Цена: <b>{format_money(price)} ₽ за 1 ⭐</b>",
        reply_markup=stars_keyboard(
            presets=presets, is_owner=current_user_id == config.owner_id
        ),
    )


@router.message(CommandStart())
async def start(
    message: Message, state: FSMContext, config: Config, orders: OrderRepository
) -> None:
    await show_catalog(message, state, config, orders)


@router.message(Command("cancel"))
async def cancel(
    message: Message, state: FSMContext, config: Config, orders: OrderRepository
) -> None:
    await show_catalog(message, state, config, orders)


def manager_panel_text(
    manager_ids: tuple[int, ...],
    price: Decimal,
    presets: tuple[int, ...],
    config: Config,
    orders: OrderRepository,
) -> str:
    if not manager_ids:
        manager_list = "Подключённых менеджеров пока нет."
    else:
        manager_list = "\n".join(
            f"• <code>{manager_id}</code>" for manager_id in manager_ids
        )
    min_stars, max_stars = orders.get_star_limits(config.min_stars, config.max_stars)
    payment_details = orders.get_payment_details(config.payment_details)
    return (
        "⚙️ <b>Админ-панель</b>\n\n"
        "Новые заявки автоматически приходят вам и всем подключённым менеджерам.\n\n"
        f"💰 Цена: <b>{format_money(price)} ₽ за 1 ⭐</b>\n"
        f"⭐ Кнопки: <b>{', '.join(map(str, presets))}</b>\n\n"
        f"↔️ Произвольный заказ: <b>от {min_stars} до {max_stars} ⭐</b>\n\n"
        f"💳 <b>Реквизиты:</b>\n{escape(payment_details)}\n\n"
        f"<b>Менеджеры:</b>\n{manager_list}"
    )


def current_panel_data(
    config: Config, orders: OrderRepository
) -> tuple[Decimal, tuple[int, ...], tuple[int, ...]]:
    return (
        orders.get_price_per_star(config.price_per_star_rub),
        orders.get_star_presets(),
        orders.list_manager_ids(),
    )


async def owner_only(callback: CallbackQuery, config: Config) -> bool:
    if callback.from_user.id == config.owner_id:
        return True
    await callback.answer("Доступно только владельцу", show_alert=True)
    return False


@router.callback_query(F.data == "panel:main")
async def open_admin_panel(
    callback: CallbackQuery,
    state: FSMContext,
    config: Config,
    orders: OrderRepository,
) -> None:
    if not await owner_only(callback, config):
        return
    await callback.answer()
    await state.clear()
    price, presets, manager_ids = current_panel_data(config, orders)
    if callback.message:
        await callback.message.edit_text(
            manager_panel_text(manager_ids, price, presets, config, orders),
            reply_markup=manager_panel_keyboard(manager_ids),
        )


@router.callback_query(F.data == "panel:price")
async def request_price(
    callback: CallbackQuery, state: FSMContext, config: Config
) -> None:
    if not await owner_only(callback, config):
        return
    await callback.answer()
    await state.set_state(AdminPanel.waiting_price)
    if callback.message:
        await callback.message.edit_text(
            "💰 <b>Изменение цены</b>\n\n"
            "Отправьте новую цену одной звезды в рублях.\n"
            "Пример: <code>1,75</code>",
            reply_markup=manager_input_keyboard(),
        )


@router.message(AdminPanel.waiting_price)
async def save_price(
    message: Message,
    state: FSMContext,
    config: Config,
    orders: OrderRepository,
) -> None:
    if message.from_user.id != config.owner_id:
        await state.clear()
        return
    try:
        price = Decimal((message.text or "").strip().replace(",", ".")).quantize(
            Decimal("0.01")
        )
    except InvalidOperation:
        await message.answer("Введите цену числом, например: <code>1,75</code>.")
        return
    if not price.is_finite() or price <= 0 or price > Decimal("100000"):
        await message.answer("Цена должна быть больше нуля и не выше 100 000 ₽.")
        return
    orders.set_price_per_star(price)
    await state.clear()
    current_price, presets, manager_ids = current_panel_data(config, orders)
    await message.answer(
        "✅ Цена сохранена.\n\n"
        + manager_panel_text(manager_ids, current_price, presets, config, orders),
        reply_markup=manager_panel_keyboard(manager_ids),
    )


@router.callback_query(F.data == "panel:payment_details")
async def request_payment_details(
    callback: CallbackQuery, state: FSMContext, config: Config
) -> None:
    if not await owner_only(callback, config):
        return
    await callback.answer()
    await state.set_state(AdminPanel.waiting_payment_details)
    if callback.message:
        await callback.message.edit_text(
            "💳 <b>Изменение реквизитов</b>\n\n"
            "Отправьте новый текст реквизитов одним сообщением. Можно использовать "
            "несколько строк.",
            reply_markup=manager_input_keyboard(),
        )


@router.message(AdminPanel.waiting_payment_details)
async def save_payment_details(
    message: Message,
    state: FSMContext,
    config: Config,
    orders: OrderRepository,
) -> None:
    if message.from_user.id != config.owner_id:
        await state.clear()
        return
    payment_details = (message.text or "").strip()
    if not 5 <= len(payment_details) <= 1500:
        await message.answer("Реквизиты должны содержать от 5 до 1500 символов.")
        return
    orders.set_payment_details(payment_details)
    await state.clear()
    price, presets, manager_ids = current_panel_data(config, orders)
    await message.answer(
        "✅ Реквизиты сохранены.\n\n"
        + manager_panel_text(manager_ids, price, presets, config, orders),
        reply_markup=manager_panel_keyboard(manager_ids),
    )


@router.callback_query(F.data == "panel:limits")
async def request_limits(
    callback: CallbackQuery, state: FSMContext, config: Config
) -> None:
    if not await owner_only(callback, config):
        return
    await callback.answer()
    await state.set_state(AdminPanel.waiting_limits)
    if callback.message:
        await callback.message.edit_text(
            "↔️ <b>Лимиты произвольного заказа</b>\n\n"
            "Отправьте минимальное и максимальное количество через пробел.\n"
            "Пример: <code>50 100000</code>",
            reply_markup=manager_input_keyboard(),
        )


@router.message(AdminPanel.waiting_limits)
async def save_limits(
    message: Message,
    state: FSMContext,
    config: Config,
    orders: OrderRepository,
) -> None:
    if message.from_user.id != config.owner_id:
        await state.clear()
        return
    parts = [
        part
        for part in re.split(r"[\s,;]+", (message.text or "").strip())
        if part
    ]
    if len(parts) != 2 or any(not part.isdigit() for part in parts):
        await message.answer("Введите два целых числа, например: <code>50 100000</code>.")
        return
    min_stars, max_stars = map(int, parts)
    if min_stars <= 0 or max_stars < min_stars or max_stars > 100_000_000:
        await message.answer(
            "Минимум должен быть больше нуля, максимум — не меньше минимума "
            "и не выше 100 000 000."
        )
        return
    orders.set_star_limits(min_stars, max_stars)
    await state.clear()
    price, presets, manager_ids = current_panel_data(config, orders)
    await message.answer(
        "✅ Лимиты сохранены.\n\n"
        + manager_panel_text(manager_ids, price, presets, config, orders),
        reply_markup=manager_panel_keyboard(manager_ids),
    )


@router.callback_query(F.data == "panel:presets")
async def request_presets(
    callback: CallbackQuery, state: FSMContext, config: Config
) -> None:
    if not await owner_only(callback, config):
        return
    await callback.answer()
    await state.set_state(AdminPanel.waiting_presets)
    if callback.message:
        await callback.message.edit_text(
            "⭐ <b>Изменение готовых вариантов</b>\n\n"
            "Отправьте от 1 до 6 вариантов через пробел или запятую.\n"
            "Пример: <code>50 100 500</code>",
            reply_markup=manager_input_keyboard(),
        )


@router.message(AdminPanel.waiting_presets)
async def save_presets(
    message: Message,
    state: FSMContext,
    config: Config,
    orders: OrderRepository,
) -> None:
    if message.from_user.id != config.owner_id:
        await state.clear()
        return
    parts = [
        part
        for part in re.split(r"[\s,;]+", (message.text or "").strip())
        if part
    ]
    if not 1 <= len(parts) <= 6 or any(not part.isdigit() for part in parts):
        await message.answer(
            "Укажите от 1 до 6 целых чисел, например: <code>50 100 500</code>."
        )
        return
    presets = tuple(dict.fromkeys(int(part) for part in parts))
    if len(presets) != len(parts):
        await message.answer("Варианты количества не должны повторяться.")
        return
    min_stars, max_stars = orders.get_star_limits(config.min_stars, config.max_stars)
    if any(not min_stars <= value <= max_stars for value in presets):
        await message.answer(
            f"Каждый вариант должен быть от {min_stars} до {max_stars}."
        )
        return
    orders.set_star_presets(presets)
    await state.clear()
    price, current_presets, manager_ids = current_panel_data(config, orders)
    await message.answer(
        "✅ Кнопки сохранены.\n\n"
        + manager_panel_text(manager_ids, price, current_presets, config, orders),
        reply_markup=manager_panel_keyboard(manager_ids),
    )


@router.callback_query(F.data == "panel:add")
async def request_manager_id(
    callback: CallbackQuery, state: FSMContext, config: Config
) -> None:
    if not await owner_only(callback, config):
        return
    await callback.answer()
    await state.set_state(AdminPanel.waiting_manager_id)
    if callback.message:
        await callback.message.edit_text(
            "➕ <b>Добавление менеджера</b>\n\n"
            "Отправьте числовой Telegram ID менеджера. Его можно узнать у @userinfobot.",
            reply_markup=manager_input_keyboard(),
        )


@router.message(AdminPanel.waiting_manager_id)
async def save_manager(
    message: Message,
    state: FSMContext,
    config: Config,
    orders: OrderRepository,
) -> None:
    if message.from_user.id != config.owner_id:
        await state.clear()
        return
    raw_id = (message.text or "").strip()
    if not raw_id.isdigit():
        await message.answer(
            "Отправьте только числовой Telegram ID.",
            reply_markup=manager_input_keyboard(),
        )
        return
    manager_id = int(raw_id)
    if manager_id == config.owner_id:
        result_text = "Владелец уже имеет полный доступ."
    elif orders.add_manager(manager_id):
        result_text = (
            f"✅ Менеджеру <code>{manager_id}</code> выдан доступ.\n"
            "Попросите его открыть бота и нажать Start."
        )
    else:
        result_text = "Этот менеджер уже имеет доступ."
    await state.clear()
    price, presets, manager_ids = current_panel_data(config, orders)
    await message.answer(
        f"{result_text}\n\n"
        f"{manager_panel_text(manager_ids, price, presets, config, orders)}",
        reply_markup=manager_panel_keyboard(manager_ids),
    )


@router.callback_query(F.data.startswith("panel:remove:"))
async def confirm_manager_removal(callback: CallbackQuery, config: Config) -> None:
    if not await owner_only(callback, config):
        return
    await callback.answer()
    manager_id = int((callback.data or "").rsplit(":", maxsplit=1)[1])
    if callback.message:
        await callback.message.edit_text(
            f"Удалить менеджера <code>{manager_id}</code> и закрыть ему доступ к новым заявкам?",
            reply_markup=manager_remove_keyboard(manager_id),
        )


@router.callback_query(F.data.startswith("panel:confirm_remove:"))
async def remove_manager(
    callback: CallbackQuery,
    state: FSMContext,
    config: Config,
    orders: OrderRepository,
) -> None:
    if not await owner_only(callback, config):
        return
    manager_id = int((callback.data or "").rsplit(":", maxsplit=1)[1])
    removed = orders.remove_manager(manager_id)
    await callback.answer("Доступ отозван" if removed else "Менеджер уже удалён")
    await state.clear()
    price, presets, manager_ids = current_panel_data(config, orders)
    if callback.message:
        await callback.message.edit_text(
            manager_panel_text(manager_ids, price, presets, config, orders),
            reply_markup=manager_panel_keyboard(manager_ids),
        )


@router.callback_query(F.data == "restart")
async def restart(
    callback: CallbackQuery,
    state: FSMContext,
    config: Config,
    orders: OrderRepository,
) -> None:
    await callback.answer()
    if callback.message:
        await show_catalog(
            callback.message, state, config, orders, viewer_id=callback.from_user.id
        )


@router.callback_query(F.data == "stars:custom")
async def choose_custom(
    callback: CallbackQuery,
    state: FSMContext,
    config: Config,
    orders: OrderRepository,
) -> None:
    await callback.answer()
    await state.set_state(Purchase.custom_amount)
    min_stars, max_stars = orders.get_star_limits(config.min_stars, config.max_stars)
    if callback.message:
        await callback.message.answer(
            f"Введите количество звёзд числом от {min_stars} до {max_stars}:"
        )


@router.message(Purchase.custom_amount)
async def custom_amount(
    message: Message,
    state: FSMContext,
    config: Config,
    orders: OrderRepository,
) -> None:
    raw_value = (message.text or "").strip().replace(" ", "")
    if not raw_value.isdigit():
        await message.answer("Введите целое число, например: <b>750</b>")
        return
    stars = int(raw_value)
    min_stars, max_stars = orders.get_star_limits(config.min_stars, config.max_stars)
    if not min_stars <= stars <= max_stars:
        await message.answer(
            f"Допустимо от {min_stars} до {max_stars} звёзд. "
            "Введите другое количество:"
        )
        return
    await show_payment(message, state, stars, config, orders)


@router.callback_query(F.data.startswith("stars:"))
async def choose_preset(
    callback: CallbackQuery,
    state: FSMContext,
    config: Config,
    orders: OrderRepository,
) -> None:
    await callback.answer()
    if not callback.message or callback.data is None:
        return
    stars = int(callback.data.split(":", maxsplit=1)[1])
    await show_payment(callback.message, state, stars, config, orders)


async def show_payment(
    message: Message,
    state: FSMContext,
    stars: int,
    config: Config,
    orders: OrderRepository,
) -> None:
    price = orders.get_price_per_star(config.price_per_star_rub)
    payment_details = orders.get_payment_details(config.payment_details)
    total = calculate_total(stars, price)
    await state.update_data(stars=stars, total=str(total))
    await state.set_state(Purchase.payment)
    await message.answer(
        "<b>Ваш заказ</b>\n\n"
        f"Количество: <b>{stars} ⭐</b>\n"
        f"К оплате: <b>{format_money(total)} ₽</b>\n\n"
        "<b>Реквизиты:</b>\n"
        f"{escape(payment_details)}\n\n"
        "После оплаты нажмите кнопку ниже и отправьте чек.",
        reply_markup=payment_keyboard(),
    )


@router.callback_query(Purchase.payment, F.data == "paid")
async def paid(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(Purchase.receipt)
    if callback.message:
        await callback.message.answer(
            "Отправьте чек <b>одним фото или PDF-документом</b>.\n"
            "Для отмены используйте /cancel."
        )


@router.message(Purchase.receipt, F.photo | F.document)
async def receipt(
    message: Message,
    state: FSMContext,
) -> None:
    if message.photo:
        receipt_file_id = message.photo[-1].file_id
        receipt_type = "photo"
    elif message.document:
        if message.document.mime_type not in {"application/pdf", "image/jpeg", "image/png"}:
            await message.answer("Пришлите чек фотографией или PDF-документом.")
            return
        receipt_file_id = message.document.file_id
        receipt_type = "document"
    else:  # pragma: no cover - protected by filter
        return

    await state.update_data(
        receipt_file_id=receipt_file_id,
        receipt_type=receipt_type,
    )
    await state.set_state(Purchase.recipient)
    await message.answer(
        "📎 <b>Файл получен.</b> Оплата ещё не подтверждена.\n\n"
        "Теперь укажите <b>@username</b>, на который нужно отправить звёзды.\n"
        "Пример: <code>@durov</code>"
    )


@router.message(Purchase.receipt)
async def invalid_receipt(message: Message) -> None:
    await message.answer("Нужен чек: отправьте фотографию или PDF-документ.")


@router.message(Purchase.recipient)
async def recipient(
    message: Message,
    state: FSMContext,
    bot: Bot,
    config: Config,
    orders: OrderRepository,
) -> None:
    recipient_username = normalize_username(message.text or "")
    if recipient_username is None:
        await message.answer(
            "Не похоже на корректный username. Отправьте его в формате "
            "<code>@username</code>."
        )
        return

    data = await state.get_data()
    order = orders.create(
        buyer_id=message.from_user.id,
        buyer_username=message.from_user.username,
        recipient_username=recipient_username,
        stars=int(data["stars"]),
        amount_rub=str(data["total"]),
        receipt_file_id=str(data["receipt_file_id"]),
        receipt_type=str(data["receipt_type"]),
    )
    await state.clear()

    await message.answer(
        f"🕓 <b>Заявка №{order.id} отправлена на проверку.</b>\n\n"
        f"Получатель: <b>{escape(recipient_username)}</b>\n"
        f"Количество: <b>{order.stars} ⭐</b>\n\n"
        "Фотография сама по себе не подтверждает оплату. После проверки чека "
        "бот пришлёт отдельное уведомление."
    )
    await notify_admins(bot, config, orders, order)


async def notify_admins(
    bot: Bot, config: Config, orders: OrderRepository, order: Order
) -> None:
    buyer = f"@{order.buyer_username}" if order.buyer_username else "username не задан"
    caption = (
        f"🆕 <b>Новая заявка №{order.id}</b>\n\n"
        f"Покупатель: {escape(buyer)}\n"
        f"Telegram ID: <code>{order.buyer_id}</code>\n"
        f"Получатель: <b>{escape(order.recipient_username)}</b>\n"
        f"Количество: <b>{order.stars} ⭐</b>\n"
        f"Сумма: <b>{escape(format_money(Decimal(order.amount_rub)))} ₽</b>"
    )
    recipient_ids = (config.owner_id, *orders.list_manager_ids())
    for admin_id in dict.fromkeys(recipient_ids):
        try:
            if order.receipt_type == "photo":
                await bot.send_photo(
                    admin_id,
                    order.receipt_file_id,
                    caption=caption,
                    reply_markup=receipt_review_keyboard(order.id),
                )
            else:
                await bot.send_document(
                    admin_id,
                    order.receipt_file_id,
                    caption=caption,
                    reply_markup=receipt_review_keyboard(order.id),
                )
        except (TelegramBadRequest, TelegramForbiddenError):
            # Один неверный/неактивный администратор не должен ломать заказ.
            continue


@router.callback_query(F.data.startswith("review:"))
async def review_receipt(
    callback: CallbackQuery,
    bot: Bot,
    config: Config,
    orders: OrderRepository,
) -> None:
    if not orders.is_staff(callback.from_user.id, config.owner_id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    if callback.data is None:
        return

    _, status, raw_order_id = callback.data.split(":", maxsplit=2)
    order_id = int(raw_order_id)
    order = orders.get(order_id)
    if order is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if not orders.set_status(order_id, status):
        await callback.answer("Чек уже проверен", show_alert=True)
        return

    approved = status == "approved"
    status_text = "✅ Чек подтверждён" if approved else "❌ Чек отклонён"
    await callback.answer(status_text)
    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.reply(
                f"Заявка №{order_id}: <b>{status_text}</b>",
                reply_markup=admin_order_keyboard(order_id) if approved else None,
            )
        except TelegramBadRequest:
            pass

    user_text = (
        f"✅ <b>Оплата заявки №{order_id} подтверждена.</b>\n\n"
        f"На {escape(order.recipient_username)} будет отправлено {order.stars} ⭐.\n"
        "Звёзды придут в течение <b>15 минут</b>."
        if approved
        else f"❌ <b>Заявка №{order_id} отклонена.</b>\n"
        "Присланный файл не подтверждает оплату. Проверьте чек и оформите "
        "заявку заново через /start."
    )
    try:
        await bot.send_message(order.buyer_id, user_text)
    except (TelegramBadRequest, TelegramForbiddenError):
        pass


@router.callback_query(F.data.startswith("admin:"))
async def change_order_status(
    callback: CallbackQuery,
    bot: Bot,
    config: Config,
    orders: OrderRepository,
) -> None:
    if not orders.is_staff(callback.from_user.id, config.owner_id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    if callback.data is None:
        return

    _, status, raw_order_id = callback.data.split(":", maxsplit=2)
    order_id = int(raw_order_id)
    order = orders.get(order_id)
    if order is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if not orders.set_status(order_id, status):
        await callback.answer("Заявка уже обработана", show_alert=True)
        return

    status_text = "✅ Выполнено" if status == "completed" else "❌ Отклонено"
    await callback.answer(status_text)
    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.reply(f"Заявка №{order_id}: <b>{status_text}</b>")
        except TelegramBadRequest:
            pass

    user_text = (
        f"✅ <b>Заявка №{order_id} выполнена.</b>\n"
        f"На {escape(order.recipient_username)} начислено {order.stars} ⭐."
        if status == "completed"
        else f"❌ <b>Заявка №{order_id} отклонена.</b>\n"
        "Обратитесь к продавцу для уточнения причины."
    )
    try:
        await bot.send_message(order.buyer_id, user_text)
    except (TelegramBadRequest, TelegramForbiddenError):
        pass


@router.message()
async def fallback(message: Message) -> None:
    await message.answer("Чтобы начать покупку, используйте /start. Для отмены — /cancel.")
