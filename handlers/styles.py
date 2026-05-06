import uuid
import logging
import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from config import Config
from handlers.menu import get_main_menu_keyboard
from database.db import get_db
from services.aitunnel_service import AITunnelService
from utils.helpers import send_photo_or_fallback

logger = logging.getLogger(__name__)

async def show_styles_menu(target, context=None):
    keyboard = []
    for key, style in Config.STYLES.items():
        keyboard.append([InlineKeyboardButton(style['name'], callback_data=f"select_style_{key}")])
    text = "🎨 *Выбери сценарий для фотосессии:*"
    if isinstance(target, int):
        await context.bot.send_message(target, text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await target.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def styles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await show_styles_menu(update.message)

async def show_styles_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await show_styles_menu(query.message)

async def style_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user_id = update.effective_user.id
    style_key = query.data.replace("select_style_", "")
    style = Config.STYLES.get(style_key)
    if not style:
        await query.edit_message_text("❌ Неизвестный стиль.")
        return
    db = await get_db()
    photo_count = await db.get_user_photo_count(user_id)
    if photo_count < Config.MIN_PHOTOS:
        await query.edit_message_text(f"⚠️ Нужно минимум {Config.MIN_PHOTOS} фото. Загрузите их через меню.")
        return
    await db.set_user_selected_style(user_id, style_key)
    context.user_data['selected_style'] = style_key
    logger.info(f"✅ Стиль {style_key} сохранён для user {user_id}")

    # Показать выбор модели
    keyboard = []
    for model_key, info in Config.PACKAGE_MODELS.items():
        btn = f"{info['name']} – {info['price_rub']}₽ / {info['price_tokens']} жетонов"
        keyboard.append([InlineKeyboardButton(btn, callback_data=f"select_model_{model_key}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад к стилям", callback_data="back_to_styles")])
    await query.edit_message_text(
        f"✅ Стиль *{style['name']}* выбран.\n\nТеперь выбери модель генерации:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def model_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    model_key = query.data.replace("select_model_", "")
    if model_key not in Config.PACKAGE_MODELS:
        await query.edit_message_text("❌ Неизвестная модель.")
        return
    context.user_data['selected_model'] = model_key
    model_info = Config.PACKAGE_MODELS[model_key]
    style_key = context.user_data.get('selected_style')
    style_name = Config.STYLES.get(style_key, {}).get('name', 'выбранный стиль')
    db = await get_db()
    tokens = await db.get_user_tokens(user_id)

    keyboard = []
    if tokens >= model_info['price_tokens']:
        keyboard.append([InlineKeyboardButton(f"💎 Оплатить жетонами ({model_info['price_tokens']} шт., у вас {tokens})", callback_data="pay_with_tokens")])
    keyboard.append([InlineKeyboardButton(f"💳 Оплатить {model_info['price_rub']}₽", callback_data="pay_with_money")])
    keyboard.append([InlineKeyboardButton("◀️ Назад к стилям", callback_data="back_to_styles")])

    await query.edit_message_text(
        f"✅ Ты выбрал: *{style_name}*, модель *{model_info['name']}*\n\n"
        f"Пакет из {model_info.get('batch_size', 8)} фотографий стоит {model_info['price_rub']}₽ или {model_info['price_tokens']} жетонов.\n\n"
        "👇 Как хочешь оплатить?",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def pay_with_tokens_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    model_key = context.user_data.get('selected_model')
    style_key = context.user_data.get('selected_style')
    if not model_key or not style_key:
        await query.edit_message_text("❌ Сначала выбери стиль и модель.")
        return
    model_info = Config.PACKAGE_MODELS[model_key]
    db = await get_db()
    if not await db.use_tokens(user_id, model_info['price_tokens']):
        await query.edit_message_text("❌ Недостаточно жетонов.")
        return
    await query.edit_message_text(f"⏳ Генерация {model_info.get('batch_size', 8)} фото... Это может занять до 2 минут.")
    await generate_package(user_id, context.bot, db, context, style_key, model_key)

async def pay_with_money_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    model_key = context.user_data.get('selected_model')
    style_key = context.user_data.get('selected_style')
    if not model_key or not style_key:
        await query.edit_message_text("❌ Сначала выбери стиль и модель.")
        return
    model_info = Config.PACKAGE_MODELS[model_key]
    label = f"package_{user_id}_{uuid.uuid4().hex[:8]}"
    data = {'style_key': style_key, 'model_key': model_key}
    db = await get_db()
    await db.create_order(user_id, label, model_info['price_rub'], data=data)
    try:
        from yookassa import Payment
        payment = Payment.create({
            "amount": {"value": str(model_info['price_rub']), "currency": "RUB"},
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/BozhokAI_bot?start=payment_{label}"
            },
            "description": f"Фотосессия ({model_info['name']}, стиль {style_key})",
            "metadata": {"label": label, "user_id": user_id}
        }, uuid.uuid4())
        await db.update_order_payment_id(label, payment.id)
        payment_url = payment.confirmation.confirmation_url
    except Exception as e:
        logger.error(f"Ошибка платежа: {e}")
        await query.edit_message_text("❌ Не удалось создать ссылку на оплату.")
        return
    keyboard = [[InlineKeyboardButton(f"💳 Оплатить {model_info['price_rub']}₽", url=payment_url)]]
    await query.edit_message_text(
        f"✨ Стоимость: {model_info['price_rub']}₽\n\n👇 Нажми кнопку для оплаты. После оплаты фото придут автоматически.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def back_to_styles_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_styles_menu(query.message)

async def generate_package(user_id: int, bot: Bot, db, context, style_key: str, model_key: str):
    try:
        style = Config.STYLES.get(style_key)
        if not style:
            await bot.send_message(user_id, "❌ Стиль не найден.")
            return
        photo_paths = await db.get_user_photos(user_id, "input")
        photo_paths = [p for p in photo_paths if os.path.exists(p)]
        if not photo_paths:
            await bot.send_message(user_id, "❌ Ваши фото не найдены. Загрузите заново.")
            model_info = Config.PACKAGE_MODELS.get(model_key)
            if model_info:
                await db.add_tokens(user_id, model_info['price_tokens'])
            return
        gender = await db.get_user_gender(user_id)
        service = AITunnelService(model_key=model_key)
        results = await service.generate_package_photos(photo_paths, style_key, gender)
        if results:
            await bot.send_message(user_id, f"✅ Твоя фотосессия в стиле *{style['name']}* готова! Вот {len(results)} фотографий:", parse_mode='Markdown')
            for idx, img_data in enumerate(results, 1):
                await send_photo_or_fallback(bot, user_id, img_data, caption=f"📸 Фото {idx}/{len(results)}")
                await asyncio.sleep(0.3)
        else:
            await bot.send_message(user_id, "❌ Не удалось сгенерировать фотосессию.")
            model_info = Config.PACKAGE_MODELS.get(model_key)
            if model_info:
                await db.add_tokens(user_id, model_info['price_tokens'])
                await bot.send_message(user_id, f"💎 Жетоны возвращены.")
        context.user_data.pop('selected_style', None)
        context.user_data.pop('selected_model', None)
        await bot.send_message(user_id, text="👇 *Главное меню*:", parse_mode='Markdown', reply_markup=get_main_menu_keyboard())
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}", exc_info=True)
        await bot.send_message(user_id, "❌ Произошла ошибка.")
        model_info = Config.PACKAGE_MODELS.get(model_key)
        if model_info:
            await db.add_tokens(user_id, model_info['price_tokens'])
            await bot.send_message(user_id, f"💎 Жетоны возвращены.")

async def generate_package_from_data(user_id: int, bot: Bot, db, data: dict):
    style_key = data.get('style_key')
    model_key = data.get('model_key', 'gemini')
    if not style_key:
        logger.error("Нет style_key")
        return
    photo_paths = await db.get_user_photos(user_id, "input")
    photo_paths = [p for p in photo_paths if os.path.exists(p)]
    if not photo_paths:
        await bot.send_message(user_id, "❌ Ваши фото не найдены. Загрузите заново.")
        return
    gender = await db.get_user_gender(user_id)
    service = AITunnelService(model_key=model_key)
    results = await service.generate_package_photos(photo_paths, style_key, gender)
    if results:
        style = Config.STYLES.get(style_key, {})
        name = style.get('name', 'этого стиля')
        await bot.send_message(user_id, f"✅ Твоя фотосессия в стиле *{name}* готова! Вот {len(results)} фотографий:", parse_mode='Markdown')
        for idx, img_data in enumerate(results, 1):
            await send_photo_or_fallback(bot, user_id, img_data, caption=f"📸 Фото {idx}/{len(results)}")
            await asyncio.sleep(0.3)
    else:
        await bot.send_message(user_id, "❌ Ошибка генерации.")
    await bot.send_message(user_id, text="👇 *Главное меню*:", parse_mode='Markdown', reply_markup=get_main_menu_keyboard())

styles_handler = CommandHandler("styles", styles_command)
show_styles_cb = CallbackQueryHandler(show_styles_callback, pattern="^show_styles$")
style_selected_cb = CallbackQueryHandler(style_selected_callback, pattern="^select_style_")
model_selected_cb = CallbackQueryHandler(model_selected_callback, pattern="^select_model_")
pay_with_tokens_cb = CallbackQueryHandler(pay_with_tokens_callback, pattern="^pay_with_tokens$")
pay_with_money_cb = CallbackQueryHandler(pay_with_money_callback, pattern="^pay_with_money$")
back_to_styles_cb = CallbackQueryHandler(back_to_styles_callback, pattern="^back_to_styles$")