from telegram import ReplyKeyboardMarkup, KeyboardButton, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from database.db import get_db
from config import Config
import logging

logger = logging.getLogger(__name__)

# Список всех текстов кнопок главного меню (для проверки в других модулях)
MAIN_MENU_BUTTONS = [
    "📤 Загрузить фото",
    "🖼️ Стили",
    "❓ Помощь",
    "🗑 Очистить селфи",
    "🏠 Главное меню",
    "💎 Мои жетоны"
]

def get_main_menu_keyboard():
    buttons = [
        [KeyboardButton("📤 Загрузить фото"), KeyboardButton("🖼️ Стили")],
        [KeyboardButton("💎 Мои жетоны"), KeyboardButton("❓ Помощь")],
        [KeyboardButton("🗑 Очистить селфи"), KeyboardButton("🏠 Главное меню")],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 *Главное меню*\n\nВыберите действие:",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

async def tokens_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = await get_db()
    tokens = await db.get_user_tokens(user_id)

    # Формируем текст с ценами пакетов из PACKAGE_MODELS
    flash = Config.PACKAGE_MODELS['flash']
    medium = Config.PACKAGE_MODELS['medium']
    high = Config.PACKAGE_MODELS['high']
    text = (
        f"💎 *Ваш баланс жетонов:* {tokens}\n\n"
        "💰 *Стоимость пакетов (8 фото):*\n"
        f"• {flash['name']} – {flash['price_tokens']} жетонов\n"
        f"• {medium['name']} – {medium['price_tokens']} жетонов\n"
        f"• {high['name']} – {high['price_tokens']} жетонов\n\n"
        "💎 Жетоны можно купить кнопкой ниже."
    )
    keyboard = [[InlineKeyboardButton("💎 Купить 20 жетонов за 700₽", callback_data="buy_tokens")]]
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Экспорт
menu_handler = CommandHandler("menu", menu_command)
tokens_handler = MessageHandler(filters.Text("💎 Мои жетоны"), tokens_info_command)