import logging
import asyncio
import sys
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from groq import AsyncGroq
import sqlite3

# ============================================================
# ⚙️  НАСТРОЙКИ
# ============================================================

TELEGRAM_TOKEN = "ВСТАВЬ_ТОКЕН"       # ← @BotFather
GROQ_API_KEY   = "ВСТАВЬ_GROQ_КЛЮЧ"  # ← console.groq.com
ADMIN_ID       = 1693113909           # ваш Telegram ID
DB_PATH        = "bot_database.db"

BOT_PERSONALITY = (
    "Ты — Гена Валет, дерзкий, умный и харизматичный AI-персонаж. "
    "Твой стиль общения: краткий, с юмором, иногда с сарказмом, но всегда по делу."
)

LIMITS = {
    "free":          10,
    "premium_month": 1000,
    "premium_year":  10000,
}

# ============================================================
# ЛОГИРОВАНИЕ
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ============================================================
# ГЛОБАЛЬНЫЕ ОБЪЕКТЫ
# ============================================================

dp          = Dispatcher()
groq_client = AsyncGroq(api_key=GROQ_API_KEY)

# ============================================================
# БАЗА ДАННЫХ
# ============================================================

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id       INTEGER UNIQUE NOT NULL,
            username          TEXT,
            first_name        TEXT,
            subscription_type TEXT DEFAULT 'free',
            subscription_end  TEXT,
            messages_today    INTEGER DEFAULT 0,
            last_message_date TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER,
            role      TEXT,
            content   TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    logger.info("✅ База данных готова")

# ============================================================
# МОДЕЛЬ ПОЛЬЗОВАТЕЛЯ
# ============================================================

class User:
    def __init__(self, telegram_id, username, first_name,
                 subscription_type="free", subscription_end=None,
                 messages_today=0, last_message_date=None, **_):
        self.telegram_id       = telegram_id
        self.username          = username
        self.first_name        = first_name
        self.subscription_type = subscription_type
        self.subscription_end  = subscription_end
        self.messages_today    = messages_today
        self.last_message_date = last_message_date

    @staticmethod
    def get_or_create(tg_id: int, username: str, first_name: str) -> "User":
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("SELECT * FROM users WHERE telegram_id = ?", (tg_id,))
        row = cur.fetchone()
        if not row:
            cur.execute(
                "INSERT INTO users (telegram_id, username, first_name) VALUES (?, ?, ?)",
                (tg_id, username, first_name),
            )
            conn.commit()
            cur.execute("SELECT * FROM users WHERE telegram_id = ?", (tg_id,))
            row = cur.fetchone()
        conn.close()
        return User(**dict(row))

    def save(self):
        conn = get_conn()
        conn.execute(
            """UPDATE users
               SET username=?, first_name=?, subscription_type=?,
                   subscription_end=?, messages_today=?, last_message_date=?
               WHERE telegram_id=?""",
            (self.username, self.first_name, self.subscription_type,
             self.subscription_end, self.messages_today,
             self.last_message_date, self.telegram_id),
        )
        conn.commit()
        conn.close()

    def can_send_message(self) -> bool:
        today = str(datetime.now().date())
        if self.last_message_date != today:
            self.messages_today    = 0
            self.last_message_date = today
            self.save()

        if self.subscription_type != "free" and self.subscription_end:
            try:
                if datetime.fromisoformat(self.subscription_end).date() < datetime.now().date():
                    self.subscription_type = "free"
                    self.subscription_end  = None
                    self.save()
            except Exception:
                pass

        return self.messages_today < self.daily_limit

    def increment(self):
        self.messages_today += 1
        self.save()

    @property
    def daily_limit(self) -> int:
        return LIMITS.get(self.subscription_type, 10)

# ============================================================
# ИСТОРИЯ СООБЩЕНИЙ
# ============================================================

def save_message(user_id: int, role: str, content: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
        (user_id, role, content),
    )
    conn.commit()
    conn.close()


def get_history(user_id: int, limit: int = 10) -> list:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(
        "SELECT role, content FROM messages WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
        (user_id, limit),
    )
    rows = cur.fetchall()
    conn.close()
    # Groq/OpenAI формат: [{"role": "user"/"assistant", "content": "текст"}]
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

# ============================================================
# ВЫЗОВ GROQ
# ============================================================

async def ask_groq(user_id: int, user_text: str) -> str:
    history = get_history(user_id, limit=10)
    messages = (
        [{"role": "system", "content": BOT_PERSONALITY}]
        + history
        + [{"role": "user", "content": user_text}]
    )
    response = await groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=1000,
    )
    return response.choices[0].message.content

# ============================================================
# КЛАВИАТУРЫ
# ============================================================

def main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💬 Чат с ИИ")],
            [KeyboardButton(text="👤 Мой профиль"), KeyboardButton(text="💎 Подписка")],
            [KeyboardButton(text="ℹ️ О проекте")],
        ],
        resize_keyboard=True,
    )


def sub_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Месяц — 299₽",  callback_data="sub_month")],
        [InlineKeyboardButton(text="📅 Год — 2490₽",   callback_data="sub_year")],
        [InlineKeyboardButton(text="❌ Отмена",          callback_data="sub_cancel")],
    ])

# ============================================================
# ОБРАБОТЧИКИ
# ============================================================

