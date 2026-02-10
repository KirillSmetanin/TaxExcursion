from flask import Flask, render_template, request, redirect, url_for, send_file, session, make_response, jsonify
import os
from datetime import datetime, timedelta, date
import calendar
import psycopg
from psycopg.rows import dict_row
import urllib.parse
import csv
import io
import threading
import requests
import time
from functools import wraps

# Импортируем функции из отдельных файлов
from database_fix import fix_database_operation

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-12345')
app.config['ADMIN_PASSWORD'] = os.environ.get('ADMIN_PASSWORD', 'YFNS_BOT_Password123')

# Русские названия месяцев
RUSSIAN_MONTHS = [
    'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
]

RUSSIAN_WEEKDAYS_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
RUSSIAN_WEEKDAYS_FULL = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']

# Дни недели, которые должны быть закрыты (понедельник=0, пятница=4)
CLOSED_WEEKDAYS = [0, 4]

# Флаг для отслеживания инициализации БД
db_initialized = False

def start_keep_alive():
    """Запускает keep-alive в фоновом потоке"""
    def ping_self():
        url = os.environ.get('RENDER_EXTERNAL_URL', 'https://taxexcursion.ru')
        
        while True:
            try:
                response = requests.get(f"{url}/health", timeout=10)
                print(f"[{datetime.now()}] Keep-alive ping: {response.status_code}")
            except Exception as e:
                print(f"[{datetime.now()}] Keep-alive failed: {e}")
            
            time.sleep(600)

    if os.environ.get('RENDER') == 'true':
        thread = threading.Thread(target=ping_self, daemon=True)
        thread.start()
        print("✅ Keep-alive service started")

def get_db_connection():
    """Подключение к PostgreSQL с psycopg3"""
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        parsed_url = urllib.parse.urlparse(database_url)
        
        conn = psycopg.connect(
            dbname=parsed_url.path[1:],
            user=parsed_url.username,
            password=parsed_url.password,
            host=parsed_url.hostname,
            port=parsed_url.port,
            sslmode='require'
        )
    else:
        conn = psycopg.connect(
            dbname='tax_excursion',
            user='postgres',
            password='postgres',
            host='localhost'
        )
    
    return conn

def init_database():
    """Инициализация БД с таблицей для заблокированных дат"""
    global db_initialized
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Создаем таблицу бронирований если ее нет
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100),
                school_name VARCHAR(200) NOT NULL,
                class_number VARCHAR(20) NOT NULL,
                class_profile VARCHAR(100),
                excursion_date DATE NOT NULL,
                contact_phone VARCHAR(20) NOT NULL,
                participants_count INTEGER NOT NULL,
                booking_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                additional_info TEXT,
                status VARCHAR(20) DEFAULT 'pending'
            )
        ''')
        
        # Создаем таблицу для заблокированных дат
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blocked_dates (
                id SERIAL PRIMARY KEY,
                blocked_date DATE NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()
        db_initialized = True
        print("✅ База данных PostgreSQL инициализирована")
        
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")

def check_and_init_db():
    """Проверяет и инициализирует БД если нужно"""
    global db_initialized
    if not db_initialized:
        init_database()

def get_blocked_dates():
    """Получает заблокированные даты из БД"""
    check_and_init_db()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT blocked_date FROM blocked_dates')
        dates = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return {date[0].isoformat() for date in dates}
        
    except Exception as e:
        print(f"Ошибка получения заблокированных дат: {e}")
        return set()

def is_date_blocked(date_obj):
    """Проверяет, заблокирована ли дата"""
    blocked_dates = get_blocked_dates()
    return date_obj.isoformat() in blocked_dates

def block_date(date_str):
    """Блокирует дату"""
    check_and_init_db()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('INSERT INTO blocked_dates (blocked_date) VALUES (%s) ON CONFLICT DO NOTHING', (date_str,))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return True, "Дата заблокирована"
        
    except Exception as e:
        return False, str(e)

def unblock_date(date_str):
    """Разблокирует дату"""
    check_and_init_db()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM blocked_dates WHERE blocked_date = %s', (date_str,))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return True, "Дата разблокирована"
        
    except Exception as e:
        return False, str(e)

def get_bookings_count_by_date():
    """Количество записей по датам"""
    check_and_init_db()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT excursion_date::text, COUNT(*) as count 
            FROM bookings 
            WHERE (status != 'cancelled' OR status IS NULL)
            GROUP BY excursion_date
        ''')
        
        booked_dates = {}
        for row in cursor.fetchall():
            booked_dates[row[0]] = row[1]
        
        cursor.close()
        conn.close()
        return booked_dates
        
    except Exception as e:
        print(f"Ошибка получения бронирований: {e}")
        return {}

