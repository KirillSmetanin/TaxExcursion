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
    """Миграция базы данных - добавляем недостающие колонки"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        print("🔍 Проверяем структуру таблицы bookings...")
        
        # Проверяем существующие колонки
        cursor.execute("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'bookings'
            ORDER BY ordinal_position
        """)
        
        columns = cursor.fetchall()
        print(f"📊 Найдено колонок: {len(columns)}")
        for col in columns:
            print(f"  - {col[0]} ({col[1]}) {'NULL' if col[2] == 'YES' else 'NOT NULL'}")
        
        # Проверяем нужные колонки
        required_columns = ['status', 'additional_info']
        existing_columns = [col[0] for col in columns]
        
        # Добавляем недостающие колонки
        for column in required_columns:
            if column not in existing_columns:
                print(f"➕ Добавляем колонку '{column}'...")
                
                if column == 'status':
                    cursor.execute(f'''
                        ALTER TABLE bookings 
                        ADD COLUMN {column} VARCHAR(20) DEFAULT 'pending'
                    ''')
                elif column == 'additional_info':
                    cursor.execute(f'''
                        ALTER TABLE bookings 
                        ADD COLUMN {column} TEXT
                    ''')
                
                print(f"✅ Колонка '{column}' добавлена")
        
        # Проверяем данные в существующих записях
        cursor.execute("SELECT COUNT(*) FROM bookings")
        total = cursor.fetchone()[0]
        print(f"\n📊 Всего записей в базе: {total}")
        
        if total > 0:
            cursor.execute("SELECT COUNT(*) FROM bookings WHERE status IS NULL")
            null_status = cursor.fetchone()[0]
            
            if null_status > 0:
                print(f"🔄 Устанавливаем status='pending' для {null_status} записей...")
                cursor.execute("UPDATE bookings SET status = 'pending' WHERE status IS NULL")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("\n🎉 Миграция успешно завершена!")
        
    except Exception as e:
        print(f"❌ Ошибка миграции: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    print("🚀 Запуск миграции базы данных...")
    migrate_database()