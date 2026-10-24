import asyncio
import logging
import os
import re
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

from db import (
    init_db, save_booking, update_status, get_booking,
    get_work_days, update_schedule, block_day, unblock_day, is_day_blocked,
    get_bookings_for_date, get_active_bookings,
    save_cancel_reason, save_review, get_all_reviews, get_order_details,
    has_active_booking, add_to_blacklist, remove_from_blacklist,
    is_blacklisted, get_blacklist
)
from keyboards import (
    get_dates_kb, get_slots_kb, get_admin_order_kb,
    get_format_reply_kb, get_address_choice_kb,
    get_skip_reply_kb, get_payment_reply_kb,
    get_contact_reply_kb, get_confirm_reply_kb, remove_kb,
    get_admin_panel_kb, get_admin_back_kb, get_admin_schedule_kb,
    get_admin_hours_kb, get_admin_block_days_kb, get_review_rating_kb,
    get_admin_orders_list_kb, get_review_choice_kb, get_cancel_choice_kb,
    get_main_reply_kb, get_admin_main_reply_kb, get_persons_reply_kb,
    get_admin_blacklist_kb
)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

logging.basicConfig(level=logging.INFO)
dp = Dispatcher(storage=MemoryStorage())
geolocator = Nominatim(user_agent="makeup_booking_bot_v2")


# --- АНТИСПАМ MIDDLEWARE ---
class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit: float = 1.2):
        self.rate_limit = rate_limit
        self.users = {}

    async def __call__(self, handler, event, data):
        user_id = event.from_user.id
        current_time = time.time()

        if user_id in self.users:
            last_time = self.users[user_id]
            if current_time - last_time < self.rate_limit:
                if isinstance(event, CallbackQuery):
                    await event.answer("⏳ Пожалуйста, не спамьте кнопками.", show_alert=False)
                return  # Пропускаем обработку

        self.users[user_id] = current_time
        return await handler(event, data)


# Подключаем антиспам
dp.callback_query.middleware(ThrottlingMiddleware())
dp.message.middleware(ThrottlingMiddleware())


class Booking(StatesGroup):
    date = State()
    time = State()
    format = State()
    address_choice = State()
    address_text = State()
    persons = State()
    reference = State()
    notes = State()
    payment = State()
    contact = State()
    confirm = State()


class Review(StatesGroup):
    waiting_choice = State()
    waiting_text = State()


class AdminCancel(StatesGroup):
    waiting_choice = State()
    waiting_reason = State()


class AdminBlacklist(StatesGroup):
    waiting_add = State()
    waiting_remove = State()


async def send_clean_msg(message: Message, state: FSMContext, text: str, reply_markup=None):
    data = await state.get_data()
    old_bot_msg_id = data.get("last_bot_msg")
    if isinstance(message, Message):
        try:
            await message.delete()
        except:
            pass
    if old_bot_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=old_bot_msg_id)
        except:
            pass
    msg = await message.bot.send_message(chat_id=message.chat.id, text=text, reply_markup=reply_markup)
    await state.update_data(last_bot_msg=msg.message_id)


def check_address(address_str: str):
    if len(address_str) < 5:
        return False, "Адрес слишком короткий."
    try:
        location = geolocator.geocode(address_str, addressdetails=True, timeout=10, language="ru", country_codes="BY")
        if not location:
            return False, "Адрес не найден в Беларуси. Пожалуйста, укажите город, улицу и дом (например: Минск, ул. Ленина 10)."
        address_details = location.raw.get('address', {})
        country_code = address_details.get('country_code', '').lower()
        if country_code and country_code != 'by':
            return False, "Пожалуйста, указывайте адреса только в Беларуси."
        has_street = any(
            k in address_details for k in ['road', 'pedestrian', 'footway', 'path', 'residential', 'street'])
        has_house = 'house_number' in address_details
        if not has_street and not has_house:
            return False, "Укажите более точный адрес (улицу и дом)."
        return True, ""
    except Exception:
        return True, ""

    # ==================== ГЛАВНЫЙ СТАРТ ====================


