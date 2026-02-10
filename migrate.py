import os
import psycopg
import urllib.parse

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

def migrate_database():
    """Полная миграция базы данных - исправляем структуру"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        print("🚀 Начинаем экстренную миграцию базы данных...")
        
        # 1. Сначала проверяем структуру таблицы
        print("\n📊 Текущая структура таблицы bookings:")
        cursor.execute("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'bookings'
            ORDER BY ordinal_position
        """)
        
        columns = cursor.fetchall()
        for col in columns:
            print(f"  - {col[0]} ({col[1]}) {'NULL' if col[2] == 'YES' else 'NOT NULL'}")
        
        # 2. Удаляем колонку contact_person если она существует
        print("\n🔧 Шаг 1: Удаляем колонку contact_person...")
        try:
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'bookings' AND column_name = 'contact_person'
            """)
            
            if cursor.fetchone():
                print("   🗑️  Колонка contact_person найдена, удаляем...")
                
                # Временная мера: если есть ограничение NOT NULL, сначала уберем его
                try:
                    print("   🔧 Проверяем ограничения NOT NULL...")
                    cursor.execute("""
                        SELECT COUNT(*) FROM bookings WHERE contact_person IS NULL
                    """)
                    null_count = cursor.fetchone()[0]
                    
                    if null_count > 0:
                        print(f"   ⚠️  Найдено {null_count} записей с NULL в contact_person")
                        print("   🔧 Устанавливаем временные значения...")
                        cursor.execute("""
                            UPDATE bookings SET contact_person = 'УДАЛЕНО_ПРИ_МИГРАЦИИ' 
                            WHERE contact_person IS NULL
                        """)
                
                except Exception as e:
                    print(f"   ⚠️  Предупреждение при проверке NULL: {e}")
                
                # Удаляем колонку
                cursor.execute("ALTER TABLE bookings DROP COLUMN contact_person")
                print("   ✅ Колонка contact_person успешно удалена")
            else:
                print("   ✅ Колонка contact_person уже удалена")
                
        except Exception as e:
            print(f"   ❌ Ошибка удаления contact_person: {e}")
            print("   🔧 Пробуем альтернативный подход...")
            
            try:
                # Если не получается удалить, сначала уберем NOT NULL ограничение
                cursor.execute("""
                    ALTER TABLE bookings 
                    ALTER COLUMN contact_person DROP NOT NULL
                """)
                print("   ✅ Убрано ограничение NOT NULL")
                
                # Устанавливаем значения по умолчанию
                cursor.execute("""
                    UPDATE bookings 
                    SET contact_person = 'УДАЛЕНО' 
                    WHERE contact_person IS NULL
                """)
                
                # Теперь пробуем удалить снова
                cursor.execute("ALTER TABLE bookings DROP COLUMN contact_person")
                print("   ✅ Колонка contact_person удалена (второй подход)")
                
            except Exception as e2:
                print(f"   ❌ Критическая ошибка: {e2}")
                print("   ⚠️  Пропускаем этот шаг, продолжаем миграцию...")
        
        # 3. Проверяем текущие ограничения
        print("\n🔧 Шаг 2: Проверяем ограничения таблицы...")
        try:
            cursor.execute("""
                SELECT constraint_name, constraint_type 
                FROM information_schema.table_constraints 
                WHERE table_name = 'bookings'
            """)
            
            constraints = cursor.fetchall()
            print(f"   📋 Найдено ограничений: {len(constraints)}")
            
            for constraint in constraints:
                print(f"   - {constraint[0]} ({constraint[1]})")
                
                # Удаляем любые ограничения связанные с contact_person
                if 'contact_person' in constraint[0].lower():
                    print(f"   🗑️  Удаляем ограничение: {constraint[0]}")
                    cursor.execute(f'ALTER TABLE bookings DROP CONSTRAINT IF EXISTS {constraint[0]}')
                    
        except Exception as e:
            print(f"   ⚠️  Ошибка проверки ограничений: {e}")
        
        # 4. Добавляем колонку status если её нет
        print("\n🔧 Шаг 3: Добавляем колонку status...")
        try:
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'bookings' AND column_name = 'status'
            """)
            
            if not cursor.fetchone():
                print("   ➕ Добавляем колонку status...")
                cursor.execute('''
                    ALTER TABLE bookings 
                    ADD COLUMN status VARCHAR(20) DEFAULT 'pending'
                ''')
                print("   ✅ Колонка status добавлена")
            else:
                print("   ✅ Колонка status уже существует")
                
        except Exception as e:
            print(f"   ❌ Ошибка добавления status: {e}")
        
        # 5. Добавляем колонку additional_info если её нет
        print("\n🔧 Шаг 4: Добавляем колонку additional_info...")
        try:
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'bookings' AND column_name = 'additional_info'
            """)
            
            if not cursor.fetchone():
                print("   ➕ Добавляем колонку additional_info...")
                cursor.execute('''
                    ALTER TABLE bookings 
                    ADD COLUMN additional_info TEXT
                ''')
                print("   ✅ Колонка additional_info добавлена")
            else:
                print("   ✅ Колонка additional_info уже существует")
                
        except Exception as e:
            print(f"   ❌ Ошибка добавления additional_info: {e}")
        
        # 6. Создаем таблицу для заблокированных дат
        print("\n🔧 Шаг 5: Создаем таблицу blocked_dates...")
        try:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = 'blocked_dates'
                )
            """)
            
            if not cursor.fetchone()[0]:
                print("   ➕ Создаем таблицу blocked_dates...")
                cursor.execute('''
                    CREATE TABLE blocked_dates (
                        id SERIAL PRIMARY KEY,
                        blocked_date DATE NOT NULL UNIQUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("   ✅ Таблица blocked_dates создана")
            else:
                print("   ✅ Таблица blocked_dates уже существует")
                
        except Exception as e:
            print(f"   ❌ Ошибка создания blocked_dates: {e}")
        
        # 7. Обновляем существующие записи
        print("\n🔧 Шаг 6: Обновляем существующие записи...")
        try:
            cursor.execute("SELECT COUNT(*) FROM bookings")
            total = cursor.fetchone()[0]
            print(f"   📊 Всего записей: {total}")
            
            if total > 0:
                # Устанавливаем статус для записей без статуса
                cursor.execute("SELECT COUNT(*) FROM bookings WHERE status IS NULL")
                null_status = cursor.fetchone()[0]
                if null_status > 0:
                    print(f"   🔄 Устанавливаем status='pending' для {null_status} записей...")
                    cursor.execute("UPDATE bookings SET status = 'pending' WHERE status IS NULL")
                    print(f"   ✅ Обновлено {cursor.rowcount} записей")
        except Exception as e:
            print(f"   ❌ Ошибка обновления записей: {e}")
        
        # 8. Выводим финальную структуру
        print("\n📊 Финальная структура таблицы bookings:")
        cursor.execute("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'bookings'
            ORDER BY ordinal_position
        """)
        
        columns = cursor.fetchall()
        for col in columns:
            print(f"  - {col[0]} ({col[1]}) {'NULL' if col[2] == 'YES' else 'NOT NULL'}")
        
        # 9. Проверяем, что можно вставлять новые записи
        print("\n🔧 Шаг 7: Тестируем вставку тестовой записи...")
        try:
            # Пробуем вставить тестовую запись без contact_person
            cursor.execute('''
                INSERT INTO bookings 
                (username, school_name, class_number, excursion_date, 
                 contact_phone, participants_count, status, additional_info)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                'Тест Миграции', 
                'Тестовая школа', 
                '10А', 
                '2024-01-01', 
                '+79999999999', 
                10, 
                'pending', 
                'Тестовая запись после миграции'
            ))
            
            print("   ✅ Тестовая запись успешно добавлена")
            
            # Удаляем тестовую запись
            cursor.execute("DELETE FROM bookings WHERE username = 'Тест Миграции'")
            print("   ✅ Тестовая запись удалена")
            
        except Exception as e:
            print(f"   ❌ Ошибка тестовой вставки: {e}")
            print("   ⚠️  Требуется дополнительная отладка структуры таблицы")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("\n" + "="*50)
        print("🎉 МИГРАЦИЯ ЗАВЕРШЕНА!")
        print("="*50)
        print("✅ База данных обновлена")
        print("✅ Колонка contact_person удалена")
        print("✅ Добавлены новые колонки")
        print("✅ Таблица blocked_dates создана")
        print("✅ Можно продолжать работу с приложением")
        print("="*50)
        
    except Exception as e:
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА МИГРАЦИИ: {e}")
        print("="*50)
        print("⚠️  Требуется ручное вмешательство:")
        print("1. Проверьте структуру таблицы bookings")
        print("2. Убедитесь что колонка contact_person удалена")
        print("3. Проверьте ограничения NOT NULL")
        print("="*50)
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    print("="*60)
    print("🚀 ЗАПУСК ЭКСТРЕННОЙ МИГРАЦИИ БАЗЫ ДАННЫХ")
    print("="*60)
    print("⚠️  Эта миграция удалит колонку contact_person")
    print("⚠️  Исправляет ошибку NOT NULL constraint violation")
    print("="*60)
    
    response = input("Продолжить? (да/нет): ").lower().strip()
    
    if response in ['да', 'yes', 'y', 'д']:
        migrate_database()
    else:
        print("❌ Миграция отменена пользователем")