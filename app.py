from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
import sqlite3
from datetime import datetime, timedelta, date
import os
import calendar

app = Flask(__name__)
# Безопасный ключ для сессий - берется из переменных окружения
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['DATABASE_URL'] = os.environ.get('DATABASE_URL', 'sqlite:///instance/bookings.db')

# Русские названия месяцев
RUSSIAN_MONTHS = [
    'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
]

# Русские дни недели
RUSSIAN_WEEKDAYS_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
RUSSIAN_WEEKDAYS_FULL = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']

def get_db_connection():
    """Создает подключение к базе данных SQLite"""
    # На Render используем абсолютный путь
    db_path = os.path.join(os.getcwd(), 'instance', 'bookings.db')
    os.makedirs('instance', exist_ok=True)
    
    conn = sqlite3.connect(db_path)
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
            booking_date TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Создаем индекс для поиска по дате
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_excursion_date ON bookings(excursion_date)')
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

def get_bookings_count_by_date():
    """Получаем количество записей на каждую дату"""
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
    
    _, num_days = calendar.monthrange(year, month)
    first_weekday = calendar.weekday(year, month, 1)
    
    bookings = get_bookings_count_by_date()
    
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
    
    days = []
    for _ in range(first_weekday):
        days.append(None)
    
    for day in range(1, num_days + 1):
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        date_obj = date(year, month, day)
        weekday = date_obj.weekday()
        is_weekend = weekday >= 5
        
        if date_obj < today:
            status = 'past'
            available_slots = 0
        elif is_weekend:
            status = 'weekend'
            available_slots = 0
        else:
            bookings_count = bookings.get(date_str, 0)
            # Максимум 2 записи в день
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
    
    for i in range(0, len(days), 7):
        week = days[i:i+7]
        while len(week) < 7:
            week.append(None)
        calendar_data['weeks'].append(week)
    
    return calendar_data

@app.before_first_request
def before_first_request():
    """Инициализация БД при первом запросе"""
    init_database()

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
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Запись на экскурсию</title>
            <style>
                body {{ font-family: Arial; padding: 40px; text-align: center; }}
                .error {{ color: #e74c3c; background: #ffe6e6; padding: 20px; border-radius: 10px; margin: 20px auto; max-width: 600px; }}
                .btn {{ display: inline-block; padding: 12px 24px; background: #3498db; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <h1>Запись на экскурсию в УФНС</h1>
            <div class="error">
                <h3>⚠️ Временно недоступно</h3>
                <p>Технические работы. Попробуйте обновить страницу через несколько минут.</p>
            </div>
            <a href="/" class="btn">Обновить страницу</a>
        </body>
        </html>
        ''', 500

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
    except:
        return redirect('/')

@app.route('/book/<date_str>')
def book_date(date_str):
    """Страница записи на конкретную дату"""
    try:
        date_parts = date_str.split('-')
        date_obj = date(int(date_parts[0]), int(date_parts[1]), int(date_parts[2]))
        today = date.today()
        
        if date_obj < today:
            return '''
            <!DOCTYPE html>
            <html>
            <body style="padding: 40px; text-align: center; font-family: Arial;">
                <h1 style="color: #e74c3c;">❌ Нельзя записаться на прошедшую дату</h1>
                <a href="/" style="display: inline-block; padding: 12px 24px; background: #3498db; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px;">Вернуться</a>
            </body>
            </html>
            ''', 400
        
        if date_obj.weekday() >= 5:
            return '''
            <!DOCTYPE html>
            <html>
            <body style="padding: 40px; text-align: center; font-family: Arial;">
                <h1 style="color: #e74c3c;">❌ Запись только в будние дни</h1>
                <a href="/" style="display: inline-block; padding: 12px 24px; background: #3498db; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px;">Вернуться</a>
            </body>
            </html>
            ''', 400
        
        bookings = get_bookings_count_by_date()
        bookings_count = bookings.get(date_str, 0)
        
        if bookings_count >= 2:
            return '''
            <!DOCTYPE html>
            <html>
            <body style="padding: 40px; text-align: center; font-family: Arial;">
                <h1 style="color: #e74c3c;">❌ Мест нет</h1>
                <a href="/" style="display: inline-block; padding: 12px 24px; background: #3498db; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px;">Вернуться</a>
            </body>
            </html>
            ''', 400
        
        available_slots = 2 - bookings_count
        
        return render_template('booking.html',
                             date_str=date_str,
                             date_formatted=date_obj.strftime('%d.%m.%Y'),
                             weekday=RUSSIAN_WEEKDAYS_FULL[date_obj.weekday()],
                             available_slots=available_slots)
        
    except:
        return redirect('/')

@app.route('/submit_booking', methods=['POST'])
def submit_booking():
    """Обработка формы записи"""
    try:
        excursion_date = request.form.get('excursion_date')
        username = request.form.get('username')
        school_name = request.form.get('school_name')
        class_number = request.form.get('class_number')
        class_profile = request.form.get('class_profile', '')
        contact_person = request.form.get('contact_person')
        contact_phone = request.form.get('contact_phone')
        participants_count = request.form.get('participants_count')
        
        # Валидация
        if not all([excursion_date, username, school_name, class_number, contact_person, contact_phone, participants_count]):
            flash('Заполните все обязательные поля', 'error')
            return redirect(f'/book/{excursion_date}')
        
        # Проверяем доступность
        bookings = get_bookings_count_by_date()
        if bookings.get(excursion_date, 0) >= 2:
            return '''
            <!DOCTYPE html>
            <html>
            <body style="padding: 40px; text-align: center; font-family: Arial;">
                <h1 style="color: #e74c3c;">❌ Мест нет</h1>
                <a href="/" style="display: inline-block; padding: 12px 24px; background: #3498db; color: white; text-decoration: none; border-radius: 5px;">Вернуться</a>
            </body>
            </html>
            '''
        
        # Сохраняем в БД
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
        
        # Успех
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
        <body style="padding: 40px; text-align: center; font-family: Arial;">
            <h1 style="color: #e74c3c;">❌ Ошибка: {str(e)}</h1>
            <a href="/" style="display: inline-block; padding: 12px 24px; background: #3498db; color: white; text-decoration: none; border-radius: 5px;">Вернуться</a>
        </body>
        </html>
        ''', 500

@app.route('/admin')
def admin():
    """Админ-панель"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM bookings ORDER BY excursion_date DESC')
    bookings = cursor.fetchall()
    conn.close()
    
    return render_template('admin.html', bookings=bookings)

@app.route('/clear_test')
def clear_test():
    """Очистка тестовых данных (только для разработки)"""
    if os.environ.get('RENDER') != 'true':  # На продакшене отключаем
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bookings WHERE username = 'Тестовый'")
        conn.commit()
        conn.close()
        return '<h1>✅ Тестовые данные очищены</h1><a href="/admin">Вернуться</a>'
    return '<h1>❌ Недоступно на продакшене</h1>'

@app.route('/health')
def health():
    """Проверка работоспособности (для Render)"""
    return {'status': 'ok', 'timestamp': datetime.now().isoformat()}

if __name__ == '__main__':
    # На Render порт берется из переменной окружения
    port = int(os.environ.get('PORT', 5000))
    init_database()
    app.run(host='0.0.0.0', port=port, debug=False)