@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    try:
        await message.delete()
    except:
        pass

    if is_blacklisted(message.from_user.id):
        return await message.answer("❌ Вы заблокированы и не можете использовать этого бота.")

    text = "Здравствуйте! Это бот визажиста.\nДля записи нажмите кнопку ниже."

    if message.from_user.id == ADMIN_ID:
        await message.answer(text + "\n\n(Для вас доступно меню управления)", reply_markup=get_admin_main_reply_kb())
    else:
        await message.answer(text, reply_markup=get_main_reply_kb())


# ==================== АДМИН ПАНЕЛЬ ====================

@dp.message(F.text == "📋 Меню", F.from_user.id == ADMIN_ID)
async def admin_panel_handler(message: Message, state: FSMContext):
    await state.clear()
    try:
        await message.delete()
    except:
        pass
    await message.answer("⚙️ <b>Главное меню</b>\nВыберите действие:",
                         reply_markup=get_admin_panel_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "adm_menu")
async def admin_back_to_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("⚙️ <b>Главное меню</b>\nВыберите действие:",
                                 reply_markup=get_admin_panel_kb(), parse_mode="HTML")


# --- ЧЕРНЫЙ СПИСОК ---
@dp.callback_query(F.data == "adm_blacklist")
async def admin_blacklist_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("⛔ <b>Управление Черным списком</b>\nВыберите действие:",
                                 reply_markup=get_admin_blacklist_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "adm_bl_view")
async def admin_bl_view(call: CallbackQuery):
    users = get_blacklist()
    if not users:
        return await call.message.edit_text("В черном списке пока никого нет.", reply_markup=get_admin_blacklist_kb())
    text = "⛔ <b>Заблокированные ID:</b>\n\n" + "\n".join([f"<code>{u}</code>" for u in users])
    await call.message.edit_text(text, reply_markup=get_admin_blacklist_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "adm_bl_add")
async def admin_bl_add_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminBlacklist.waiting_add)
    await call.message.edit_text("Введите ID пользователя, которого нужно заблокировать:", reply_markup=remove_kb())


@dp.message(AdminBlacklist.waiting_add)
async def admin_bl_add_process(message: Message, state: FSMContext):
    try:
        user_id = int(message.text)
        add_to_blacklist(user_id)
        await state.clear()
        await message.answer(f"✅ Пользователь <code>{user_id}</code> добавлен в ЧС.",
                             reply_markup=get_admin_blacklist_kb(), parse_mode="HTML")
    except ValueError:
        await message.answer("❌ Ошибка. ID должен состоять только из цифр. Попробуйте еще раз.")


@dp.callback_query(F.data == "adm_bl_remove")
async def admin_bl_remove_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminBlacklist.waiting_remove)
    await call.message.edit_text("Введите ID пользователя, которого нужно разблокировать:", reply_markup=remove_kb())


@dp.message(AdminBlacklist.waiting_remove)
async def admin_bl_remove_process(message: Message, state: FSMContext):
    try:
        user_id = int(message.text)
        remove_from_blacklist(user_id)
        await state.clear()
        await message.answer(f"✅ Пользователь <code>{user_id}</code> удален из ЧС.",
                             reply_markup=get_admin_blacklist_kb(), parse_mode="HTML")
    except ValueError:
        await message.answer("❌ Ошибка. ID должен состоять только из цифр. Попробуйте еще раз.")


# --- СПИСКИ ЗАКАЗОВ ---
@dp.callback_query(F.data == "adm_new")
async def admin_new(call: CallbackQuery):
    all_active = get_active_bookings()
    new_bookings = [b for b in all_active if b[5] == 'new']

    if not new_bookings:
        await call.message.edit_text("🆕 <b>Новые заявки:</b>\n\nНовых заявок нет.", reply_markup=get_admin_back_kb(),
                                     parse_mode="HTML")
    else:
        await call.message.edit_text(
            "🆕 <b>Новые заявки (ожидают решения):</b>\n\nНажмите ✅ или ❌ для быстрого действия:",
            reply_markup=get_admin_orders_list_kb(new_bookings), parse_mode="HTML")


