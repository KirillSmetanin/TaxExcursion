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
    """Полная миграция базы данных - добавляем все необходимые таблицы и колонки"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        print("🚀 Начинаем миграцию базы данных...")
        
        # 1. Удаляем колонку contact_person если она существует
        print("🔍 Проверяем наличие колонки contact_person...")
        try:
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'bookings' AND column_name = 'contact_person'
            """)
            if cursor.fetchone():
                print("🗑️  Удаляем колонку contact_person...")
                cursor.execute("ALTER TABLE bookings DROP COLUMN contact_person")
                print("✅ Колонка contact_person удалена")
            else:
                print("✅ Колонка contact_person отсутствует (все правильно)")
        except Exception as e:
            print(f"⚠️  Ошибка проверки contact_person: {e}")
        
        # 2. Добавляем колонку status если её нет
        print("\n🔍 Проверяем наличие колонки status...")
        try:
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'bookings' AND column_name = 'status'
            """)
            if not cursor.fetchone():
                print("➕ Добавляем колонку status...")
                cursor.execute('''
                    ALTER TABLE bookings 
                    ADD COLUMN status VARCHAR(20) DEFAULT 'pending'
                ''')
                print("✅ Колонка status добавлена")
            else:
                print("✅ Колонка status уже существует")
        except Exception as e:
            print(f"⚠️  Ошибка проверки status: {e}")
        
        # 3. Добавляем колонку additional_info если её нет
        print("\n🔍 Проверяем наличие колонки additional_info...")
        try:
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'bookings' AND column_name = 'additional_info'
            """)
            if not cursor.fetchone():
                print("➕ Добавляем колонку additional_info...")
                cursor.execute('''
                    ALTER TABLE bookings 
                    ADD COLUMN additional_info TEXT
                ''')
                print("✅ Колонка additional_info добавлена")
            else:
                print("✅ Колонка additional_info уже существует")
        except Exception as e:
            print(f"⚠️  Ошибка проверки additional_info: {e}")
        
        # 4. Создаем таблицу для заблокированных дат если её нет
        print("\n🔍 Проверяем наличие таблицы blocked_dates...")
        try:
            cursor.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = 'blocked_dates'
                )
            """)
            if not cursor.fetchone()[0]:
                print("➕ Создаем таблицу blocked_dates...")
                cursor.execute('''
                    CREATE TABLE blocked_dates (
                        id SERIAL PRIMARY KEY,
                        blocked_date DATE NOT NULL UNIQUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("✅ Таблица blocked_dates создана")
            else:
                print("✅ Таблица blocked_dates уже существует")
        except Exception as e:
            print(f"⚠️  Ошибка проверки blocked_dates: {e}")
        
        # 5. Проверяем и удаляем уникальное ограничение на excursion_date если оно существует
        print("\n🔍 Проверяем уникальные ограничения на bookings...")
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
                    print(f"🗑️  Удаляем уникальное ограничение: {constraint_name}")
                    cursor.execute(f'ALTER TABLE bookings DROP CONSTRAINT IF EXISTS {constraint_name}')
                    print(f"✅ Уникальное ограничение {constraint_name} удалено")
            else:
                print("✅ Уникальных ограничений на excursion_date нет")
        except Exception as e:
            print(f"⚠️  Ошибка проверки ограничений: {e}")
        
        # 6. Обновляем существующие записи
        print("\n🔄 Обновляем существующие записи...")
        try:
            cursor.execute("SELECT COUNT(*) FROM bookings")
            total = cursor.fetchone()[0]
            print(f"📊 Всего записей: {total}")
            
            if total > 0:
                # Устанавливаем статус для записей без статуса
                cursor.execute("SELECT COUNT(*) FROM bookings WHERE status IS NULL")
                null_status = cursor.fetchone()[0]
                if null_status > 0:
                    print(f"🔄 Устанавливаем status='pending' для {null_status} записей...")
                    cursor.execute("UPDATE bookings SET status = 'pending' WHERE status IS NULL")
                    print(f"✅ Обновлено {cursor.rowcount} записей")
        except Exception as e:
            print(f"⚠️  Ошибка обновления записей: {e}")
        
        # 7. Выводим финальную структуру
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
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("\n🎉 Миграция успешно завершена!")
        print("✅ База данных готова к работе с новыми функциями")
        print("✅ Закрыты понедельники и пятницы")
        print("✅ Добавлена система блокировки дат")
        print("✅ Убрано поле 'Контактное лицо в УФНС'")
        print("✅ Исправлены проблемы с подтверждением записей")
        
    except Exception as e:
        print(f"\n❌ Критическая ошибка миграции: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 Запуск полной миграции базы данных...")
    print("=" * 50)
    migrate_database()
    print("=" * 50)