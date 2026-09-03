from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def stars_keyboard(
    *, presets: tuple[int, ...] = (50, 100, 500), is_owner: bool = False
) -> InlineKeyboardMarkup:
    preset_buttons = [
        InlineKeyboardButton(text=f"⭐ {value}", callback_data=f"stars:{value}")
        for value in presets
    ]
    rows = [preset_buttons[index : index + 3] for index in range(0, len(preset_buttons), 3)]
    rows.append(
        [InlineKeyboardButton(text="✍️ Другое количество", callback_data="stars:custom")]
    )
    if is_owner:
        rows.append(
            [InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="panel:main")]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def manager_panel_keyboard(manager_ids: tuple[int, ...]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="💰 Изменить цену", callback_data="panel:price"),
            InlineKeyboardButton(text="⭐ Изменить кнопки", callback_data="panel:presets"),
        ],
        [
            InlineKeyboardButton(
                text="💳 Изменить реквизиты", callback_data="panel:payment_details"
            ),
            InlineKeyboardButton(
                text="↔️ Изменить лимиты", callback_data="panel:limits"
            ),
        ],
        [InlineKeyboardButton(text="➕ Добавить менеджера", callback_data="panel:add")]
    ]
    rows.extend(
        [
            InlineKeyboardButton(
                text=f"🗑 Удалить {manager_id}",
                callback_data=f"panel:remove:{manager_id}",
            )
        ]
        for manager_id in manager_ids
    )
    rows.append([InlineKeyboardButton(text="↩️ В магазин", callback_data="restart")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def manager_input_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад", callback_data="panel:main")]
        ]
    )


def manager_remove_keyboard(manager_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, удалить",
                    callback_data=f"panel:confirm_remove:{manager_id}",
                )
            ],
            [InlineKeyboardButton(text="↩️ Отмена", callback_data="panel:main")],
        ]
    )


def payment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я оплатил — отправить чек", callback_data="paid")],
            [InlineKeyboardButton(text="↩️ Изменить заказ", callback_data="restart")],
        ]
    )


def admin_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Выполнено", callback_data=f"admin:completed:{order_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить", callback_data=f"admin:rejected:{order_id}"
                ),
            ]
        ]
    )


def receipt_review_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить чек",
                    callback_data=f"review:approved:{order_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить чек",
                    callback_data=f"review:rejected:{order_id}",
                ),
            ]
        ]
    )
