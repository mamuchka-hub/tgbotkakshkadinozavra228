import sqlite3
import os

DB_NAME = "bookings.db"


def init_db():
    if os.path.exists(DB_NAME):
        try:
            os.remove(DB_NAME)
        except:
            pass

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            datetime TEXT NOT NULL,
            format TEXT NOT NULL,
            address TEXT,
            persons INTEGER DEFAULT 1,
            reference_file_id TEXT,
            notes TEXT,
            contact TEXT NOT NULL,
            payment TEXT, 
            status TEXT DEFAULT 'new',
            cancel_reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
            day_of_week INTEGER PRIMARY KEY,
            start_hour INTEGER,
            end_hour INTEGER
        )
    """)
    cur.execute("INSERT OR IGNORE INTO schedule (day_of_week, start_hour, end_hour) VALUES (4, 16, 24)")
    cur.execute("INSERT OR IGNORE INTO schedule (day_of_week, start_hour, end_hour) VALUES (5, 12, 24)")
    cur.execute("INSERT OR IGNORE INTO schedule (day_of_week, start_hour, end_hour) VALUES (6, 12, 24)")

    cur.execute("CREATE TABLE IF NOT EXISTS blocked_days (date TEXT PRIMARY KEY)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            user_id INTEGER,
            username TEXT,
            rating INTEGER,
            text TEXT,
            photo_file_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# --- АНТИСПАМ ---
def has_active_booking(user_id):
    """Проверяет, есть ли у пользователя активная заявка (new или confirmed)"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT id FROM bookings WHERE user_id = ? AND status IN ('new', 'confirmed')", (user_id,))
    res = cur.fetchone()
    conn.close()
    return bool(res)


def get_work_days():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT day_of_week, start_hour, end_hour FROM schedule")
    rows = cur.fetchall()
    conn.close()
    return {row[0]: (row[1], row[2]) for row in rows}


def is_day_blocked(date_str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT date FROM blocked_days WHERE date = ?", (date_str,))
    res = cur.fetchone()
    conn.close()
    return bool(res)


def block_day(date_str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO blocked_days (date) VALUES (?)", (date_str,))
    conn.commit()
    conn.close()


def unblock_day(date_str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM blocked_days WHERE date = ?", (date_str,))
    conn.commit()
    conn.close()


def update_schedule(day_of_week, start_h, end_h):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE schedule SET start_hour = ?, end_hour = ? WHERE day_of_week = ?", (start_h, end_h, day_of_week))
    conn.commit()
    conn.close()


def get_busy_slots(date_str: str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT datetime FROM bookings WHERE datetime LIKE ? AND status IN ('new', 'confirmed')",
                (f"{date_str}%",))
    rows = cur.fetchall()
    conn.close()
    return [row[0].split(" ")[1] for row in rows]


def save_booking(user_id, username, dt_str, fmt, addr, persons, ref_id, notes, contact, payment):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bookings (user_id, username, datetime, format, address, persons, reference_file_id, notes, contact, payment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, username, dt_str, fmt, addr, persons, ref_id, notes, contact, payment))
    conn.commit()
    order_id = cur.lastrowid
    conn.close()
    return order_id


def update_status(order_id, status):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE bookings SET status = ? WHERE id = ?", (status, order_id))
    conn.commit()
    conn.close()


def save_cancel_reason(order_id, reason):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE bookings SET cancel_reason = ? WHERE id = ?", (reason, order_id))
    conn.commit()
    conn.close()


def get_booking(order_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT user_id, datetime FROM bookings WHERE id = ?", (order_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_order_details(order_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, username, datetime, format, address, persons, notes, contact, payment, status FROM bookings WHERE id = ?",
        (order_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_bookings_for_date(date_str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, username, datetime, format, persons, status FROM bookings WHERE datetime LIKE ? AND status IN ('new', 'confirmed')",
        (f"{date_str}%",))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_active_bookings():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, username, datetime, format, persons, status FROM bookings WHERE status IN ('new', 'confirmed') ORDER BY datetime ASC")
    rows = cur.fetchall()
    conn.close()
    return rows


def save_review(order_id, user_id, username, rating, text, photo_file_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO reviews (order_id, user_id, username, rating, text, photo_file_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (order_id, user_id, username, rating, text, photo_file_id))
    conn.commit()
    conn.close()


def get_all_reviews():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT order_id, user_id, username, rating, text, photo_file_id FROM reviews ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return rows