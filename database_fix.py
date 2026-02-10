# database_fix.py - Инструменты для работы с базой данных
import os
import urllib.parse
import psycopg

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

# СОХРАНИТЬ ЭТУ ФУНКЦИЮ для совместимости с app.py
def fix_database_operation():
    """Основная операция исправления базы данных (старая функция для совместимости)"""
    # Перенаправляем на мягкое исправление для сохранения обратной совместимости
    return fix_database_soft()

def reset_database_radical():
    """РАДИКАЛЬНОЕ решение: полный сброс базы данных (удаляет все данные!)"""
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
            
            # Получаем список всех таблиц
            cursor.execute("""
                SELECT tablename 
                FROM pg_tables 
                WHERE schemaname = 'public'
            """)
            
            tables = cursor.fetchall()
            for table in tables:
                table_name = table[0]
                try:
                    cursor.execute(f'DROP TABLE IF EXISTS {table_name} CASCADE')
                    results.append(f"   ✅ Удалена таблица: {table_name}")
                except Exception as e:
                    results.append(f"   ⚠️  Не удалось удалить {table_name}: {str(e)}")
            
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
            
            # 4. Добавляем индекс для ускорения поиска
            results.append("<br><strong>📊 Шаг 4: Создание индексов...</strong>")
            
            cursor.execute('CREATE INDEX idx_bookings_date ON bookings(excursion_date)')
            cursor.execute('CREATE INDEX idx_bookings_status ON bookings(status)')
            cursor.execute('CREATE INDEX idx_bookings_school ON bookings(school_name)')
            
            results.append("   ✅ Индексы созданы")
            
            # 5. Тестируем вставку
            results.append("<br><strong>📊 Шаг 5: Тестирование вставки данных...</strong>")
            
            # Тестовые данные
            test_data = [
                ('Иванов Иван Иванович', 'Гимназия №1', '10А', 'Физмат', 
                 '2024-03-15', '+79991234567', 25, 'pending', 'Первая тестовая запись'),
                ('Петрова Анна Сергеевна', 'Лицей №2', '11Б', 'Гуманитарный', 
                 '2024-03-16', '+79997654321', 20, 'confirmed', 'Вторая тестовая запись'),
                ('Сидоров Алексей Петрович', 'Школа №3', '9В', '', 
                 '2024-03-17', '+79995554433', 15, 'pending', 'Третья тестовая запись')
            ]
            
            for data in test_data:
                cursor.execute('''
                    INSERT INTO bookings 
                    (username, school_name, class_number, class_profile, 
                     excursion_date, contact_phone, participants_count, status, additional_info)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', data)
            
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
            
            # Показываем структуру bookings
            results.append("<br><strong>Структура таблицы bookings:</strong>")
            cursor.execute("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = 'bookings'
                ORDER BY ordinal_position
            """)
            
            columns = cursor.fetchall()
            for col in columns:
                results.append(f"   - {col[0]} ({col[1]}) {'NULL' if col[2] == 'YES' else 'NOT NULL'}")
            
            # Показываем структуру blocked_dates
            results.append("<br><strong>Структура таблицы blocked_dates:</strong>")
            cursor.execute("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = 'blocked_dates'
                ORDER BY ordinal_position
            """)
            
            columns = cursor.fetchall()
            for col in columns:
                results.append(f"   - {col[0]} ({col[1]}) {'NULL' if col[2] == 'YES' else 'NOT NULL'}")
            
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

def fix_database_soft():
    """Мягкое исправление: сохраняет существующие данные"""
    results = []
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        results.append("<strong>🚀 Запуск мягкого исправления базы данных...</strong>")
        results.append("<br><strong style='color: #f39c12;'>⚠️ Пытаемся сохранить существующие данные</strong>")
        
        # 1. Проверяем текущую структуру
        results.append("<br><strong>📊 Текущая структура таблицы bookings:</strong>")
        try:
            cursor.execute("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = 'bookings'
                ORDER BY ordinal_position
            """)
            
            columns = cursor.fetchall()
            if columns:
                for col in columns:
                    results.append(f"  - {col[0]} ({col[1]}) {'NULL' if col[2] == 'YES' else 'NOT NULL'}")
            else:
                results.append("   ℹ️ Таблица bookings не существует или пуста")
        except:
            results.append("   ℹ️ Не удалось получить структуру таблицы")
        
        # 2. Проверяем существование таблицы bookings
        cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'bookings')")
        table_exists = cursor.fetchone()[0]
        
        if table_exists:
            results.append("<br><strong>🔧 Сохраняем существующие данные...</strong>")
            
            try:
                # Создаем временную таблицу для сохранения данных
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS temp_backup (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(100),
                        school_name VARCHAR(200),
                        class_number VARCHAR(20),
                        class_profile VARCHAR(100),
                        excursion_date DATE,
                        contact_phone VARCHAR(20),
                        participants_count INTEGER,
                        booking_date TIMESTAMP,
                        additional_info TEXT,
                        status VARCHAR(20)
                    )
                ''')
                
                # Копируем данные в бэкап
                cursor.execute('TRUNCATE TABLE temp_backup')
                
                try:
                    cursor.execute('''
                        INSERT INTO temp_backup 
                        (username, school_name, class_number, class_profile, 
                         excursion_date, contact_phone, participants_count, 
                         booking_date, additional_info, status)
                        SELECT 
                            username, 
                            school_name, 
                            class_number, 
                            COALESCE(class_profile, '') as class_profile,
                            excursion_date, 
                            contact_phone, 
                            participants_count, 
                            booking_date, 
                            COALESCE(additional_info, '') as additional_info,
                            COALESCE(status, 'pending') as status
                        FROM bookings
                    ''')
                    
                    backup_count = cursor.rowcount
                    results.append(f"   ✅ Сохранено {backup_count} записей в бэкап")
                except Exception as e:
                    results.append(f"   ⚠️  Ошибка бэкапа: {str(e)}")
                    backup_count = 0
                
            except Exception as e:
                results.append(f"   ⚠️  Не удалось создать бэкап: {str(e)}")
                backup_count = 0
        
        # 3. Удаляем старую таблицу и создаем новую
        results.append("<br><strong>🔧 Создаем новую структуру...</strong>")
        
        try:
            cursor.execute('DROP TABLE IF EXISTS bookings CASCADE')
            results.append("   ✅ Старая таблица удалена")
            
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
            
            results.append("   ✅ Новая таблица создана")
            
        except Exception as e:
            results.append(f"   ❌ Ошибка создания таблицы: {str(e)}")
            conn.rollback()
            return False, results
        
        # 4. Восстанавливаем данные из бэкапа если они есть
        if 'backup_count' in locals() and backup_count > 0:
            results.append("<br><strong>🔧 Восстанавливаем данные из бэкапа...</strong>")
            
            try:
                cursor.execute('''
                    INSERT INTO bookings 
                    (username, school_name, class_number, class_profile, 
                     excursion_date, contact_phone, participants_count, 
                     booking_date, additional_info, status)
                    SELECT 
                        COALESCE(username, 'Не указано'),
                        COALESCE(school_name, 'Не указано'),
                        COALESCE(class_number, 'Не указано'),
                        class_profile,
                        excursion_date,
                        COALESCE(contact_phone, 'Не указано'),
                        COALESCE(participants_count, 0),
                        COALESCE(booking_date, CURRENT_TIMESTAMP),
                        additional_info,
                        COALESCE(status, 'pending')
                    FROM temp_backup
                ''')
                
                restored_count = cursor.rowcount
                results.append(f"   ✅ Восстановлено {restored_count} записей")
                
            except Exception as e:
                results.append(f"   ⚠️  Ошибка восстановления: {str(e)}")
        
        # 5. Удаляем временную таблицу
        try:
            cursor.execute('DROP TABLE IF EXISTS temp_backup')
            results.append("   ✅ Временная таблица удалена")
        except:
            pass
        
        # 6. Создаем таблицу blocked_dates если её нет
        results.append("<br><strong>🔧 Создаем таблицу blocked_dates...</strong>")
        try:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = 'blocked_dates'
                )
            """)
            
            if not cursor.fetchone()[0]:
                cursor.execute('''
                    CREATE TABLE blocked_dates (
                        id SERIAL PRIMARY KEY,
                        blocked_date DATE NOT NULL UNIQUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                results.append("   ✅ Таблица blocked_dates создана")
            else:
                results.append("   ✅ Таблица blocked_dates уже существует")
                
        except Exception as e:
            results.append(f"   ⚠️  Ошибка создания blocked_dates: {str(e)}")
        
        # 7. Создаем индексы
        results.append("<br><strong>🔧 Создаем индексы...</strong>")
        try:
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(excursion_date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_bookings_school ON bookings(school_name)')
            results.append("   ✅ Индексы созданы")
        except Exception as e:
            results.append(f"   ⚠️  Ошибка создания индексов: {str(e)}")
        
        # 8. Финальная проверка
        results.append("<br><strong>📊 Финальная структура базы:</strong>")
        
        cursor.execute("SELECT COUNT(*) FROM bookings")
        count = cursor.fetchone()[0]
        results.append(f"   📊 Всего записей в bookings: {count}")
        
        cursor.execute("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'bookings'
            ORDER BY ordinal_position
        """)
        
        columns = cursor.fetchall()
        for col in columns:
            results.append(f"   - {col[0]} ({col[1]}) {'NULL' if col[2] == 'YES' else 'NOT NULL'}")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        results.append("<br><strong style='color: #2ecc71;'>✅ МЯГКОЕ ИСПРАВЛЕНИЕ ВЫПОЛНЕНО!</strong>")
        
        return True, results
        
    except Exception as e:
        return False, [f"❌ Критическая ошибка: {str(e)}"]