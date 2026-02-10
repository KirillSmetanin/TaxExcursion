# database_fix.py
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

def fix_database_operation():
    """Основная операция исправления базы данных"""
    results = []
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        results.append("<strong>🚀 Запуск полного исправления базы данных...</strong>")
        
        # 1. Проверяем текущую структуру
        results.append("<br><strong>📊 Текущая структура таблицы bookings:</strong>")
        cursor.execute("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'bookings'
            ORDER BY ordinal_position
        """)
        
        columns = cursor.fetchall()
        for col in columns:
            results.append(f"  - {col[0]} ({col[1]}) {'NULL' if col[2] == 'YES' else 'NOT NULL'}")
        
        # 2. Удаляем колонку contact_person если она существует
        results.append("<br><strong>🔧 Шаг 1: Удаляем колонку contact_person...</strong>")
        try:
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'bookings' AND column_name = 'contact_person'
            """)
            
            if cursor.fetchone():
                # Если есть записи с NULL в contact_person, устанавливаем значения по умолчанию
                cursor.execute("SELECT COUNT(*) FROM bookings WHERE contact_person IS NULL")
                null_count = cursor.fetchone()[0]
                
                if null_count > 0:
                    cursor.execute("UPDATE bookings SET contact_person = 'УДАЛЕНО_ПРИ_МИГРАЦИИ' WHERE contact_person IS NULL")
                    results.append(f"   ✅ Обновлено {null_count} записей с NULL значениями")
                
                # Удаляем колонку
                cursor.execute("ALTER TABLE bookings DROP COLUMN contact_person")
                results.append("   ✅ Колонка contact_person успешно удалена")
            else:
                results.append("   ✅ Колонка contact_person уже удалена")
                
        except Exception as e:
            results.append(f"   ❌ Ошибка удаления contact_person: {str(e)}")
            results.append("   🔧 Пробуем альтернативный подход...")
            
            try:
                # Если не получается удалить, убираем NOT NULL ограничение
                cursor.execute("ALTER TABLE bookings ALTER COLUMN contact_person DROP NOT NULL")
                results.append("   ✅ Убрано ограничение NOT NULL")
                
                # Устанавливаем значения по умолчанию
                cursor.execute("UPDATE bookings SET contact_person = 'УДАЛЕНО' WHERE contact_person IS NULL")
                results.append("   ✅ Установлены значения по умолчанию")
                
                # Пробуем снова
                cursor.execute("ALTER TABLE bookings DROP COLUMN contact_person")
                results.append("   ✅ Колонка contact_person удалена (второй подход)")
                
            except Exception as e2:
                results.append(f"   ❌ Критическая ошибка: {str(e2)}")
        
        # 3. Добавляем колонку status если её нет
        results.append("<br><strong>🔧 Шаг 2: Добавляем колонку status...</strong>")
        try:
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'bookings' AND column_name = 'status'
            """)
            
            if not cursor.fetchone():
                cursor.execute('''
                    ALTER TABLE bookings 
                    ADD COLUMN status VARCHAR(20) DEFAULT 'pending'
                ''')
                results.append("   ✅ Колонка status добавлена")
            else:
                results.append("   ✅ Колонка status уже существует")
                
        except Exception as e:
            results.append(f"   ❌ Ошибка добавления status: {str(e)}")
        
        # 4. Добавляем колонку additional_info если её нет
        results.append("<br><strong>🔧 Шаг 3: Добавляем колонку additional_info...</strong>")
        try:
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'bookings' AND column_name = 'additional_info'
            """)
            
            if not cursor.fetchone():
                cursor.execute('''
                    ALTER TABLE bookings 
                    ADD COLUMN additional_info TEXT
                ''')
                results.append("   ✅ Колонка additional_info добавлена")
            else:
                results.append("   ✅ Колонка additional_info уже существует")
                
        except Exception as e:
            results.append(f"   ❌ Ошибка добавления additional_info: {str(e)}")
        
        # 5. Создаем таблицу для заблокированных дат
        results.append("<br><strong>🔧 Шаг 4: Создаем таблицу blocked_dates...</strong>")
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
            results.append(f"   ❌ Ошибка создания blocked_dates: {str(e)}")
        
        # 6. Удаляем уникальные ограничения на excursion_date
        results.append("<br><strong>🔧 Шаг 5: Удаляем уникальные ограничения...</strong>")
        try:
            cursor.execute("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'bookings' 
                AND constraint_type = 'UNIQUE'
                AND constraint_name LIKE '%excursion_date%'
            """)
            
            unique_constraints = cursor.fetchall()
            if unique_constraints:
                for constraint in unique_constraints:
                    constraint_name = constraint[0]
                    try:
                        cursor.execute(f'ALTER TABLE bookings DROP CONSTRAINT IF EXISTS {constraint_name}')
                        results.append(f"   ✅ Удалено уникальное ограничение: {constraint_name}")
                    except Exception as e:
                        results.append(f"   ❌ Ошибка удаления {constraint_name}: {str(e)}")
            else:
                results.append("   ✅ Уникальных ограничений на excursion_date нет")
        except Exception as e:
            results.append(f"   ❌ Ошибка проверки ограничений: {str(e)}")
        
        # 7. Обновляем существующие записи
        results.append("<br><strong>🔧 Шаг 6: Обновляем существующие записи...</strong>")
        try:
            cursor.execute("SELECT COUNT(*) FROM bookings")
            total = cursor.fetchone()[0]
            results.append(f"   📊 Всего записей: {total}")
            
            if total > 0:
                # Устанавливаем статус для записей без статуса
                cursor.execute("SELECT COUNT(*) FROM bookings WHERE status IS NULL")
                null_status = cursor.fetchone()[0]
                if null_status > 0:
                    cursor.execute("UPDATE bookings SET status = 'pending' WHERE status IS NULL")
                    results.append(f"   ✅ Установлен status='pending' для {null_status} записей")
                    
                # Проверяем наличие записей с contact_person (на всякий случай)
                try:
                    cursor.execute("SELECT COUNT(*) FROM bookings WHERE contact_person IS NOT NULL")
                    has_contact_person = cursor.fetchone()[0]
                    if has_contact_person > 0:
                        results.append(f"   ⚠️  Обнаружено {has_contact_person} записей с contact_person")
                except:
                    pass
        except Exception as e:
            results.append(f"   ❌ Ошибка обновления записей: {str(e)}")
        
        # 8. Тестируем вставку
        results.append("<br><strong>🔧 Шаг 7: Тестируем вставку записи...</strong>")
        try:
            cursor.execute('''
                INSERT INTO bookings 
                (username, school_name, class_number, excursion_date, 
                 contact_phone, participants_count, status, additional_info)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                'Тест Исправления', 
                'Тестовая школа', 
                '10А', 
                '2024-01-01', 
                '+79999999999', 
                10, 
                'pending', 
                'Тестовая запись после исправления'
            ))
            
            results.append("   ✅ Тестовая запись успешно добавлена")
            
            # Удаляем тестовую запись
            cursor.execute("DELETE FROM bookings WHERE username = 'Тест Исправления'")
            results.append("   ✅ Тестовая запись удалена")
            
        except Exception as e:
            results.append(f"   ❌ Ошибка тестовой вставки: {str(e)}")
        
        # 9. Выводим финальную структуру
        results.append("<br><strong>📊 Финальная структура таблицы bookings:</strong>")
        cursor.execute("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'bookings'
            ORDER BY ordinal_position
        """)
        
        columns = cursor.fetchall()
        for col in columns:
            results.append(f"  - {col[0]} ({col[1]}) {'NULL' if col[2] == 'YES' else 'NOT NULL'}")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        # Возвращаем результаты
        return True, results
        
    except Exception as e:
        return False, [f"❌ Критическая ошибка: {str(e)}"]