import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from config import Config
from database.db import get_db
from services.aitunnel_service import AITunnelService
from utils.helpers import send_photo_or_fallback
from handlers.menu import get_main_menu_keyboard

logger = logging.getLogger(__name__)

async def single_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список стилей для одиночной генерации"""
    keyboard = []
    for key, style in Config.STYLES.items():
        keyboard.append([InlineKeyboardButton(style['name'], callback_data=f"single_style_{key}")])
    await update.message.reply_text(
        "🎨 *Выбери стиль для одиночного фото (GPT Image 2, максимальное качество):*",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def single_style_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    style_key = query.data.replace("single_style_", "")
    context.user_data['single_style'] = style_key
    db = await get_db()
    
    # Проверяем наличие фото
    photo_paths = await db.get_user_photos(user_id, "input")
    photo_paths = [p for p in photo_paths if os.path.exists(p)]
    if not photo_paths:
        await query.edit_message_text(
            "❌ Нет загруженных фото. Загрузите фото через главное меню (📤 Загрузить фото).",
            reply_markup=get_main_menu_keyboard()
        )
        return

    # Проверяем баланс (если используете жетоны – можно добавить, но для простоты сразу генерируем)
    # Здесь можно добавить списание жетонов, если хотите. Пока просто генерируем.
    
    await query.edit_message_text("⏳ Генерация одного фото (GPT Image 2, high quality)... Может занять до 1–2 минут.")
    
    gender = await db.get_user_gender(user_id)
    service = AITunnelService(model_key="gpt_single")   # модель должна быть в PACKAGE_MODELS
    results = await service.generate_package_photos(photo_paths, style_key, gender)

    if results:
        style = Config.STYLES.get(style_key, {})
        name = style.get('name', 'этого стиля')
        await query.message.reply_text(f"✅ Твоё фото в стиле *{name}* готово!", parse_mode='Markdown')
        await send_photo_or_fallback(context.bot, user_id, results[0])
    else:
        await query.message.reply_text("❌ Не удалось сгенерировать фото. Попробуйте позже или выберите другой стиль.")
    
    await query.message.reply_text("👇 *Главное меню*:", parse_mode='Markdown', reply_markup=get_main_menu_keyboard())