def generate_calendar_data(year=None, month=None):
    """Генерация календаря с учетом закрытых дней недели и заблокированных дат"""
    today = date.today()
    
    if year is None:
        year = today.year
    if month is None:
        month = today.month
    
    _, num_days = calendar.monthrange(year, month)
    first_weekday = calendar.weekday(year, month, 1)
    
    bookings = get_bookings_count_by_date()
    blocked_dates_set = get_blocked_dates()
    
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
        is_closed_weekday = weekday in CLOSED_WEEKDAYS
        
        if date_obj < today:
            status = 'past'
            available_slots = 0
        elif is_weekend:
            status = 'weekend'
            available_slots = 0
        elif is_closed_weekday:
            status = 'closed'
            available_slots = 0
        elif date_str in blocked_dates_set:
            status = 'blocked'
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
            'is_closed_weekday': is_closed_weekday,
            'is_blocked': date_str in blocked_dates_set,
            'weekday_name': RUSSIAN_WEEKDAYS_FULL[weekday],
        })
    
    for i in range(0, len(days), 7):
        week = days[i:i+7]
        while len(week) < 7:
            week.append(None)
        calendar_data['weeks'].append(week)
    
    return calendar_data

# Декоратор для админ-доступа
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect('/admin/login')
        return f(*args, **kwargs)
    return decorated_function

# Маршруты для пользовательской части
@app.route('/')
def index():
    """Главная страница"""
    check_and_init_db()
    
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
        <body style="font-family: Arial; padding: 40px; text-align: center;">
            <h1 style="color: #e74c3c;">❌ Ошибка загрузки календаря</h1>
            <pre>{str(e)}</pre>
            <a href="/" style="display: inline-block; padding: 12px 24px; background: #3498db; color: white; text-decoration: none; border-radius: 5px;">
                Обновить страницу
            </a>
        </body>
        </html>
        ''', 500

@app.route('/month/<int:year>/<int:month>')
def month_view(year, month):
    """Просмотр конкретного месяца"""
    check_and_init_db()
    
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
    """Страница записи"""
    check_and_init_db()
    
    try:
        date_obj = date.fromisoformat(date_str)
        today = date.today()
        
        if date_obj < today:
            return '''
            <!DOCTYPE html>
            <html>
            <body style="font-family: Arial; padding: 40px; text-align: center;">
                <h1 style="color: #e74c3c;">❌ Нельзя записаться на прошедшую дату</h1>
                <a href="/" style="display: inline-block; padding: 12px 24px; background: #3498db; color: white; text-decoration: none; border-radius: 5px;">
                    Вернуться к календарю
                </a>
            </body>
            </html>
            ''', 400
        
        weekday = date_obj.weekday()
        if weekday >= 5:
            return '''
            <!DOCTYPE html>
            <html>
            <body style="font-family: Arial; padding: 40px; text-align: center;">
                <h1 style="color: #e74c3c;">❌ Запись возможна только в будние дни (Вт-Чт)</h1>
                <a href="/" style="display: inline-block; padding: 12px 24px; background: #3498db; color: white; text-decoration: none; border-radius: 5px;">
                    Вернуться к календарю
                </a>
            </body>
            </html>
            ''', 400
        
        if weekday in CLOSED_WEEKDAYS:
            return f'''
            <!DOCTYPE html>
            <html>
            <body style="font-family: Arial; padding: 40px; text-align: center;">
                <h1 style="color: #e74c3c;">❌ Запись недоступна</h1>
                <p>По понедельникам и пятницам экскурсии не проводятся.</p>
                <a href="/" style="display: inline-block; padding: 12px 24px; background: #3498db; color: white; text-decoration: none; border-radius: 5px;">
                    Вернуться к календарю
                </a>
            </body>
            </html>
            ''', 400
        
        if is_date_blocked(date_obj):
            return '''
            <!DOCTYPE html>
            <html>
            <body style="font-family: Arial; padding: 40px; text-align: center;">
                <h1 style="color: #e74c3c;">❌ На эту дату запись временно недоступна</h1>
                <a href="/" style="display: inline-block; padding: 12px 24px; background: #3498db; color: white; text-decoration: none; border-radius: 5px;">
                    Вернуться к календарю
                </a>
            </body>
            </html>
            ''', 400
        
        bookings = get_bookings_count_by_date()
        bookings_count = bookings.get(date_str, 0)
        
        if bookings_count >= 2:
            return '''
            <!DOCTYPE html>
            <html>
            <body style="font-family: Arial; padding: 40px; text-align: center;">
                <h1 style="color: #e74c3c;">❌ На эту дату уже нет свободных мест</h1>
                <a href="/" style="display: inline-block; padding: 12px 24px; background: #3498db; color: white; text-decoration: none; border-radius: 5px;">
                    Вернуться к календарю
                </a>
            </body>
            </html>
            ''', 400
        
        available_slots = 2 - bookings_count
        
        return render_template('booking.html',
                             date_str=date_str,
                             date_formatted=date_obj.strftime('%d.%m.%Y'),
                             weekday=RUSSIAN_WEEKDAYS_FULL[weekday],
                             available_slots=available_slots)
        
    except:
        return redirect('/')

@app.route('/submit_booking', methods=['POST'])
def submit_booking():
    """Обработка формы записи"""
    check_and_init_db()
    
    try:
        excursion_date = request.form.get('excursion_date')
        username = request.form.get('username')
        school_name = request.form.get('school_name')
        class_number = request.form.get('class_number')
        class_profile = request.form.get('class_profile', '')
        contact_phone = request.form.get('contact_phone')
        participants_count = request.form.get('participants_count')
        additional_info = request.form.get('additional_info', '')
        
        # Валидация
        if not all([excursion_date, username, school_name, class_number, 
                   contact_phone, participants_count]):
            return '''
            <!DOCTYPE html>
            <html>
            <body style="font-family: Arial; padding: 40px; text-align: center;">
                <h1 style="color: #e74c3c;">❌ Все обязательные поля должны быть заполнены</h1>
                <a href="/" style="display: inline-block; padding: 12px 24px; background: #3498db; color: white; text-decoration: none; border-radius: 5px;">
                    Вернуться к календарю
                </a>
            </body>
            </html>
            ''', 400
        
        # Проверяем доступность
        bookings = get_bookings_count_by_date()
        current_count = bookings.get(excursion_date, 0)
        
        if current_count >= 2:
            return '''
            <!DOCTYPE html>
            <html>
            <body style="font-family: Arial; padding: 40px; text-align: center;">
                <h1 style="color: #e74c3c;">❌ На эту дату уже нет свободных мест</h1>
                <p>Максимум 2 группы в день.</p>
                <a href="/" style="display: inline-block; padding: 12px 24px; background: #3498db; color: white; text-decoration: none; border-radius: 5px;">
                    Вернуться к календарю
                </a>
            </body>
            </html>
            '''
        
        # Сохраняем в БД
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO bookings 
            (username, school_name, class_number, class_profile, 
             excursion_date, contact_phone, participants_count, additional_info)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (username, school_name, class_number, class_profile,
              excursion_date, contact_phone, int(participants_count), additional_info))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        # Успех
        date_obj = date.fromisoformat(excursion_date)
        return render_template('success.html',
                             date_formatted=date_obj.strftime('%d.%m.%Y'),
                             school_name=school_name)
        
    except Exception as e:
        return f'''
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial; padding: 40px; text-align: center;">
            <h1 style="color: #e74c3c;">❌ Ошибка при обработке заявки</h1>
            <p>{str(e)}</p>
            <a href="/" style="display: inline-block; padding: 12px 24px; background: #3498db; color: white; text-decoration: none; border-radius: 5px;">
                Вернуться к календарю
            </a>
        </body>
        </html>
        ''', 500

# ------------------------------------------------------------
# АДМИН-ЧАСТЬ
# ------------------------------------------------------------

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Вход в админку"""
    if request.method == 'POST':
        password = request.form.get('password')
        if password == app.config['ADMIN_PASSWORD']:
            session['admin_logged_in'] = True
            return redirect('/admin')
        else:
            return '''
            <!DOCTYPE html>
            <html>
            <body style="font-family: Arial; padding: 40px; text-align: center;">
                <h1 style="color: #e74c3c;">❌ Неверный пароль</h1>
                <a href="/admin/login">Попробовать снова</a>
            </body>
            </html>
            '''
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Вход в админ-панель</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: Arial; padding: 20px; text-align: center; background: #f5f5f5; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
            .login-box { max-width: 400px; width: 100%; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
            input[type="password"] { width: 100%; padding: 12px; margin: 20px 0; border: 1px solid #ddd; border-radius: 5px; font-size: 16px; }
            button { background: #3498db; color: white; border: none; padding: 12px 30px; border-radius: 5px; cursor: pointer; font-size: 16px; width: 100%; }
            @media (max-width: 480px) {
                .login-box { padding: 20px; }
                body { padding: 10px; }
            }
        </style>
    </head>
    <body>
        <div class="login-box">
            <h1>Вход в админ-панель</h1>
            <form method="POST">
                <input type="password" name="password" placeholder="Пароль" required>
                <br>
                <button type="submit">Войти</button>
            </form>
        </div>
    </body>
    </html>
    '''

