from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from datetime import datetime, timedelta
from db import get_busy_slots, get_work_days, is_day_blocked


def get_main_reply_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✨ Записаться на макияж")]], resize_keyboard=True)


def get_admin_main_reply_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✨ Записаться на макияж")], [KeyboardButton(text="📋 Меню")]],
        resize_keyboard=True
    )


def get_dates_kb():
    kb = []
    today = datetime.now().date()
    row = []
    work_days = get_work_days()

    for i in range(42):
        d = today + timedelta(days=i)
        date_str = d.strftime('%Y-%m-%d')

        if d.weekday() in work_days and not is_day_blocked(date_str):
            if i == 0:
                start_h, end_h = work_days[d.weekday()]
                if datetime.now().hour >= end_h: continue

            day_name = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][d.weekday()]
            date_text = d.strftime("%d.%m")
            row.append(InlineKeyboardButton(text=f"{day_name} {date_text}", callback_data=f"date_{date_str}"))

            if len(row) == 3:
                kb.append(row)
                row = []
    if row: kb.append(row)
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_slots_kb(date_str: str):
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    work_days = get_work_days()
    start_h, end_h = work_days[d.weekday()]
    busy_slots = get_busy_slots(date_str)

    kb = []
    row = []
    for h in range(start_h, end_h):
        time_str = f"{h:02d}:00"
        if time_str in busy_slots: continue
        row.append(InlineKeyboardButton(text=time_str, callback_data=f"time_{date_str}_{time_str}"))
        if len(row) == 3:
            kb.append(row)
            row = []

    if not kb and not row:
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Нет свободных мест", callback_data="no_slots")]])
    if row: kb.append(row)
    kb.append([InlineKeyboardButton(text="⬅️ Назад к датам", callback_data="back_to_dates")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_format_reply_kb():
    kb = [
        [KeyboardButton(text="🏢 У мастера")],
        [KeyboardButton(text="🏠 Свое место")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def get_persons_reply_kb():
    kb = [
        [KeyboardButton(text="1"), KeyboardButton(text="2"), KeyboardButton(text="3")],
        [KeyboardButton(text="4"), KeyboardButton(text="5")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def get_address_choice_kb():
    kb = [[KeyboardButton(text="📍 Отправить геолокацию", request_location=True)],
          [KeyboardButton(text="✏️ Ввести адрес вручную")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def get_skip_reply_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⏭ Пропустить")]], resize_keyboard=True)


def get_payment_reply_kb():
    kb = [[KeyboardButton(text="💳 По карте")], [KeyboardButton(text="💵 Наличными")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def get_contact_reply_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Отправить мой номер", request_contact=True)]],
                               resize_keyboard=True)


def get_confirm_reply_kb():
    kb = [[KeyboardButton(text="✅ Подтвердить")], [KeyboardButton(text="🔄 Заново")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def get_review_choice_kb():
    kb = [[KeyboardButton(text="✍️ Написать отзыв")], [KeyboardButton(text="⏭ Пропустить")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def get_cancel_choice_kb():
    kb = [[KeyboardButton(text="✍️ Написать причину")], [KeyboardButton(text="⏭ Пропустить")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def get_admin_order_kb(order_id: int, user_id: int):
    kb = [
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"adm_confirmed_{order_id}"),
         InlineKeyboardButton(text="❌ Отмена", callback_data=f"adm_cancelled_{order_id}")],
        [InlineKeyboardButton(text="✔️ Выполнено", callback_data=f"adm_done_{order_id}")],
        [InlineKeyboardButton(text="💬 Написать клиенту", url=f"tg://user?id={user_id}")],
        [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="adm_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_admin_panel_kb():
    kb = [
        [InlineKeyboardButton(text="🆕 Новые заявки", callback_data="adm_new")],
        [InlineKeyboardButton(text="📅 Заказы на сегодня", callback_data="adm_today")],
        [InlineKeyboardButton(text="🗓 Заказы на выходные", callback_data="adm_week")],
        [InlineKeyboardButton(text="📋 Все активные заказы", callback_data="adm_all")],
        [InlineKeyboardButton(text="⭐ Отзывы", callback_data="adm_reviews")],
        [InlineKeyboardButton(text="⏰ Настроить график", callback_data="adm_schedule")],
        [InlineKeyboardButton(text="🚫 Закрыть/Открыть день", callback_data="adm_block_menu")],
        [InlineKeyboardButton(text="⛔ Черный список", callback_data="adm_blacklist")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_admin_back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В меню", callback_data="adm_menu")]])


def get_admin_blacklist_kb():
    kb = [
        [InlineKeyboardButton(text="➕ Добавить ID в ЧС", callback_data="adm_bl_add")],
        [InlineKeyboardButton(text="📋 Показать список ЧС", callback_data="adm_bl_view")],
        [InlineKeyboardButton(text="➖ Удалить ID из ЧС", callback_data="adm_bl_remove")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="adm_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_admin_orders_list_kb(bookings):
    kb = []
    for b in bookings:
        b_id, uname, dt, fmt, persons, status = b
        time_str = dt.split(" ")[1]
        date_str = dt.split(" ")[0]

        btn_text = f"📄 №{b_id} | {date_str[5:]} {time_str} | @{uname or 'клиент'}"
        kb.append([InlineKeyboardButton(text=btn_text, callback_data=f"adm_view_{b_id}")])

        if status == "new":
            kb.append([
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"adm_confirmed_{b_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_cancelled_{b_id}")
            ])
        elif status == "confirmed":
            kb.append([
                InlineKeyboardButton(text="✔️ Выполнено", callback_data=f"adm_done_{b_id}")
            ])

    kb.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="adm_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_admin_schedule_kb():
    kb = [
        [InlineKeyboardButton(text="Пятница", callback_data="adm_sched_day_4")],
        [InlineKeyboardButton(text="Суббота", callback_data="adm_sched_day_5")],
        [InlineKeyboardButton(text="Воскресенье", callback_data="adm_sched_day_6")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="adm_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_admin_hours_kb(day: int, is_start: bool):
    kb, row = [], []
    hours = range(10, 21) if is_start else range(12, 25)

    for h in hours:
        prefix = "st" if is_start else "en"
        row.append(InlineKeyboardButton(text=f"{h}:00", callback_data=f"adm_sched_{prefix}_{day}_{h}"))
        if len(row) == 4:
            kb.append(row)
            row = []
    if row: kb.append(row)

    kb.append([InlineKeyboardButton(text="⬅️ Назад к дням", callback_data="adm_schedule")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_admin_block_days_kb(offset=0):
    kb = []
    today = datetime.now().date()
    work_days = get_work_days()
    count, skipped = 0, 0

    for i in range(60):
        d = today + timedelta(days=i)
        date_str = d.strftime('%Y-%m-%d')

        if d.weekday() in work_days:
            if skipped < offset:
                skipped += 1
                continue

            is_blocked = is_day_blocked(date_str)
            status = "🔴 Закрыт" if is_blocked else "🟢 Открыт"
            day_name = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][d.weekday()]

            kb.append([InlineKeyboardButton(text=f"{day_name} {d.strftime('%d.%m')} | {status}",
                                            callback_data=f"adm_toggle_{date_str}_{offset}")])
            count += 1
            if count >= 7: break

    nav_row = []
    if offset > 0: nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"adm_block_pg_{offset - 7}"))
    if count == 7: nav_row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"adm_block_pg_{offset + 7}"))
    if nav_row: kb.append(nav_row)

    kb.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="adm_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_review_rating_kb(order_id: int):
    kb = [
        [
            InlineKeyboardButton(text="1", callback_data=f"rate_1_{order_id}"),
            InlineKeyboardButton(text="2", callback_data=f"rate_2_{order_id}"),
            InlineKeyboardButton(text="3", callback_data=f"rate_3_{order_id}"),
            InlineKeyboardButton(text="4", callback_data=f"rate_4_{order_id}"),
            InlineKeyboardButton(text="5", callback_data=f"rate_5_{order_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def remove_kb():
    return ReplyKeyboardRemove()