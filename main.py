import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import database as db

# Твои реальные данные:
BOT_TOKEN = "8890981994:AAHZ8oyHPzXdfy_go2l0uvApZA1eeVib9bE"
MANAGER_CHAT_ID = -1003974836099  

bot = Bot(token='8890981994:AAH9Q7zQypfJp1s3Zts6ejeuvb0vlLqkbVo')
dp = Dispatcher()

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else "Нет никнейма"
    first_name = message.from_user.first_name
    
    args = message.text.split()
    referrer_id = None
    source_tag = "Прямой переход (Органика)"
    
    if len(args) > 1:
        param = args[1]
        if param.isdigit():
            referrer_id = int(param)
            source_tag = f"Реферал от Юзера ID {referrer_id}"
        else:
            source_tag = f"Источник: {param}"

    is_new = db.add_new_user(user_id, username, first_name, referrer_id, source_tag)
    
    if is_new:
        manager_text = (
            f"🎯 Новый запуск бота AI!\n\n"
            f"👤 Имя: {first_name}\n"
            f"🆔 Логин: {username} (ID: {user_id})\n"
            f"📢 Источник трафика: {source_tag}\n"
            f"🔗 Реф. ссылка юзера: t.me/API_valey_AI_BOT?start={user_id}"
        )
        try:
            await bot.send_message(chat_id=MANAGER_CHAT_ID, text=manager_text, parse_mode="Markdown")
        except Exception as e:
            print(f"Ошибка отправки лога в чат: {e}")

    await message.answer(f"Здорово, {first_name}! Я твой персональный AI. 🤖\n\nВыдал тебе 5 бесплатных токенов. Пиши любой вопрос — раскидаю всё по фактам.\n\nПосмотреть баланс: /balance")

@dp.message(Command("balance"))
async def cmd_balance(message: types.Message):
    tokens = db.get_tokens(message.from_user.id)
    await message.answer(f"Твой баланс: {tokens} токенов. 🪙")

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    total = db.get_stats()
    await message.answer(f"📊 Админ-панель AI:\n\nВсего уникальных пользователей в базе: {total[0] if isinstance(total, tuple) else total}")

@dp.message(F.text)
async def chat_logic(message: types.Message):
    user_id = message.from_user.id
    tokens = db.get_tokens(user_id)
    
    if tokens <= 0:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Купить 50 токенов (99 руб)", callback_data="pay_99")],
            [InlineKeyboardButton(text="💎 Безлимит на месяц (499 руб)", callback_data="pay_499")]
        ])
        await message.answer("Халява кончилась, токены на нуле. \nЧтобы продолжить общение, нужно пополнить баланс AI через воронку продаж:", reply_markup=kb)
        return

    db.use_token(user_id)
    await message.answer(f" AI проанализировал вопрос '{message.text}' и выдал вердикт: Работать надо, а не ерундой страдать! (Осталось токенов: {tokens-1})")

@dp.callback_query(F.data.startswith("pay_"))
async def process_payment(callback: types.CallbackQuery):
    await callback.message.answer("💳 Демонстрация оплаты: Платеж успешно зачислен! Токены начислены, продолжаем сессию. 😎")
    await callback.answer()

async def main():
    db.init_db()
    print("🚀 Тестовый бот AI успешно запущен и слушает команды!")
    await dp.start_polling(bot)

if __name__ == "main":
    asyncio.run(main())