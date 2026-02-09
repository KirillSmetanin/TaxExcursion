from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from datetime import datetime, timedelta, date
import os
import calendar

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'

# Русские названия месяцев
RUSSIAN_MONTHS = [
    'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
]

# Русские дни недели (сокращенные и полные)
RUSSIAN_WEEKDAYS_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
RUSSIAN_WEEKDAYS_FULL = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']

def get_db_connection():
    """Создает подключение к базе данных"""
    os.makedirs('instance', exist_ok=True)
    conn = sqlite3.connect('instance/bookings.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Создает таблицу если она не существует"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
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
    
    conn.commit()
    conn.close()

def get_bookings_count_by_date():
    """Получаем количество записей на каждую дату"""
    init_database()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT excursion_date, COUNT(*) as count 
        FROM bookings 
        GROUP BY excursion_date
    ''')
    booked_dates = {}
    for row in cursor.fetchall():
        booked_dates[row['excursion_date']] = row['count']
    
    conn.close()
    return booked_dates

def generate_calendar_data(year=None, month=None):
    """Генерирует данные для календаря на указанный месяц"""
    today = date.today()
    
    if year is None:
        year = today.year
    if month is None:
        month = today.month
    
    # Получаем количество дней в месяце
    _, num_days = calendar.monthrange(year, month)
    
    # Получаем день недели первого дня месяца (0=понедельник, 6=воскресенье)
    first_weekday = calendar.weekday(year, month, 1)
    
    # Получаем данные о бронированиях
    bookings = get_bookings_count_by_date()
    
    # Создаем календарь
    calendar_data = {
        'year': year,
        'month': month,
        'month_name': RUSSIAN_MONTHS[month - 1],
        'prev_month': month - 1 if month > 1 else 12,
        'prev_year': year if month > 1 else year - 1,
        'next_month': month + 1 if month < 12 else 1,
        'next_year': year if month < 12 else year + 1,
        'weekdays': RUSSIAN_WEEKDAYS_SHORT,
        'weeks': []
    }
    
    # Создаем дни месяца
    days = []
    
    # Пустые дни в начале месяца
    for _ in range(first_weekday):
        days.append(None)
    
    # Дни месяца
    for day in range(1, num_days + 1):
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        date_obj = date(year, month, day)
        
        # Определяем день недели (0=понедельник, 6=воскресенье)
        weekday = date_obj.weekday()
        is_weekend = weekday >= 5  # 5=суббота, 6=воскресенье
        
        # Определяем статус дня
        if date_obj < today:
            status = 'past'
            available_slots = 0
        elif is_weekend:
            status = 'weekend'
            available_slots = 0
        else:
            bookings_count = bookings.get(date_str, 0)
            available_slots = max(0, 2 - bookings_count)
            
            if available_slots == 0:
                status = 'booked'
            elif available_slots == 1:
                status = 'limited'
            else:
                status = 'available'
        
        days.append({
            'day': day,
            'date_str': date_str,
            'date_obj': date_obj,
            'status': status,
            'available_slots': available_slots,
            'is_today': date_obj == today,
            'is_weekend': is_weekend,
            'weekday_name': RUSSIAN_WEEKDAYS_FULL[weekday],
            'weekday_num': weekday
        })
    
    # Разбиваем дни на недели
    for i in range(0, len(days), 7):
        week = days[i:i+7]
        while len(week) < 7:
            week.append(None)
        calendar_data['weeks'].append(week)
    
    return calendar_data

@app.route('/')
def index():
    """Главная страница с календарем"""
    try:
        today = date.today()
        calendar_data = generate_calendar_data(today.year, today.month)
        
        bookings = get_bookings_count_by_date()
        total_bookings = sum(bookings.values())
        
        return render_template('index.html', 
                             calendar=calendar_data,
                             today=today,
                             total_bookings=total_bookings)
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Ошибка</title>
            <style>
                body {{ font-family: Arial; padding: 20px; }}
                .error {{ color: red; background: #ffe6e6; padding: 15px; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h1>Временно недоступно</h1>
            <div class="error">
                <h3>Ошибка: {str(e)}</h3>
            </div>
            <p><a href="/simple">Упрощенная версия</a></p>
        </body>
        </html>
        '''

@app.route('/simple')
def simple_index():
    """Упрощенная главная страница"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Экскурсии в УФНС</title>
        <style>
            body { font-family: Arial; padding: 20px; }
            .success { color: green; }
            .box { background: #f0f8ff; padding: 20px; border-radius: 10px; margin: 20px 0; }
        </style>
    </head>
    <body>
        <h1>Запись на экскурсию в УФНС</h1>
        <div class="box">
            <p class="success">✅ Сайт работает!</p>
            <p>Версия: Python 3.8 + Flask</p>
            <p>База данных: SQLite3</p>
        </div>
        <h3>Ссылки:</h3>
        <ul>
            <li><a href="/">Основная страница (календарь)</a></li>
            <li><a href="/test">Добавить тестовые данные</a></li>
            <li><a href="/admin">Админ-панель</a></li>
        </ul>
    </body>
    </html>
    '''

@app.route('/month/<int:year>/<int:month>')
def month_view(year, month):
    """Просмотр конкретного месяца"""
    try:
        calendar_data = generate_calendar_data(year, month)
        today = date.today()
        bookings = get_bookings_count_by_date()
        total_bookings = sum(bookings.values())
        
        return render_template('index.html', 
                             calendar=calendar_data,
                             today=today,
                             total_bookings=total_bookings)
    except Exception as e:
        return redirect('/')

@app.route('/book/<date_str>')
def book_date(date_str):
    """Страница записи на конкретную дату"""
    try:
        date_parts = date_str.split('-')
        date_obj = date(int(date_parts[0]), int(date_parts[1]), int(date_parts[2]))
        today = date.today()
        
        # Проверяем что дата не прошедшая
        if date_obj < today:
            return '''
            <!DOCTYPE html>
            <html>
            <body style="padding: 40px; text-align: center; font-family: Arial;">
                <h1 style="color: #e74c3c;">❌ Ошибка</h1>
                <p style="font-size: 1.2em; margin: 20px 0;">Нельзя записаться на прошедшую дату</p>
                <a href="/" style="display: inline-block; padding: 10px 20px; background: #3498db; color: white; text-decoration: none; border-radius: 5px;">Вернуться к календарю</a>
            </body>
            </html>
            ''', 400
        
        # Проверяем что это будний день
        if date_obj.weekday() >= 5:  # 5=суббота, 6=воскресенье
            return '''
            <!DOCTYPE html>
            <html>
            <body style="padding: 40px; text-align: center; font-family: Arial;">
                <h1 style="color: #e74c3c;">❌ Ошибка</h1>
                <p style="font-size: 1.2em; margin: 20px 0;">Запись возможна только в будние дни (Пн-Пт)</p>
                <a href="/" style="display: inline-block; padding: 10px 20px; background: #3498db; color: white; text-decoration: none; border-radius: 5px;">Вернуться к календарю</a>
            </body>
            </html>
            ''', 400
        
        # Получаем количество записей
        bookings = get_bookings_count_by_date()
        bookings_count = bookings.get(date_str, 0)
        
        if bookings_count >= 2:
            return '''
            <!DOCTYPE html>
            <html>
            <body style="padding: 40px; text-align: center; font-family: Arial;">
                <h1 style="color: #e74c3c;">❌ Мест нет</h1>
                <p style="font-size: 1.2em; margin: 20px 0;">На эту дату уже нет свободных мест</p>
                <a href="/" style="display: inline-block; padding: 10px 20px; background: #3498db; color: white; text-decoration: none; border-radius: 5px;">Вернуться к календарю</a>
            </body>
            </html>
            ''', 400
        
        available_slots = 2 - bookings_count
        
        return render_template('booking.html',
                             date_str=date_str,
                             date_formatted=date_obj.strftime('%d.%m.%Y'),
                             weekday=RUSSIAN_WEEKDAYS_FULL[date_obj.weekday()],
                             available_slots=available_slots)
        
    except (ValueError, IndexError):
        return '''
        <!DOCTYPE html>
        <html>
        <body style="padding: 40px; text-align: center; font-family: Arial;">
            <h1 style="color: #e74c3c;">❌ Ошибка</h1>
            <p style="font-size: 1.2em; margin: 20px 0;">Неверный формат даты</p>
            <a href="/" style="display: inline-block; padding: 10px 20px; background: #3498db; color: white; text-decoration: none; border-radius: 5px;">Вернуться к календарю</a>
        </body>
        </html>
        ''', 400

@app.route('/submit_booking', methods=['POST'])
def submit_booking():
    """Обработка формы записи"""
    try:
        # Получаем данные из формы
        excursion_date = request.form.get('excursion_date')
        username = request.form.get('username')
        school_name = request.form.get('school_name')
        class_number = request.form.get('class_number')
        class_profile = request.form.get('class_profile')
        contact_person = request.form.get('contact_person')
        contact_phone = request.form.get('contact_phone')
        participants_count = request.form.get('participants_count')
        
        # Проверяем обязательные поля
        if not all([excursion_date, username, school_name, class_number, contact_person, contact_phone, participants_count]):
            return '''
            <!DOCTYPE html>
            <html>
            <body style="padding: 20px; font-family: Arial;">
                <h1 style="color: #e74c3c;">❌ Ошибка</h1>
                <p>Все обязательные поля должны быть заполнены</p>
                <p><a href="/">Вернуться к календарю</a></p>
            </body>
            </html>
            '''
        
        # Проверяем доступность даты
        bookings = get_bookings_count_by_date()
        bookings_count = bookings.get(excursion_date, 0)
        
        if bookings_count >= 2:
            return '''
            <!DOCTYPE html>
            <html>
            <body style="padding: 20px; font-family: Arial;">
                <h1 style="color: #e74c3c;">❌ Ошибка</h1>
                <p>На эту дату уже нет свободных мест</p>
                <p><a href="/">Вернуться к календарю</a></p>
            </body>
            </html>
            '''
        
        # Добавляем запись в базу данных
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO bookings 
            (user_id, username, school_name, class_number, class_profile, 
             excursion_date, contact_person, contact_phone, participants_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (1, username, school_name, class_number, class_profile, 
              excursion_date, contact_person, contact_phone, int(participants_count)))
        
        conn.commit()
        conn.close()
        
        # Форматируем дату для отображения
        date_parts = excursion_date.split('-')
        date_obj = date(int(date_parts[0]), int(date_parts[1]), int(date_parts[2]))
        
        return render_template('success.html',
                             date_formatted=date_obj.strftime('%d.%m.%Y'),
                             school_name=school_name,
                             contact_person=contact_person)
        
    except Exception as e:
        return f'''
        <!DOCTYPE html>
        <html>
        <body style="padding: 20px; font-family: Arial;">
            <h1 style="color: #e74c3c;">❌ Ошибка при обработке заявки</h1>
            <p>{str(e)}</p>
            <p><a href="/">Вернуться к календарю</a></p>
        </body>
        </html>
        '''

@app.route('/admin')
def admin():
    """Админ-панель"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM bookings ORDER BY excursion_date DESC')
    bookings = cursor.fetchall()
    conn.close()
    
    return render_template('admin.html', bookings=bookings)

@app.route('/test')
def test():
    """Тестовая страница"""
    try:
        # Добавим тестовые данные
        init_database()
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Очищаем старые тестовые данные
        cursor.execute("DELETE FROM bookings WHERE username = 'Тестовый'")
        
        # Добавляем несколько тестовых записей
        today = date.today()
        test_dates = [
            today.strftime('%Y-%m-%d'),
            (today + timedelta(days=1)).strftime('%Y-%m-%d'),
            (today + timedelta(days=5)).strftime('%Y-%m-%d'),
            (today + timedelta(days=10)).strftime('%Y-%m-%d'),
            (today + timedelta(days=15)).strftime('%Y-%m-%d'),
        ]
        
        for date_str in test_dates:
            cursor.execute('''
                INSERT OR IGNORE INTO bookings 
                (user_id, username, school_name, class_number, excursion_date, contact_person, contact_phone, participants_count)
                VALUES (1, 'Тестовый', 'Школа №1', '10А', ?, 'Иванов И.И.', '+79001234567', 20)
            ''', (date_str,))
        
        conn.commit()
        conn.close()
        
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial; padding: 40px; text-align: center; }
                .success { color: #2ecc71; font-size: 1.5em; margin: 20px 0; }
                .btn { display: inline-block; padding: 10px 20px; background: #3498db; color: white; text-decoration: none; border-radius: 5px; margin: 10px; }
            </style>
        </head>
        <body>
            <h1>✅ Тестовые данные добавлены!</h1>
            <div class="success">Добавлены записи на ближайшие даты</div>
            <div>
                <a href="/" class="btn">Вернуться к календарю</a>
                <a href="/admin" class="btn">Посмотреть все записи</a>
            </div>
        </body>
        </html>
        '''
    except Exception as e:
        return f'''
        <!DOCTYPE html>
        <html>
        <body style="padding: 20px; font-family: Arial;">
            <h1>❌ Ошибка</h1>
            <p>{str(e)}</p>
            <p><a href="/">Вернуться</a></p>
        </body>
        </html>
        '''

if __name__ == '__main__':
    init_database()
    app.run(debug=True)