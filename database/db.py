import asyncpg
import logging
import os
from config import Config

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.pool = None

    async def init_pool(self, dsn: str):
        self.pool = await asyncpg.create_pool(dsn, min_size=1, max_size=10)
        await self._create_tables()
        logger.info("База данных инициализирована")

    async def _create_tables(self):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    gender TEXT,
                    agreed_to_offer BOOLEAN DEFAULT FALSE,
                    tokens INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_photos (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                    file_id TEXT,
                    file_path TEXT,
                    type TEXT,
                    uploaded_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_selected_style (
                    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                    style_key TEXT
                )
            ''')
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    label TEXT PRIMARY KEY,
                    user_id BIGINT,
                    amount INT,
                    payment_id TEXT,
                    data JSONB,
                    processed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            logger.info("Таблицы созданы/проверены")

    # ---------- Users ----------
    async def get_or_create_user(self, user_id: int, username: str = None, first_name: str = None):
        async with self.pool.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            if not user:
                await conn.execute(
                    "INSERT INTO users (user_id, username, first_name) VALUES ($1, $2, $3)",
                    user_id, username, first_name
                )
                return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            return user

    async def set_user_gender(self, user_id: int, gender: str):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE users SET gender = $1 WHERE user_id = $2", gender, user_id)

    async def get_user_gender(self, user_id: int) -> str:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT gender FROM users WHERE user_id = $1", user_id)
            return row['gender'] if row else None

    async def set_user_agreed_to_offer(self, user_id: int, agreed: bool):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE users SET agreed_to_offer = $1 WHERE user_id = $2", agreed, user_id)

    async def get_user_agreed_to_offer(self, user_id: int) -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT agreed_to_offer FROM users WHERE user_id = $1", user_id)
            return row['agreed_to_offer'] if row else False

    async def get_user_tokens(self, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT tokens FROM users WHERE user_id = $1", user_id)
            return row['tokens'] if row else 0

    async def add_tokens(self, user_id: int, amount: int):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE users SET tokens = tokens + $1 WHERE user_id = $2", amount, user_id)

    async def use_tokens(self, user_id: int, cost: int) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("SELECT tokens FROM users WHERE user_id = $1 FOR UPDATE", user_id)
                if row and row['tokens'] >= cost:
                    await conn.execute("UPDATE users SET tokens = tokens - $1 WHERE user_id = $2", cost, user_id)
                    return True
                return False

    # ---------- Photos ----------
    async def add_photo(self, user_id: int, file_id: str, file_path: str, type_: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO user_photos (user_id, file_id, file_path, type) VALUES ($1, $2, $3, $4)",
                user_id, file_id, file_path, type_
            )

    async def get_user_photos(self, user_id: int, type_: str = "input") -> list:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT file_path FROM user_photos WHERE user_id = $1 AND type = $2 ORDER BY id",
                user_id, type_
            )
            return [row['file_path'] for row in rows]

    async def get_user_photo_count(self, user_id: int, type_: str = "input") -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) FROM user_photos WHERE user_id = $1 AND type = $2",
                user_id, type_
            )
            return row[0] if row else 0

    async def delete_user_photos(self, user_id: int, type_: str = "input"):
        # Сначала удаляем физические файлы
        photos = await self.get_user_photos(user_id, type_)
        for path in photos:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.warning(f"Не удалось удалить файл {path}: {e}")
        # Удаляем записи из БД
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM user_photos WHERE user_id = $1 AND type = $2",
                user_id, type_
            )

    async def set_user_selected_style(self, user_id: int, style_key: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO user_selected_style (user_id, style_key) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET style_key = $2",
                user_id, style_key
            )

    async def get_user_selected_style(self, user_id: int) -> str:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT style_key FROM user_selected_style WHERE user_id = $1", user_id)
            return row['style_key'] if row else None

    # ---------- Orders ----------
    async def create_order(self, user_id: int, label: str, amount: int, data: dict):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO orders (label, user_id, amount, data) VALUES ($1, $2, $3, $4)",
                label, user_id, amount, data
            )

    async def update_order_payment_id(self, label: str, payment_id: str):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE orders SET payment_id = $1 WHERE label = $2", payment_id, label)

    async def get_order_data(self, label: str) -> dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT data FROM orders WHERE label = $1", label)
            return row['data'] if row else None

    async def mark_order_processed(self, label: str):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE orders SET processed = TRUE WHERE label = $1", label)

    async def is_order_processed(self, label: str) -> bool:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT processed FROM orders WHERE label = $1", label)
            return row['processed'] if row else False

    async def get_payment_id_by_label(self, label: str) -> str:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT payment_id FROM orders WHERE label = $1", label)
            return row['payment_id'] if row else None

    # ---------- НОВЫЙ МЕТОД ОЧИСТКИ (Вариант 3) ----------
    async def clean_missing_photo_records(self) -> int:
        """
        Удаляет из таблицы user_photos записи, для которых файл не существует на диске.
        Возвращает количество удалённых записей.
        """
        deleted = 0
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, file_path FROM user_photos WHERE type = 'input'")
            for row in rows:
                if not os.path.exists(row['file_path']):
                    await conn.execute("DELETE FROM user_photos WHERE id = $1", row['id'])
                    deleted += 1
                    logger.warning(f"Удалена запись о фото {row['id']} (файл отсутствует: {row['file_path']})")
        if deleted:
            logger.info(f"Очистка БД: удалено {deleted} записей о несуществующих фото")
        return deleted

# Глобальный экземпляр
_db_instance = None

async def get_db() -> Database:
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
        await _db_instance.init_pool(Config.DATABASE_URL)
    return _db_instance