@app.route('/admin/logout')
def admin_logout():
    """Выход из админки"""
    session.pop('admin_logged_in', None)
    return redirect('/')

@app.route('/admin')
@admin_required
def admin():
    """Админ-панель с фильтрацией и статистикой"""
    check_and_init_db()
    
    try:
        # Фильтрация
        status_filter = request.args.get('status', 'all')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        search = request.args.get('search', '')
        
        conn = get_db_connection()
        cursor = conn.cursor(row_factory=dict_row)
        
        # Базовый запрос
        query = '''
            SELECT id, username, school_name, class_number, class_profile,
                   excursion_date, contact_phone, 
                   participants_count, booking_date, status, additional_info
            FROM bookings 
        '''
        params = []
        where_clauses = []
        
        if status_filter != 'all':
            where_clauses.append('status = %s')
            params.append(status_filter)
        
        if date_from:
            where_clauses.append('excursion_date >= %s')
            params.append(date_from)
        
        if date_to:
            where_clauses.append('excursion_date <= %s')
            params.append(date_to)
        
        if search:
            where_clauses.append('''
                (school_name ILIKE %s OR 
                 username ILIKE %s OR 
                 contact_phone ILIKE %s)
            ''')
            search_term = f'%{search}%'
            params.extend([search_term, search_term, search_term])
        
        if where_clauses:
            query += ' WHERE ' + ' AND '.join(where_clauses)
        
        query += ' ORDER BY excursion_date DESC, booking_date DESC'
        
        cursor.execute(query, params)
        bookings = cursor.fetchall()
        
        # Статистика
        cursor.execute('SELECT COUNT(*) as total FROM bookings')
        total = cursor.fetchone()['total']
        
        cursor.execute('SELECT COUNT(*) as pending FROM bookings WHERE status = %s', ('pending',))
        pending = cursor.fetchone()['pending']
        
        cursor.execute('SELECT COUNT(*) as confirmed FROM bookings WHERE status = %s', ('confirmed',))
        confirmed = cursor.fetchone()['confirmed']
        
        cursor.execute('SELECT COUNT(*) as cancelled FROM bookings WHERE status = %s', ('cancelled',))
        cancelled = cursor.fetchone()['cancelled']
        
        # Статистика по месяцам
        cursor.execute('''
            SELECT 
                DATE_TRUNC('month', excursion_date) as month,
                COUNT(*) as count
            FROM bookings 
            WHERE excursion_date >= CURRENT_DATE - INTERVAL '6 months'
            GROUP BY DATE_TRUNC('month', excursion_date)
            ORDER BY month DESC
        ''')
        monthly_stats = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template('admin.html', 
                             bookings=bookings,
                             status_filter=status_filter,
                             date_from=date_from,
                             date_to=date_to,
                             search=search,
                             stats={
                                 'total': total,
                                 'pending': pending,
                                 'confirmed': confirmed,
                                 'cancelled': cancelled,
                                 'monthly_stats': monthly_stats
                             },
                             today=date.today())
    except Exception as e:
        return f'''
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial; padding: 40px; text-align: center;">
            <h1>Ошибка админ-панели</h1>
            <pre>{str(e)}</pre>
            <a href="/">На главную</a>
        </body>
        </html>
        ''', 500