@dp.callback_query(F.data == "adm_today")
async def admin_today(call: CallbackQuery):
    today_str = datetime.now().strftime("%Y-%m-%d")
    bookings = get_bookings_for_date(today_str)

    if not bookings:
        await call.message.edit_text(f"📅 <b>Заказы на сегодня ({today_str}):</b>\n\nЗаказов нет.",
                                     reply_markup=get_admin_back_kb(), parse_mode="HTML")
    else:
        await call.message.edit_text(f"📅 <b>Заказы на сегодня ({today_str}):</b>\n\nНажмите для управления:",
                                     reply_markup=get_admin_orders_list_kb(bookings), parse_mode="HTML")


@dp.callback_query(F.data == "adm_all")
async def admin_all(call: CallbackQuery):
    bookings = get_active_bookings()

    if not bookings:
        await call.message.edit_text("📋 <b>Все активные заказы:</b>\n\nАктивных заказов нет.",
                                     reply_markup=get_admin_back_kb(), parse_mode="HTML")
    else:
        await call.message.edit_text("📋 <b>Все активные заказы:</b>\n\nНажмите для управления:",
                                     reply_markup=get_admin_orders_list_kb(bookings), parse_mode="HTML")


@dp.callback_query(F.data.startswith("adm_week"))
async def admin_week(call: CallbackQuery):
    today = datetime.now().date()
    days_ahead = 4 - today.weekday()
    if days_ahead < 0: days_ahead += 7
    friday = today + timedelta(days=days_ahead)

    bookings_all = []
    text = "🗓 <b>Расписание на выходные:</b>\n\n"
    for i in range(3):
        d = friday + timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")
        day_name = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][d.weekday()]
        bookings = get_bookings_for_date(date_str)

        text += f"<b>{day_name} {d.strftime('%d.%m')}</b>\n"
        if not bookings:
            text += "  Нет записей\n"
        else:
            bookings_all.extend(bookings)
            for b in bookings:
                b_id, uname, dt, fmt, persons, status = b
                text += f"  {dt.split(' ')[1]} — №{b_id} @{uname or 'нет'} ({status})\n"
        text += "\n"

    kb = get_admin_orders_list_kb(bookings_all) if bookings_all else get_admin_back_kb()
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data.startswith("adm_view_"))
async def admin_view_order(call: CallbackQuery, state: FSMContext):
    await state.clear()
    order_id = int(call.data.split("_")[2])
    details = get_order_details(order_id)
    if not details:
        return await call.answer("Заказ не найден", show_alert=True)

    user_id, username, dt_str, fmt, addr, persons, notes, contact, payment, status = details
    status_rus = {"new": "🟡 Новый", "confirmed": "🟢 Подтвержден", "done": "✅ Выполнен", "cancelled": "🔴 Отменен"}.get(
        status, status)

    text = (
        f"📄 <b>Заявка №{order_id}</b>\n"
        f"Статус: {status_rus}\n\n"
        f"<blockquote>"
        f"👤 Клиент: @{username or 'нет'} (ID: {user_id})\n"
        f"📅 Время: {dt_str}\n"
        f"📍 Формат: {fmt} ({addr})\n"
        f"👥 Человек: {persons}\n"
        f"💬 Особенности: {notes}\n"
        f"💰 Оплата: {payment}\n"
        f"📞 Контакт: {contact}"
        f"</blockquote>"
    )

    kb = get_admin_order_kb(order_id, user_id)
    if status in ["done", "cancelled"]:
        kb = get_admin_back_kb()
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


# --- ОТЗЫВЫ ---
@dp.callback_query(F.data == "adm_reviews")
async def admin_reviews(call: CallbackQuery, state: FSMContext):
    await state.clear()
    reviews = get_all_reviews()
    if not reviews:
        return await call.message.edit_text("⭐ <b>Отзывы</b>\n\nПока нет ни одного отзыва.",
                                            reply_markup=get_admin_back_kb(), parse_mode="HTML")

    await call.message.edit_text("⭐ <b>Последние отзывы:</b>\n(Листайте чат, чтобы увидеть все)",
                                 reply_markup=get_admin_back_kb(), parse_mode="HTML")

    for r in reviews[:20]:
        order_id, user_id, username, rating, text, photo_id = r
        review_text = f"⭐ Оценка: <b>{rating}/5</b>\nКлиент: @{username or user_id}\nЗаказ: №{order_id}\n\n💬 {text or 'Без текста'}"
        if photo_id:
            await call.message.answer_photo(photo_id, caption=review_text, parse_mode="HTML")
        else:
            await call.message.answer(review_text, parse_mode="HTML")


