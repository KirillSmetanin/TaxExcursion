from flask import Flask, render_template, request, redirect, url_for, flash
import os
from datetime import datetime, timedelta, date
import calendar
import psycopg2
from psycopg2.extras import DictCursor
import urllib.parse

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

# Русские названия месяцев
RUSSIAN_MONTHS = [
    'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
]

# Русские дни недели
RUSSIAN_WEEKDAYS_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
RUSSIAN_WEEKDAYS_FULL = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']

def get_db_connection():
    """Создает подключение к PostgreSQL"""
    # Получаем URL базы данных из переменной окружения
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # Парсим URL для Render
        parsed_url = urllib.parse.urlparse(database_url)
        
        conn = psycopg2.connect(
            database=parsed_url.path[1:],
            user=parsed_url.username,
            password=parsed_url.password,
            host=parsed_url.hostname,
            port=parsed_url.port,
            sslmode='require'
        )
    else:
        # Для локальной разработки
        conn = psycopg2.connect(
            dbname='tax_excursion',
            user='postgres',
            password='postgres',
            host='localhost'
        )
    
    conn.autocommit = False
    return conn

def init_database():
    """Создает таблицы если они не существуют"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Создаем таблицу bookings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL DEFAULT 1,
                username VARCHAR(100),
                school_name VARCHAR(200) NOT NULL,
                class_number VARCHAR(20) NOT NULL,
                class_profile VARCHAR(100),
                excursion_date DATE NOT NULL,
                contact_person VARCHAR(200) NOT NULL,
                contact_phone VARCHAR(20) NOT NULL,
                participants_count INTEGER NOT NULL,
                booking_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(excursion_date)
            )
        ''')
        
        # Создаем индекс для быстрого поиска
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_excursion_date 
            ON bookings(excursion_date)
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ База данных PostgreSQL инициализирована")
        
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")

def get_bookings_count_by_date():
    """Получаем количество записей на каждую дату"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        
        cursor.execute('''
            SELECT excursion_date::text, COUNT(*) as count 
            FROM bookings 
            GROUP BY excursion_date
            ORDER BY excursion_date
        ''')
        
        booked_dates = {}
        for row in cursor.fetchall():
            booked_dates[str(row['excursion_date'])] = row['count']
        
        cursor.close()
        return booked_dates
        
    except Exception as e:
        print(f"Ошибка получения бронирований: {e}")
        return {}
    finally:
        if conn:
            conn.close()

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
        date_obj = date(year, month, day)
        date_str = date_obj.isoformat()
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
    
    # Разбиваем на недели
    for i in range(0, len(days), 7):
        week = days[i:i+7]
        while len(week) < 7:
            week.append(None)
        calendar_data['weeks'].append(week)
    
    return calendar_data

@app.before_first_request
def initialize():
    """Инициализация при первом запросе"""
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
            <title>Ошибка</title>
            <style>
                body {{ font-family: Arial; padding: 40px; text-align: center; }}
                .error {{ color: #e74c3c; background: #ffe6e6; padding: 20px; border-radius: 10px; max-width: 600px; margin: 20px auto; }}
                .btn {{ display: inline-block; padding: 12px 24px; background: #3498db; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <h1>Запись на экскурсию</h1>
            <div class="error">
                <h3>⚠️ Временно недоступно</h3>
                <p>Проводятся технические работы. Попробуйте позже.</p>
                <p><small>Ошибка: {str(e)}</small></p>
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
        date_obj = date.fromisoformat(date_str)
        today = date.today()
        
        # Проверки
        if date_obj < today:
            flash('Нельзя записаться на прошедшую дату', 'error')
            return redirect('/')
        
        if date_obj.weekday() >= 5:
            flash('Запись возможна только в будние дни', 'error')
            return redirect('/')
        
        # Проверяем доступность
        bookings = get_bookings_count_by_date()
        bookings_count = bookings.get(date_str, 0)
        
        if bookings_count >= 2:
            flash('На эту дату уже нет свободных мест', 'error')
            return redirect('/')
        
        available_slots = 2 - bookings_count
        
        return render_template('booking.html',
                             date_str=date_str,
                             date_formatted=date_obj.strftime('%d.%m.%Y'),
                             weekday=RUSSIAN_WEEKDAYS_FULL[date_obj.weekday()],
                             available_slots=available_slots)
        
    except:
        flash('Неверный формат даты', 'error')
        return redirect('/')

@app.route('/submit_booking', methods=['POST'])
def submit_booking():
    """Обработка формы записи"""
    try:
        # Получаем данные
        data = request.form
        excursion_date = data.get('excursion_date')
        username = data.get('username')
        school_name = data.get('school_name')
        class_number = data.get('class_number')
        class_profile = data.get('class_profile', '')
        contact_person = data.get('contact_person')
        contact_phone = data.get('contact_phone')
        participants_count = data.get('participants_count')
        
        # Валидация
        required_fields = [excursion_date, username, school_name, class_number, 
                          contact_person, contact_phone, participants_count]
        if not all(required_fields):
            flash('Заполните все обязательные поля', 'error')
            return redirect(f'/book/{excursion_date}')
        
        # Проверяем доступность
        bookings = get_bookings_count_by_date()
        if bookings.get(excursion_date, 0) >= 2:
            flash('На эту дату уже нет мест', 'error')
            return redirect('/')
        
        # Сохраняем в БД
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO bookings 
            (username, school_name, class_number, class_profile, 
             excursion_date, contact_person, contact_phone, participants_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (username, school_name, class_number, class_profile,
              excursion_date, contact_person, contact_phone, int(participants_count)))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        # Успех
        date_obj = date.fromisoformat(excursion_date)
        return render_template('success.html',
                             date_formatted=date_obj.strftime('%d.%m.%Y'),
                             school_name=school_name,
                             contact_person=contact_person)
        
    except Exception as e:
        flash(f'Ошибка при сохранении: {str(e)}', 'error')
        return redirect('/')

@app.route('/admin')
def admin():
    """Админ-панель"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute('''
            SELECT id, username, school_name, class_number, class_profile,
                   excursion_date, contact_person, contact_phone, 
                   participants_count, booking_date
            FROM bookings 
            ORDER BY excursion_date DESC
        ''')
        bookings = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return render_template('admin.html', bookings=bookings)
    except Exception as e:
        return f'Ошибка при загрузке данных: {str(e)}', 500

@app.route('/admin/delete/<int:booking_id>', methods=['POST'])
def delete_booking(booking_id):
    """Удаление записи (только для админа)"""
    if request.method == 'POST':
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM bookings WHERE id = %s', (booking_id,))
            conn.commit()
            cursor.close()
            conn.close()
            flash('Запись успешно удалена', 'success')
        except Exception as e:
            flash(f'Ошибка при удалении: {str(e)}', 'error')
    
    return redirect('/admin')

@app.route('/health')
def health():
    """Проверка работоспособности"""
    try:
        # Проверяем подключение к БД
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        cursor.close()
        conn.close()
        
        return {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'database': 'connected'
        }
    except Exception as e:
        return {
            'status': 'unhealthy',
            'timestamp': datetime.now().isoformat(),
            'database': 'disconnected',
            'error': str(e)
        }, 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    init_database()
    app.run(host='0.0.0.0', port=port, debug=False)