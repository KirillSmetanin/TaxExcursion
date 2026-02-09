import sqlite3

conn = sqlite3.connect('instance/bookings.db')
cursor = conn.cursor()

# Создаем таблицу bookings
cursor.execute('''
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT,
    school_name TEXT NOT NULL,
    class_number TEXT NOT NULL,
    class_profile TEXT,
    excursion_date TEXT NOT NULL,
    contact_person TEXT NOT NULL,
    contact_phone TEXT NOT NULL,
    participants_count INTEGER NOT NULL,
    booking_date TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(excursion_date)
)
''')

# Добавим тестовые данные для проверки
cursor.execute("INSERT OR IGNORE INTO bookings (user_id, username, school_name, class_number, excursion_date, contact_person, contact_phone, participants_count) VALUES (1, 'Тестовый', 'Школа №1', '10А', '2024-02-10', 'Иванов', '+79001234567', 20)")

conn.commit()
conn.close()

print("✅ Таблица 'bookings' создана успешно!")
print("✅ Тестовая запись добавлена")