MENU_BUTTONS = {"💬 Чат с ИИ", "👤 Мой профиль", "💎 Подписка", "ℹ️ О проекте"}


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user = User.get_or_create(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or "",
    )
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}! Я — Гена Валет, твой личный ИИ.\n\n"
        f"🎁 Тебе доступно <b>{user.daily_limit}</b> сообщений в день.\n"
        f"Просто напиши мне что-нибудь 👇",
        reply_markup=main_kb(),
    )


@dp.message(F.text == "💬 Чат с ИИ")
async def handle_chat_button(message: types.Message):
    await message.answer("Напиши мне всё что нужно — отвечу!", reply_markup=main_kb())


@dp.message(F.text == "👤 Мой профиль")
async def handle_profile(message: types.Message):
    user = User.get_or_create(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or "",
    )
    status    = "🟢 Premium" if user.subscription_type != "free" else "⚪️ Free"
    left      = max(0, user.daily_limit - user.messages_today)
    sub_until = f"\n📅 До: <b>{user.subscription_end}</b>" if user.subscription_end else ""
    await message.answer(
        f"👤 <b>Профиль</b>\n"
        f"🆔 ID: <code>{user.telegram_id}</code>\n"
        f"📊 Статус: {status}{sub_until}\n"
        f"💬 Сообщений сегодня: {user.messages_today} / {user.daily_limit}\n"
        f"📨 Осталось: {left}",
        reply_markup=main_kb(),
    )


@dp.message(F.text == "💎 Подписка")
async def handle_subscription(message: types.Message):
    await message.answer(
        "💎 <b>Планы подписки:</b>\n\n"
        "📅 <b>Месяц</b> — 1 000 сообщ./день — 299₽\n"
        "📅 <b>Год</b>   — 10 000 сообщ./день — 2490₽\n\n"
        "Выбери подходящий 👇",
        reply_markup=sub_kb(),
    )


@dp.message(F.text == "ℹ️ О проекте")
async def handle_about(message: types.Message):
    await message.answer(
        "ℹ️ <b>PERSONAL</b> — твой личный AI-помощник на базе Llama 3.3.\n\n"
        "Задавай любые вопросы — отвечу по делу 😎",
        reply_markup=main_kb(),
    )


@dp.message(F.text & ~F.text.in_(MENU_BUTTONS))
async def handle_text(message: types.Message):
    user = User.get_or_create(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or "",
    )

    if not user.can_send_message():
        await message.answer(
            f"⛔️ Лимит исчерпан ({user.daily_limit} сообщ./день).\n"
            "Оформи подписку 👇",
            reply_markup=sub_kb(),
        )
        return

    await message.bot.send_chat_action(message.chat.id, "typing")

    try:
        ai_text = await ask_groq(user.telegram_id, message.text)

        save_message(user.telegram_id, "user",      message.text)
        save_message(user.telegram_id, "assistant", ai_text)
        user.increment()

        left = user.daily_limit - user.messages_today
        await message.answer(
            f"{ai_text}\n\n<i>Осталось сообщений сегодня: {left}</i>",
            reply_markup=main_kb(),
        )

    except Exception as e:
        logger.error(f"Groq error: {e}")
        await message.answer("😅 Что-то пошло не так, попробуй ещё раз.")


@dp.callback_query(F.data.startswith("sub_"))
async def sub_handler(callback: types.CallbackQuery):
    if callback.data == "sub_cancel":
        await callback.message.delete()
        return
    await callback.answer("💳 Оплата в разработке — скоро!", show_alert=True)


def activate_subscription(telegram_id: int, plan: str):
    from datetime import timedelta
    user = User.get_or_create(telegram_id, "", "")
    user.subscription_type = f"premium_{plan}"
    days = 30 if plan == "month" else 365
    user.subscription_end = str((datetime.now() + timedelta(days=days)).date())
    user.save()

# ============================================================
# ADMIN КОМАНДЫ
# ============================================================

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM users")
    total = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) as cnt FROM users WHERE subscription_type != 'free'")
    premium = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) as cnt FROM messages")
    msgs = cur.fetchone()["cnt"]
    conn.close()
    await message.answer(
        f"📊 <b>Статистика</b>\n"
        f"👥 Пользователей: {total}\n"
        f"💎 Premium: {premium}\n"
        f"💬 Сообщений всего: {msgs}"
    )


@dp.message(Command("give_premium"))
async def cmd_give_premium(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("Формат: /give_premium <user_id> <month|year>")
        return
    try:
        uid  = int(parts[1])
        plan = parts[2]
        if plan not in ("month", "year"):
            raise ValueError
        activate_subscription(uid, plan)
        await message.answer(f"✅ Premium ({plan}) выдан пользователю {uid}")
    except Exception:
        await message.answer("❌ Ошибка. Проверь формат команды.")

# ============================================================
# ЗАПУСК
# ============================================================

async def main():
    if "ВСТАВЬ" in TELEGRAM_TOKEN:
        logger.error("❌ Укажите TELEGRAM_TOKEN в коде!")
        sys.exit(1)
    if "ВСТАВЬ" in GROQ_API_KEY:
        logger.error("❌ Укажите GROQ_API_KEY в коде!")
        sys.exit(1)

    init_db()

    bot = Bot(
        token=TELEGRAM_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    logger.info("🃏 Гена Валет запущен!")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        logger.info("🛑 Бот остановлен")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
