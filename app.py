from flask import Flask, render_template, request, redirect, url_for, send_file, session, jsonify
import os
from datetime import datetime, timedelta, date
import calendar
import psycopg
from psycopg.rows import dict_row
import urllib.parse
from io import BytesIO
import pandas as pd

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

# Флаг для отслеживания инициализации БД
db_initialized = False

def get_db_connection():
    """Подключение к PostgreSQL с psycopg3"""
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # Парсим URL для Render
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
        # Для локальной разработки
        conn = psycopg.connect(
            dbname='tax_excursion',
            user='postgres',
            password='postgres',
            host='localhost'
        )
    
    return conn

def init_database():
    """Инициализация БД"""
    global db_initialized
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100),
                school_name VARCHAR(200) NOT NULL,
                class_number VARCHAR(20) NOT NULL,
                class_profile VARCHAR(100),
                excursion_date DATE NOT NULL,
                contact_person VARCHAR(200) NOT NULL,
                contact_phone VARCHAR(20) NOT NULL,
                participants_count INTEGER NOT NULL,
                booking_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                additional_info TEXT,
                status VARCHAR(20) DEFAULT 'pending'
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

def get_bookings_count_by_date():
    """Количество записей по датам"""
    check_and_init_db()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT excursion_date::text, COUNT(*) as count 
            FROM bookings 
            WHERE status != 'cancelled'
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
    """Генерация календаря"""
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
        })
    
    for i in range(0, len(days), 7):
        week = days[i:i+7]
        while len(week) < 7:
            week.append(None)
        calendar_data['weeks'].append(week)
    
    return calendar_data

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
        <head>
            <title>Запись на экскурсию</title>
            <style>
                body {{ font-family: Arial; padding: 40px; text-align: center; }}
                .container {{ max-width: 600px; margin: 0 auto; }}
                .success {{ color: #2ecc71; font-size: 1.2em; }}
                .error {{ color: #e74c3c; background: #ffe6e6; padding: 15px; border-radius: 5px; }}
                .btn {{ display: inline-block; padding: 12px 24px; background: #3498db; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Запись на экскурсию в УФНС</h1>
                <p class="success">✅ Сайт работает на Python 3.13.4</p>
                
                <div class="error">
                    <h3>⚠️ Временно недоступно</h3>
                    <p>Проводятся технические работы. Попробуйте через несколько минут.</p>
                    <p><small>Ошибка: {str(e)}</small></p>
                </div>
                
                <a href="/" class="btn">Обновить страницу</a>
                
                <div style="margin-top: 40px; padding: 20px; background: #f8f9fa; border-radius: 10px;">
                    <h3>Тестовые ссылки:</h3>
                    <p><a href="/admin/login">Админ-панель</a></p>
                    <p><a href="/health">Проверка работоспособности</a></p>
                </div>
            </div>
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
        
        if date_obj.weekday() >= 5:
            return '''
            <!DOCTYPE html>
            <html>
            <body style="font-family: Arial; padding: 40px; text-align: center;">
                <h1 style="color: #e74c3c;">❌ Запись возможна только в будние дни (Пн-Пт)</h1>
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
                             weekday=RUSSIAN_WEEKDAYS_FULL[date_obj.weekday()],
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
        contact_person = request.form.get('contact_person')
        contact_phone = request.form.get('contact_phone')
        participants_count = request.form.get('participants_count')
        additional_info = request.form.get('additional_info', '')
        
        # Валидация
        if not all([excursion_date, username, school_name, class_number, 
                   contact_person, contact_phone, participants_count]):
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
        
        # Проверяем доступность (максимум 2 записи в день)
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
             excursion_date, contact_person, contact_phone, participants_count, additional_info)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (username, school_name, class_number, class_profile,
              excursion_date, contact_person, contact_phone, int(participants_count), additional_info))
        
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
        <style>
            body { font-family: Arial; padding: 40px; text-align: center; background: #f5f5f5; }
            .login-box { max-width: 400px; margin: 50px auto; background: white; padding: 40px; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
            input[type="password"] { width: 100%; padding: 12px; margin: 20px 0; border: 1px solid #ddd; border-radius: 5px; }
            button { background: #3498db; color: white; border: none; padding: 12px 30px; border-radius: 5px; cursor: pointer; }
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

def admin_required(f):
    """Декоратор для проверки авторизации админа"""
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect('/admin/login')
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin')
@admin_required
def admin():
    """Админ-панель"""
    check_and_init_db()
    
    try:
        # Фильтрация
        status_filter = request.args.get('status', 'all')
        date_filter = request.args.get('date', '')
        
        conn = get_db_connection()
        cursor = conn.cursor(row_factory=dict_row)
        
        query = '''
            SELECT id, username, school_name, class_number, class_profile,
                   excursion_date, contact_person, contact_phone, 
                   participants_count, booking_date, status, additional_info
            FROM bookings 
        '''
        params = []
        where_clauses = []
        
        if status_filter != 'all':
            where_clauses.append('status = %s')
            params.append(status_filter)
        
        if date_filter:
            where_clauses.append('excursion_date = %s')
            params.append(date_filter)
        
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
        
        cursor.execute('''
            SELECT excursion_date, COUNT(*) as count 
            FROM bookings 
            WHERE excursion_date >= CURRENT_DATE 
            AND status != 'cancelled'
            GROUP BY excursion_date 
            ORDER BY excursion_date
        ''')
        upcoming = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template('admin.html', 
                             bookings=bookings,
                             status_filter=status_filter,
                             date_filter=date_filter,
                             stats={
                                 'total': total,
                                 'pending': pending,
                                 'confirmed': confirmed,
                                 'cancelled': cancelled,
                                 'upcoming': upcoming
                             })
    except Exception as e:
        return f'''
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial; padding: 40px;">
            <h1>Ошибка админ-панели</h1>
            <pre>{str(e)}</pre>
            <a href="/">На главную</a>
        </body>
        </html>
        ''', 500

@app.route('/admin/export')
@admin_required
def export_bookings():
    """Экспорт записей в Excel"""
    try:
        conn = get_db_connection()
        
        # Получаем данные
        query = '''
            SELECT 
                id,
                username,
                school_name,
                class_number,
                class_profile,
                excursion_date,
                contact_person,
                contact_phone,
                participants_count,
                booking_date,
                status,
                additional_info
            FROM bookings 
            ORDER BY excursion_date DESC
        '''
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        # Русские названия колонок
        df.columns = [
            'ID',
            'ФИО ответственного',
            'Учебное заведение',
            'Класс/Курс',
            'Профиль класса',
            'Дата экскурсии',
            'Контактное лицо в УФНС',
            'Контактный телефон',
            'Количество участников',
            'Дата и время записи',
            'Статус',
            'Дополнительная информация'
        ]
        
        # Преобразуем статусы
        status_mapping = {
            'pending': 'Ожидание',
            'confirmed': 'Подтверждено',
            'cancelled': 'Отменено'
        }
        df['Статус'] = df['Статус'].map(status_mapping).fillna(df['Статус'])
        
        # Создаем Excel файл в памяти
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Записи на экскурсии', index=False)
            
            # Настройка ширины колонок
            worksheet = writer.sheets['Записи на экскурсии']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 30)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        output.seek(0)
        
        # Генерируем имя файла с текущей датой
        filename = f'bookings_{datetime.now().strftime("%Y-%m-%d_%H-%M")}.xlsx'
        
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        return f'''
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial; padding: 40px; text-align: center;">
            <h1 style="color: #e74c3c;">❌ Ошибка экспорта</h1>
            <p>{str(e)}</p>
            <a href="/admin">Вернуться в админ-панель</a>
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
        contact_person = request.form.get('contact_person')
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
                contact_person = %s,
                contact_phone = %s,
                participants_count = %s,
                status = %s,
                additional_info = %s
            WHERE id = %s
        ''', (school_name, class_number, class_profile, excursion_date,
              contact_person, contact_phone, participants_count, status,
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
    """Обновление статуса записи"""
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
            'python_version': '3.13.4',
            'database': 'connected',
            'service': 'tax-excursion'
        }
    except Exception as e:
        return {
            'status': 'unhealthy',
            'timestamp': datetime.now().isoformat(),
            'python_version': '3.13.4',
            'database': 'disconnected',
            'error': str(e)
        }, 500

if __name__ == '__main__':
    # Инициализируем БД при запуске
    init_database()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)