# --- УПРАВЛЕНИЕ ЗАКАЗОМ (АДМИН) ---
@dp.callback_query(F.data.startswith("adm_confirmed_"))
async def admin_confirm(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return await call.answer("Нет прав", show_alert=True)
    await state.clear()
    order_id = int(call.data.split("_")[2])
    update_status(order_id, "confirmed")

    booking = get_booking(order_id)
    if booking:
        client_id, dt_str = booking
        confirm_text = f"✅ Ваша заявка №{order_id} на {dt_str} подтверждена!\n\nДля связи с мастером:\n👤 @Astra_nil\n📞 +375447211659\n\nЖду вас!"
        try:
            await call.bot.send_message(client_id, confirm_text)
        except:
            pass

    await call.answer("Заказ подтвержден!")
    await admin_view_order(call, state)


@dp.callback_query(F.data.startswith("adm_done_"))
async def admin_done(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return await call.answer("Нет прав", show_alert=True)
    await state.clear()
    order_id = int(call.data.split("_")[2])
    update_status(order_id, "done")

    booking = get_booking(order_id)
    if booking:
        client_id, dt_str = booking
        try:
            await call.bot.send_message(client_id, f"✔️ Заявка №{order_id} выполнена. Спасибо!")
            await call.bot.send_message(client_id, "Пожалуйста, оцените мою работу от 1 до 5 ⭐:",
                                        reply_markup=get_review_rating_kb(order_id))
        except:
            pass
    await call.answer("Заказ выполнен! Клиенту отправлен запрос на отзыв.")
    await admin_view_order(call, state)


@dp.callback_query(F.data.startswith("adm_cancelled_"))
async def admin_cancel_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return await call.answer("Нет прав", show_alert=True)
    order_id = int(call.data.split("_")[2])
    await state.update_data(cancel_order_id=order_id)
    await state.set_state(AdminCancel.waiting_choice)

    await call.message.answer(
        f"Отмена заявки №{order_id}.\n\n"
        "Хотите указать причину для клиента? (Это необязательно)",
        reply_markup=get_cancel_choice_kb()
    )


@dp.message(AdminCancel.waiting_choice, F.text == "✍️ Написать причину")
async def process_cancel_choice_write(message: Message, state: FSMContext):
    await state.set_state(AdminCancel.waiting_reason)
    await message.answer("Напишите причину отмены заявки:", reply_markup=remove_kb())


@dp.message(AdminCancel.waiting_choice, F.text == "⏭ Пропустить")
async def process_cancel_choice_skip(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get('cancel_order_id')
    update_status(order_id, "cancelled")
    save_cancel_reason(order_id, "Без причины")
    await state.clear()

    booking = get_booking(order_id)
    if booking:
        client_id, dt_str = booking
        try:
            await message.bot.send_message(client_id,
                                           f"❌ Ваша заявка №{order_id} на {dt_str} отклонена.\nЕсли хотите перенести, нажмите кнопку внизу.",
                                           reply_markup=get_main_reply_kb())
        except:
            pass
    await message.answer(f"Заявка №{order_id} отменена без причины.", reply_markup=get_admin_main_reply_kb())
    await admin_panel_handler(message, state)


@dp.message(AdminCancel.waiting_reason)
async def admin_cancel_with_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get('cancel_order_id')
    reason = message.text
    update_status(order_id, "cancelled")
    save_cancel_reason(order_id, reason)
    await state.clear()

    booking = get_booking(order_id)
    if booking:
        client_id, dt_str = booking
        try:
            await message.bot.send_message(client_id,
                                           f"❌ Ваша заявка №{order_id} на {dt_str} отклонена.\nПричина: {reason}\nЕсли хотите перенести, нажмите кнопку внизу.",
                                           reply_markup=get_main_reply_kb())
        except:
            pass
    await message.answer(f"Заявка №{order_id} отменена. Причина: {reason}", reply_markup=get_admin_main_reply_kb())
    await admin_panel_handler(message, state)


# --- НАСТРОЙКА ГРАФИКА ---
@dp.callback_query(F.data == "adm_schedule")
async def admin_schedule(call: CallbackQuery):
    work_days = get_work_days()
    days_map = {4: "Пятница", 5: "Суббота", 6: "Воскресенье"}
    text = "⏰ <b>Настройка графика работы</b>\n\n"
    for day, hours in work_days.items():
        text += f"{days_map[day]}: с {hours[0]}:00 до {hours[1]}:00\n"
    text += "\nВыберите день, который хотите изменить:"
    await call.message.edit_text(text, reply_markup=get_admin_schedule_kb(), parse_mode="HTML")


@dp.callback_query(F.data.startswith("adm_sched_day_"))
async def admin_sched_day(call: CallbackQuery):
    day = int(call.data.split("_")[3])
    days_map = {4: "Пятницу", 5: "Субботу", 6: "Воскресенье"}
    await call.message.edit_text(f"Вы меняете <b>{days_map[day]}</b>.\nВыберите час <b>начала</b> смены:",
                                 reply_markup=get_admin_hours_kb(day, is_start=True), parse_mode="HTML")


@dp.callback_query(F.data.startswith("adm_sched_st_"))
async def admin_sched_start(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    day, hour = int(parts[3]), int(parts[4])
    await state.update_data(sched_day=day, sched_start=hour)
    await call.message.edit_text(f"Начало: {hour}:00.\nТеперь выберите час <b>окончания</b> смены:",
                                 reply_markup=get_admin_hours_kb(day, is_start=False))


@dp.callback_query(F.data.startswith("adm_sched_en_"))
async def admin_sched_end(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    day, hour = int(parts[3]), int(parts[4])
    data = await state.get_data()
    start_h = data.get("sched_start")
    if hour <= start_h: return await call.answer("Ошибка: конец смены должен быть позже начала!", show_alert=True)
    update_schedule(day, start_h, hour)
    await call.message.edit_text(f"✅ График обновлен! Смена: с {start_h}:00 до {hour}:00.",
                                 reply_markup=get_admin_schedule_kb())


@dp.callback_query(F.data.startswith("adm_block_pg_"))
async def admin_block_pg(call: CallbackQuery):
    offset = int(call.data.split("_")[3])
    await call.message.edit_text("Выберите день, чтобы закрыть или открыть его для записи:",
                                 reply_markup=get_admin_block_days_kb(offset))


@dp.callback_query(F.data == "adm_block_menu")
async def admin_block_menu(call: CallbackQuery):
    await call.message.edit_text("Выберите день, чтобы закрыть или открыть его для записи:",
                                 reply_markup=get_admin_block_days_kb(0))


@dp.callback_query(F.data.startswith("adm_toggle_"))
async def admin_toggle_block(call: CallbackQuery):
    parts = call.data.split("_")
    date_str = parts[2]
    offset = int(parts[3]) if len(parts) > 3 else 0

    if is_day_blocked(date_str):
        unblock_day(date_str)
        await call.answer(f"✅ День {date_str} ОТКРЫТ для записи.")
    else:
        block_day(date_str)
        await call.answer(f"🚫 День {date_str} ЗАКРЫТ для записи.")
    await call.message.edit_text("Выберите день, чтобы закрыть или открыть его для записи:",
                                 reply_markup=get_admin_block_days_kb(offset))


# ==================== КЛИЕНТСКАЯ ЧАСТЬ ====================

@dp.message(F.text == "✨ Записаться на макияж")
async def book_handler(message: Message, state: FSMContext):
    await state.clear()

    if is_blacklisted(message.from_user.id):
        return await message.answer("❌ Вы заблокированы и не можете создавать заявки. Напишите мастеру: @Astra_nil")

    if has_active_booking(message.from_user.id):
        return await message.answer(
            "❌ У вас уже есть активная заявка. \n\n"
            "Вы не можете создать новую, пока не завершите или не отмените текущую. "
            "Если нужно что-то изменить, напишите мастеру: @Astra_nil"
        )

    await state.set_state(Booking.date)
    await send_clean_msg(message, state, "Выберите удобный день:", reply_markup=get_dates_kb())


@dp.callback_query(F.data.startswith("date_"))
async def process_date(call: CallbackQuery, state: FSMContext):
    date_str = call.data.split("_")[1]
    await state.update_data(date=date_str)
    await state.set_state(Booking.time)
    await call.message.edit_text(f"Дата: {date_str}. Выберите время:", reply_markup=get_slots_kb(date_str))
    await state.update_data(last_bot_msg=call.message.message_id)


@dp.callback_query(F.data == "back_to_dates")
async def back_to_dates(call: CallbackQuery, state: FSMContext):
    await state.set_state(Booking.date)
    await call.message.edit_text("Выберите удобный день:", reply_markup=get_dates_kb())
    await state.update_data(last_bot_msg=call.message.message_id)


@dp.callback_query(F.data.startswith("time_"))
async def process_time(call: CallbackQuery, state: FSMContext):
    _, date_str, time_str = call.data.split("_")
    await state.update_data(datetime_str=f"{date_str} {time_str}")
    await state.set_state(Booking.format)
    await state.update_data(last_bot_msg=call.message.message_id)
    await send_clean_msg(call.message, state, "Выберите место:", reply_markup=get_format_reply_kb())


@dp.message(Booking.format, F.text.in_(["🏢 У мастера", "🏠 Свое место"]))
async def process_format(message: Message, state: FSMContext):
    fmt = message.text
    if fmt == "🏠 Свое место":
        await state.update_data(format="Свое место")
        await state.set_state(Booking.address_choice)
        await send_clean_msg(message, state, "Выберите способ указания адреса:", reply_markup=get_address_choice_kb())
    else:
        await state.update_data(format="У мастера", address="Гомель, ул. Чечерская, д. 48, кв. 18")
        await state.set_state(Booking.persons)
        await send_clean_msg(message, state, "Сколько человек нужно накрасить?", reply_markup=get_persons_reply_kb())


@dp.message(Booking.address_choice, F.location)
async def process_location(message: Message, state: FSMContext):
    lat, lon = message.location.latitude, message.location.longitude
    try:
        location = geolocator.reverse(f"{lat}, {lon}", timeout=10, language="ru")
        address_text = location.address if location else f"Геолокация: {lat}, {lon}"
    except:
        address_text = f"Геолокация: {lat}, {lon}"
    await state.update_data(format="Свое место", address=address_text)
    await state.set_state(Booking.persons)
    await send_clean_msg(message, state, f"📍 Адрес: {address_text}\n\nСколько человек нужно накрасить?",
                         reply_markup=get_persons_reply_kb())


@dp.message(Booking.address_choice, F.text == "✏️ Ввести адрес вручную")
async def process_address_manual(message: Message, state: FSMContext):
    await state.update_data(format="Свое место")
    await state.set_state(Booking.address_text)
    await send_clean_msg(message, state, "Напишите ваш адрес (Город, улица, дом):", reply_markup=remove_kb())


@dp.message(Booking.address_text)
async def process_address_text(message: Message, state: FSMContext):
    address_input = message.text.strip()
    wait_msg = await message.bot.send_message(message.chat.id, "🔍 Проверяю адрес в Беларуси...")
    is_valid, error_msg = check_address(address_input)
    try:
        await wait_msg.delete()
    except:
        pass
    if not is_valid: return await send_clean_msg(message, state, f"❌ {error_msg}\n\nНапишите точный адрес:")
    await state.update_data(address=address_input)
    await state.set_state(Booking.persons)
    await send_clean_msg(message, state, "✅ Адрес подтвержден!\nСколько человек нужно накрасить?",
                         reply_markup=get_persons_reply_kb())


# ОБНОВЛЕННЫЙ ВЫБОР КОЛИЧЕСТВА ЧЕЛОВЕК
@dp.message(Booking.persons, F.text.in_(["1", "2", "3", "4", "5"]))
async def process_persons(message: Message, state: FSMContext):
    await state.update_data(persons=int(message.text))
    await state.set_state(Booking.reference)
    await send_clean_msg(message, state, "Пришлите фото-референс или нажмите внизу:", reply_markup=get_skip_reply_kb())


@dp.message(Booking.reference, F.photo)
async def process_ref_photo(message: Message, state: FSMContext):
    await state.update_data(reference_file_id=message.photo[-1].file_id)
    await state.set_state(Booking.notes)
    await send_clean_msg(message, state, "Есть аллергии? Напишите или нажмите внизу:", reply_markup=get_skip_reply_kb())


@dp.message(Booking.reference, F.text == "⏭ Пропустить")
async def skip_ref(message: Message, state: FSMContext):
    await state.update_data(reference_file_id=None)
    await state.set_state(Booking.notes)
    await send_clean_msg(message, state, "Есть аллергии? Напишите или нажмите внизу:", reply_markup=get_skip_reply_kb())


@dp.message(Booking.notes, F.text == "⏭ Пропустить")
async def skip_notes(message: Message, state: FSMContext):
    await state.update_data(notes="Нет")
    await state.set_state(Booking.payment)
    await send_clean_msg(message, state, "Как вам удобнее оплатить?", reply_markup=get_payment_reply_kb())


@dp.message(Booking.notes)
async def process_notes(message: Message, state: FSMContext):
    await state.update_data(notes=message.text)
    await state.set_state(Booking.payment)
    await send_clean_msg(message, state, "Как вам удобнее оплатить?", reply_markup=get_payment_reply_kb())


@dp.message(Booking.payment, F.text.in_(["💳 По карте", "💵 Наличными"]))
async def process_payment(message: Message, state: FSMContext):
    await state.update_data(payment=message.text)
    await state.set_state(Booking.contact)
    await send_clean_msg(message, state, "Оставьте ваш номер телефона:", reply_markup=get_contact_reply_kb())


# СТРОГАЯ ПРОВЕРКА НОМЕРА (+375/80 + код оператора 25/29/33/44 + 7 цифр)
@dp.message(Booking.contact, F.contact)
async def process_contact_telegram(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    if not phone.startswith('+'): phone = '+' + phone

    pattern = r"^(?:\+375|80)(?:25|29|33|44)\d{7}$"
    if not re.match(pattern, phone):
        return await message.answer(
            "❌ Номер из Telegram не подходит (неверный код оператора). Введите номер вручную (+375291234567):")

    await state.update_data(contact=phone)
    await state.set_state(Booking.confirm)
    data = await state.get_data()
    summary = f"Проверьте заявку:\n\n📅 {data['datetime_str']}\n📍 {data['format']} ({data['address']})\n👥 Человек: {data['persons']}\n💬 Особенности: {data['notes']}\n💰 Оплата: {data['payment']}\n📞 Контакт: {data['contact']}"
    await send_clean_msg(message, state, summary, reply_markup=get_confirm_reply_kb())


@dp.message(Booking.contact)
async def process_contact_text(message: Message, state: FSMContext):
    contact_text = message.text.strip()
    pattern = r"^(?:\+375|80)(?:25|29|33|44)\d{7}$"
    if not re.match(pattern, contact_text):
        return await message.answer(
            "❌ Ошибка. Введите белорусский номер с правильным кодом оператора (25, 29, 33, 44). Пример: +375291234567")

    await state.update_data(contact=contact_text)
    await state.set_state(Booking.confirm)
    data = await state.get_data()
    summary = f"Проверьте заявку:\n\n📅 {data['datetime_str']}\n📍 {data['format']} ({data['address']})\n👥 Человек: {data['persons']}\n💬 Особенности: {data['notes']}\n💰 Оплата: {data['payment']}\n📞 Контакт: {data['contact']}"
    await send_clean_msg(message, state, summary, reply_markup=get_confirm_reply_kb())


@dp.message(Booking.confirm, F.text == "🔄 Заново")
async def restart_booking(message: Message, state: FSMContext):
    await state.clear()
    await book_handler(message, state)


@dp.message(Booking.confirm, F.text == "✅ Подтвердить")
async def confirm_booking(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    username = message.from_user.username

    try:
        order_id = save_booking(user_id, username, data['datetime_str'], data['format'], data['address'],
                                data['persons'], data.get('reference_file_id'), data['notes'], data['contact'],
                                data['payment'])
    except Exception as e:
        return await message.answer(f"Ошибка при создании заявки: {e}")

    await state.clear()
    text = f"✅ Заявка №{order_id} принята!\n\nОжидайте подтверждения от мастера."
    kb = get_admin_main_reply_kb() if user_id == ADMIN_ID else get_main_reply_kb()
    await send_clean_msg(message, state, text, reply_markup=kb)

    admin_text = f"🆕 Заявка №{order_id}\n\nКлиент: @{username or 'нет'} (id {user_id})\n📅 {data['datetime_str']}\n📍 {data['format']} ({data['address']})\n👥 Человек: {data['persons']}\n💬 Особенности: {data['notes']}\n💰 Оплата: {data['payment']}\n📞 Контакт: {data['contact']}"
    kb_admin = get_admin_order_kb(order_id, user_id)

    try:
        if data.get('reference_file_id'):
            await message.bot.send_photo(ADMIN_ID, data['reference_file_id'], caption=admin_text, reply_markup=kb_admin)
        else:
            await message.bot.send_message(ADMIN_ID, admin_text, reply_markup=kb_admin)
    except:
        pass


# --- ОТЗЫВЫ КЛИЕНТА ---
@dp.callback_query(F.data.startswith("rate_"))
async def process_review_rating(call: CallbackQuery, state: FSMContext):
    _, rating, order_id = call.data.split("_")
    await state.update_data(review_rating=int(rating), review_order_id=int(order_id))
    await state.set_state(Review.waiting_choice)

    await call.message.edit_text(f"Вы поставили {rating} ⭐.")
    await call.message.answer("Хотите добавить текстовый отзыв или фото? (Это необязательно)",
                              reply_markup=get_review_choice_kb())


@dp.message(Review.waiting_choice, F.text == "✍️ Написать отзыв")
async def process_review_write(message: Message, state: FSMContext):
    await state.set_state(Review.waiting_text)
    await send_clean_msg(message, state, "Напишите ваш отзыв или отправьте фото:", reply_markup=remove_kb())


@dp.message(Review.waiting_choice, F.text == "⏭ Пропустить")
async def process_review_skip(message: Message, state: FSMContext):
    data = await state.get_data()
    save_review(data['review_order_id'], message.from_user.id, message.from_user.username, data['review_rating'], None,
                None)
    await state.clear()
    kb = get_admin_main_reply_kb() if message.from_user.id == ADMIN_ID else get_main_reply_kb()
    await send_clean_msg(message, state, "Спасибо за вашу оценку! Будем рады видеть вас снова.", reply_markup=kb)


@dp.message(Review.waiting_text, F.photo)
async def process_review_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    caption = message.caption if message.caption else None
    save_review(data['review_order_id'], message.from_user.id, message.from_user.username, data['review_rating'],
                caption, message.photo[-1].file_id)
    await state.clear()
    kb = get_admin_main_reply_kb() if message.from_user.id == ADMIN_ID else get_main_reply_kb()
    await send_clean_msg(message, state, "Спасибо за ваш отзыв с фото! Будем рады видеть вас снова.", reply_markup=kb)


@dp.message(Review.waiting_text, F.text)
async def process_review_text(message: Message, state: FSMContext):
    data = await state.get_data()
    save_review(data['review_order_id'], message.from_user.id, message.from_user.username, data['review_rating'],
                message.text, None)
    await state.clear()
    kb = get_admin_main_reply_kb() if message.from_user.id == ADMIN_ID else get_main_reply_kb()
    await send_clean_msg(message, state, "Спасибо за ваш отзыв! Будем рады видеть вас снова.", reply_markup=kb)


async def main():
    init_db()
    bot = Bot(token=TOKEN)
    print("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())