@app.route('/admin/block_date', methods=['POST'])
@admin_required
def admin_block_date():
    """Блокировка даты через API"""
    try:
        data = request.get_json()
        date_str = data.get('date')
        
        if not date_str:
            return jsonify({'success': False, 'message': 'Дата не указана'}), 400
        
        success, message = block_date(date_str)
        
        return jsonify({
            'success': success,
            'message': message,
            'date': date_str
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/unblock_date', methods=['POST'])
@admin_required
def admin_unblock_date():
    """Разблокировка даты через API"""
    try:
        data = request.get_json()
        date_str = data.get('date')
        
        if not date_str:
            return jsonify({'success': False, 'message': 'Дата не указана'}), 400
        
        success, message = unblock_date(date_str)
        
        return jsonify({
            'success': success,
            'message': message,
            'date': date_str
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/fix_database', methods=['GET', 'POST'])
@admin_required
def fix_database():
    """Исправление структуры базы данных - используем внешний модуль"""
    if request.method == 'GET':
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Исправление базы данных</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { font-family: Arial; padding: 20px; background: #f5f5f5; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
                .container { max-width: 800px; width: 100%; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
                .warning-box { background: #fff3cd; border: 2px solid #ffeaa7; padding: 20px; border-radius: 10px; margin: 20px 0; }
                .btn { display: inline-block; padding: 15px 30px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; width: 100%; margin: 10px 0; text-decoration: none; text-align: center; }
                .btn-danger { background: #e74c3c; color: white; }
                .btn-primary { background: #3498db; color: white; }
                .btn-secondary { background: #95a5a6; color: white; }
                input { width: 100%; padding: 12px; margin: 15px 0; border: 2px solid #3498db; border-radius: 5px; font-size: 16px; }
                @media (max-width: 768px) {
                    .container { padding: 20px; }
                    .btn { padding: 12px 24px; }
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🔧 Полное исправление базы данных</h1>
                
                <div class="warning-box">
                    <h2 style="color: #f39c12;">⚠️ Внимание!</h2>
                    <p><strong>Эта операция изменит структуру базы данных:</strong></p>
                    <ul>
                        <li>Удалит колонку <code>contact_person</code> (если существует)</li>
                        <li>Добавит колонку <code>status</code> (если отсутствует)</li>
                        <li>Добавит колонку <code>additional_info</code> (если отсутствует)</li>
                        <li>Создаст таблицу <code>blocked_dates</code> для управления датами</li>
                        <li>Удалит уникальные ограничения на <code>excursion_date</code></li>
                        <li>Обновит существующие записи</li>
                    </ul>
                    <p>Операция <strong>безопасна</strong> для существующих данных.</p>
                </div>
                
                <form method="POST">
                    <p>Для подтверждения введите "ИСПРАВИТЬ БАЗУ" ниже:</p>
                    <input type="text" name="confirmation" placeholder="ИСПРАВИТЬ БАЗУ" required>
                    
                    <button type="submit" class="btn btn-danger">
                        <strong>🚀 ЗАПУСТИТЬ ИСПРАВЛЕНИЕ БАЗЫ</strong>
                    </button>
                    
                    <a href="/admin" class="btn btn-secondary">Отмена - вернуться в админ-панель</a>
                </form>
            </div>
        </body>
        </html>
        '''
    
    if request.method == 'POST':
        confirmation = request.form.get('confirmation')
        if confirmation != 'ИСПРАВИТЬ БАЗУ':
            return '''
            <!DOCTYPE html>
            <html>
            <body style="font-family: Arial; padding: 40px; text-align: center;">
                <h1 style="color: #e74c3c;">❌ Неверное подтверждение</h1>
                <p>Вы должны ввести "ИСПРАВИТЬ БАЗУ" для подтверждения</p>
                <a href="/admin/fix_database">Попробовать снова</a>
            </body>
            </html>
            '''
        
        # Используем внешнюю функцию для миграции
        success, results = fix_database_operation()
        
        html_result = "<br>".join(results)
        
        if success:
            return f'''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Исправление базы данных - завершено</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {{ font-family: Arial; padding: 20px; background: #f5f5f5; }}
                    .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }}
                    .success-box {{ background: #d4edda; border: 2px solid #c3e6cb; padding: 20px; border-radius: 10px; margin: 20px 0; }}
                    .results {{ margin: 20px 0; padding: 20px; background: #f8f9fa; border-radius: 5px; max-height: 500px; overflow-y: auto; font-family: monospace; font-size: 14px; line-height: 1.4; }}
                    .btn {{ display: inline-block; padding: 12px 24px; background: #3498db; color: white; text-decoration: none; border-radius: 5px; margin: 10px; font-size: 14px; }}
                    @media (max-width: 768px) {{
                        .container {{ padding: 20px; }}
                        .btn {{ width: 100%; margin: 5px 0; text-align: center; }}
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1 style="color: #2ecc71;">🎉 Исправление базы данных завершено!</h1>
                    
                    <div class="success-box">
                        <h2>✅ Успешно выполнено!</h2>
                        <p>Все операции миграции успешно выполнены. База данных готова к работе.</p>
                    </div>
                    
                    <div class="results">
                        {html_result}
                    </div>
                    
                    <div style="margin-top: 30px;">
                        <a href="/admin" class="btn">Вернуться в админ-панель</a>
                        <a href="/" class="btn" style="background: #2ecc71;">Перейти к календарю</a>
                    </div>
                </div>
            </body>
            </html>
            '''
        else:
            return f'''
            <!DOCTYPE html>
            <html>
            <body style="font-family: Arial; padding: 40px; text-align: center;">
                <h1 style="color: #e74c3c;">❌ Ошибка исправления базы</h1>
                <div style="background: #ffe6e6; padding: 20px; border-radius: 5px; margin: 20px 0; text-align: left;">
                    {html_result}
                </div>
                <div style="margin-top: 30px;">
                    <a href="/admin" style="display: inline-block; padding: 12px 24px; background: #3498db; color: white; text-decoration: none; border-radius: 5px; margin: 10px;">
                        Вернуться в админ-панель
                    </a>
                    <a href="/admin/fix_database" style="display: inline-block; padding: 12px 24px; background: #e74c3c; color: white; text-decoration: none; border-radius: 5px; margin: 10px;">
                        Попробовать снова
                    </a>
                </div>
            </body>
            </html>
            ''', 500

@app.route('/admin/edit/<int:booking_id>', methods=['GET', 'POST'])
@admin_required
def edit_booking(booking_id):
    """Редактирование записи"""
    conn = get_db_connection()
    cursor = conn.cursor(row_factory=dict_row)
    
    if request.method == 'POST':
        # Обновляем запись
        school_name = request.form.get('school_name')
        class_number = request.form.get('class_number')
        class_profile = request.form.get('class_profile')
        excursion_date = request.form.get('excursion_date')
        contact_phone = request.form.get('contact_phone')
        participants_count = request.form.get('participants_count')
        status = request.form.get('status')
        additional_info = request.form.get('additional_info')
        
        cursor.execute('''
            UPDATE bookings SET
                school_name = %s,
                class_number = %s,
                class_profile = %s,
                excursion_date = %s,
                contact_phone = %s,
                participants_count = %s,
                status = %s,
                additional_info = %s
            WHERE id = %s
        ''', (school_name, class_number, class_profile, excursion_date,
              contact_phone, participants_count, status,
              additional_info, booking_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return redirect('/admin')
    
    # Получаем запись для редактирования
    cursor.execute('SELECT * FROM bookings WHERE id = %s', (booking_id,))
    booking = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if not booking:
        return redirect('/admin')
    
    return render_template('edit_booking.html', booking=booking)

@app.route('/admin/delete/<int:booking_id>', methods=['POST'])
@admin_required
def delete_booking(booking_id):
    """Удаление записи"""
    if request.method == 'POST':
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM bookings WHERE id = %s', (booking_id,))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Ошибка удаления: {e}")
    
    return redirect('/admin')

@app.route('/admin/update_status/<int:booking_id>', methods=['POST'])
@admin_required
def update_status(booking_id):
    """Обновление статуса записи - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    if request.method == 'POST':
        status = request.form.get('status')
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE bookings SET status = %s WHERE id = %s', (status, booking_id))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Ошибка обновления статуса: {e}")
    
    return redirect('/admin')

@app.route('/admin/bulk_actions', methods=['POST'])
@admin_required
def bulk_actions():
    """Массовые действия с записями"""
    action = request.form.get('action')
    selected_ids = request.form.getlist('selected_ids')
    
    if not selected_ids:
        return redirect('/admin')
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if action == 'delete':
            placeholders = ','.join(['%s'] * len(selected_ids))
            cursor.execute(f'DELETE FROM bookings WHERE id IN ({placeholders})', selected_ids)
        elif action == 'confirm':
            placeholders = ','.join(['%s'] * len(selected_ids))
            cursor.execute(f'UPDATE bookings SET status = %s WHERE id IN ({placeholders})', 
                          ['confirmed'] + selected_ids)
        elif action == 'cancel':
            placeholders = ','.join(['%s'] * len(selected_ids))
            cursor.execute(f'UPDATE bookings SET status = %s WHERE id IN ({placeholders})', 
                          ['cancelled'] + selected_ids)
        
        conn.commit()
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Ошибка массовых действий: {e}")
    
    return redirect('/admin')

@app.route('/admin/clear_all', methods=['GET', 'POST'])
@admin_required
def clear_all():
    """Очистка всех записей (с подтверждением)"""
    if request.method == 'GET':
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Очистка базы данных</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { font-family: Arial; padding: 20px; text-align: center; background: #f5f5f5; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
                .warning-box { max-width: 600px; width: 100%; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
                .danger-zone { background: #fff3cd; border: 2px solid #ffeaa7; padding: 20px; border-radius: 10px; margin: 20px 0; }
                .btn-danger { background: #e74c3c; color: white; padding: 15px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; width: 100%; margin: 10px 0; }
                .btn-secondary { background: #95a5a6; color: white; padding: 15px; border-radius: 5px; text-decoration: none; display: block; text-align: center; }
                input { padding: 12px; font-size: 16px; margin: 20px 0; width: 100%; border: 2px solid #e74c3c; border-radius: 5px; }
            </style>
        </head>
        <body>
            <div class="warning-box">
                <h1 style="color: #e74c3c;">⚠️ Очистка всей базы данных</h1>
                
                <div class="danger-zone">
                    <h2>ВНИМАНИЕ! ОПАСНАЯ ОПЕРАЦИЯ!</h2>
                    <p><strong>Будут удалены ВСЕ записи из базы данных.</strong></p>
                    <p>Это действие <strong>НЕЛЬЗЯ отменить!</strong></p>
                    <p>Все данные будут утеряны без возможности восстановления.</p>
                </div>
                
                <form method="POST">
                    <p>Для подтверждения введите "УДАЛИТЬ ВСЕ" в поле ниже:</p>
                    <input type="text" name="confirmation" placeholder="УДАЛИТЬ ВСЕ" required>
                    <button type="submit" class="btn-danger">
                        <strong>УДАЛИТЬ ВСЕ ЗАПИСИ</strong>
                    </button>
                    <br><br>
                    <a href="/admin" class="btn-secondary">Отмена - вернуться в админ-панель</a>
                </form>
            </div>
        </body>
        </html>
        '''
    
    if request.method == 'POST':
        confirmation = request.form.get('confirmation')
        if confirmation == 'УДАЛИТЬ ВСЕ':
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('DELETE FROM bookings')
                conn.commit()
                
                cursor.execute('SELECT COUNT(*) FROM bookings')
                remaining = cursor.fetchone()[0]
                
                cursor.close()
                conn.close()
                
                return f'''
                <!DOCTYPE html>
                <html>
                <body style="font-family: Arial; padding: 40px; text-align: center;">
                    <h1 style="color: #2ecc71;">✅ База данных очищена</h1>
                    <p>Все записи были удалены. Осталось записей: {remaining}</p>
                    <div style="margin-top: 30px;">
                        <a href="/admin" style="display: inline-block; padding: 12px 24px; background: #3498db; color: white; text-decoration: none; border-radius: 5px; margin: 10px;">
                            Вернуться в админ-панель
                        </a>
                    </div>
                </body>
                </html>
                '''
            except Exception as e:
                return f'''
                <!DOCTYPE html>
                <html>
                <body style="font-family: Arial; padding: 40px; text-align: center;">
                    <h1 style="color: #e74c3c;">❌ Ошибка очистки базы</h1>
                    <p>{str(e)}</p>
                    <a href="/admin">Вернуться в админ-панель</a>
                </body>
                </html>
                '''
        else:
            return '''
            <!DOCTYPE html>
            <html>
            <body style="font-family: Arial; padding: 40px; text-align: center;">
                <h1 style="color: #e74c3c;">❌ Неверное подтверждение</h1>
                <p>Вы должны ввести "УДАЛИТЬ ВСЕ" для подтверждения</p>
                <a href="/admin/clear_all">Попробовать снова</a>
            </body>
            </html>
            '''

@app.route('/health')
def health():
    """Проверка работоспособности"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        cursor.execute('SELECT COUNT(*) FROM bookings')
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        
        return {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'python_version': '3.13.4',
            'database': 'connected',
            'total_bookings': count,
            'service': 'tax-excursion'
        }
    except Exception as e:
        return {
            'status': 'unhealthy',
            'timestamp': datetime.now().isoformat(),
            'python_version': '3.13.4',
            'dАatabase': 'disconnected',
            'error': str(e)
        }, 500
    
@app.route('/admin/reset_database', methods=['GET', 'POST'])
@admin_required
def admin_reset_database():
    """Простой сброс базы данных"""
    if request.method == 'GET':
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Сброс базы данных</title>
            <style>
                body { font-family: Arial; padding: 40px; text-align: center; }
                .warning { background: #ffe6e6; padding: 20px; border-radius: 10px; margin: 20px auto; max-width: 600px; }
                .btn { padding: 12px 24px; margin: 10px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
                .btn-danger { background: #e74c3c; color: white; }
                .btn-secondary { background: #95a5a6; color: white; }
                input { padding: 10px; font-size: 16px; width: 300px; margin: 10px; }
            </style>
        </head>
        <body>
            <h1>🚀 Полный сброс базы данных</h1>
            
            <div class="warning">
                <h2 style="color: #e74c3c;">⚠️ ВНИМАНИЕ!</h2>
                <p><strong>Эта операция:</strong></p>
                <ul>
                    <li>Удалит ВСЕ существующие данные</li>
                    <li>Создаст чистые таблицы с правильной структурой</li>
                    <li>Добавит тестовые данные</li>
                    <li><strong>Восстановление невозможно!</strong></li>
                </ul>
            </div>
            
            <form method="POST">
                <p>Для подтверждения введите "УДАЛИТЬ ВСЕ":</p>
                <input type="text" name="confirmation" placeholder="УДАЛИТЬ ВСЕ" required>
                <br>
                <button type="submit" class="btn btn-danger">
                    <strong>🚀 ЗАПУСТИТЬ ПОЛНЫЙ СБРОС БАЗЫ</strong>
                </button>
                <br>
                <a href="/admin" class="btn btn-secondary">Отмена - вернуться в админ-панель</a>
            </form>
        </body>
        </html>
        '''
    
    if request.method == 'POST':
        confirmation = request.form.get('confirmation')
        if confirmation != 'УДАЛИТЬ ВСЕ':
            return '''
            <!DOCTYPE html>
            <html>
            <body style="font-family: Arial; padding: 40px; text-align: center;">
                <h1 style="color: #e74c3c;">❌ Неверное подтверждение</h1>
                <p>Для сброса базы нужно ввести "УДАЛИТЬ ВСЕ"</p>
                <a href="/admin/reset_database">Попробовать снова</a>
            </body>
            </html>
            '''
        
        # Запускаем сброс базы
        success, results = recreate_database()
        html_result = "<br>".join(results)
        
        if success:
            return f'''
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial; padding: 20px; background: #f5f5f5; }}
                    .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }}
                    .success {{ background: #e8f6ef; padding: 20px; border-radius: 10px; }}
                    .results {{ padding: 20px; background: #f8f9fa; border-radius: 5px; }}
                    .btn {{ padding: 10px 20px; background: #3498db; color: white; text-decoration: none; border-radius: 5px; margin: 10px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1 style="color: #2ecc71;">✅ База данных успешно пересоздана!</h1>
                    <div class="success">
                        <p><strong>Операция выполнена успешно!</strong></p>
                    </div>
                    <div class="results">
                        {html_result}
                    </div>
                    <div style="margin-top: 30px;">
                        <a href="/admin" class="btn">Вернуться в админ-панель</a>
                        <a href="/" class="btn" style="background: #2ecc71;">Перейти к календарю</a>
                    </div>
                </div>
            </body>
            </html>
            '''
        else:
            return f'''
            <!DOCTYPE html>
            <html>
            <body style="font-family: Arial; padding: 40px; text-align: center;">
                <h1 style="color: #e74c3c;">❌ Ошибка сброса базы</h1>
                <div style="background: #ffe6e6; padding: 20px; border-radius: 5px; margin: 20px 0; text-align: left;">
                    {html_result}
                </div>
                <div>
                    <a href="/admin" style="padding: 10px 20px; background: #3498db; color: white; text-decoration: none; border-radius: 5px; margin: 10px;">
                        Вернуться в админ-панель
                    </a>
                    <a href="/admin/reset_database" style="padding: 10px 20px; background: #e74c3c; color: white; text-decoration: none; border-radius: 5px; margin: 10px;">
                        Попробовать снова
                    </a>
                </div>
            </body>
            </html>
            ''', 500

def recreate_database():
    """Полный сброс и пересоздание базы данных"""
    results = []
    
    try:
        results.append("<strong>🚀 ЗАПУСК ПОЛНОГО СБРОСА БАЗЫ ДАННЫХ...</strong>")
        results.append("<br><strong style='color: #e74c3c;'>⚠️ ВНИМАНИЕ: ВСЕ ДАННЫЕ БУДУТ УДАЛЕНЫ!</strong>")
        
        # Подключаемся к базе
        conn = get_db_connection()
        conn.autocommit = False
        
        try:
            cursor = conn.cursor()
            
            # 1. Удаляем все таблицы если они существуют
            results.append("<br><strong>📊 Шаг 1: Удаление существующих таблиц...</strong>")
            
            cursor.execute("DROP TABLE IF EXISTS bookings CASCADE")
            results.append("   ✅ Таблица bookings удалена")
            
            cursor.execute("DROP TABLE IF EXISTS blocked_dates CASCADE")
            results.append("   ✅ Таблица blocked_dates удалена")
            
            # Коммитим удаление
            conn.commit()
            results.append("   ✅ Все таблицы удалены")
            
            # 2. Создаем таблицу bookings с правильной структурой
            results.append("<br><strong>📊 Шаг 2: Создание новой таблицы bookings...</strong>")
            
            cursor.execute('''
                CREATE TABLE bookings (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) NOT NULL,
                    school_name VARCHAR(200) NOT NULL,
                    class_number VARCHAR(20) NOT NULL,
                    class_profile VARCHAR(100),
                    excursion_date DATE NOT NULL,
                    contact_phone VARCHAR(20) NOT NULL,
                    participants_count INTEGER NOT NULL,
                    booking_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    additional_info TEXT,
                    status VARCHAR(20) DEFAULT 'pending'
                )
            ''')
            
            results.append("   ✅ Таблица bookings создана")
            
            # 3. Создаем таблицу blocked_dates
            results.append("<br><strong>📊 Шаг 3: Создание таблицы blocked_dates...</strong>")
            
            cursor.execute('''
                CREATE TABLE blocked_dates (
                    id SERIAL PRIMARY KEY,
                    blocked_date DATE NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            results.append("   ✅ Таблица blocked_dates создана")
            
            # 4. Добавляем индексы для ускорения поиска
            results.append("<br><strong>📊 Шаг 4: Создание индексов...</strong>")
            
            cursor.execute('CREATE INDEX idx_bookings_date ON bookings(excursion_date)')
            cursor.execute('CREATE INDEX idx_bookings_status ON bookings(status)')
            cursor.execute('CREATE INDEX idx_bookings_school ON bookings(school_name)')
            
            results.append("   ✅ Индексы созданы")
            
            # 5. Тестируем вставку
            results.append("<br><strong>📊 Шаг 5: Тестирование вставки данных...</strong>")
            
            # Тестовые данные
            cursor.execute('''
                INSERT INTO bookings 
                (username, school_name, class_number, class_profile, 
                 excursion_date, contact_phone, participants_count, status, additional_info)
                VALUES 
                ('Иванов Иван Иванович', 'Гимназия №1', '10А', 'Физмат', 
                 '2024-03-15', '+79991234567', 25, 'pending', 'Первая тестовая запись'),
                ('Петрова Анна Сергеевна', 'Лицей №2', '11Б', 'Гуманитарный', 
                 '2024-03-16', '+79997654321', 20, 'confirmed', 'Вторая тестовая запись'),
                ('Сидоров Алексей Петрович', 'Школа №3', '9В', '', 
                 '2024-03-17', '+79995554433', 15, 'pending', 'Третья тестовая запись')
            ''')
            
            # Тестовая заблокированная дата
            cursor.execute('INSERT INTO blocked_dates (blocked_date) VALUES (%s)', ('2024-03-18',))
            
            results.append("   ✅ Тестовые данные добавлены")
            
            # 6. Проверяем структуру
            results.append("<br><strong>📊 Шаг 6: Проверка структуры базы...</strong>")
            
            cursor.execute("SELECT COUNT(*) FROM bookings")
            bookings_count = cursor.fetchone()[0]
            results.append(f"   📊 Записей в bookings: {bookings_count}")
            
            cursor.execute("SELECT COUNT(*) FROM blocked_dates")
            blocked_count = cursor.fetchone()[0]
            results.append(f"   📊 Заблокированных дат: {blocked_count}")
            
            # Финализируем
            conn.commit()
            
            results.append("<br><strong style='color: #2ecc71;'>✅ БАЗА ДАННЫХ УСПЕШНО ПЕРЕСОЗДАНА!</strong>")
            results.append("<br>Структура базы:")
            results.append("   • bookings - таблица бронирований")
            results.append("   • blocked_dates - таблица заблокированных дат")
            results.append("   • Все индексы созданы")
            results.append("   • Тестовые данные добавлены")
            
            cursor.close()
            conn.close()
            
            return True, results
            
        except Exception as e:
            # Откатываем изменения при ошибке
            conn.rollback()
            cursor.close()
            conn.close()
            raise e
            
    except Exception as e:
        results.append(f"<br><strong style='color: #e74c3c;'>❌ КРИТИЧЕСКАЯ ОШИБКА: {str(e)}</strong>")
        return False, results

if __name__ == '__main__':
    init_database()
    start_keep_alive()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)