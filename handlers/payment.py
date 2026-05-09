import uuid
import logging
from decimal import Decimal
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from yookassa import Configuration, Payment
from config import Config
from handlers.menu import get_main_menu_keyboard
from database.db import get_db
from handlers.styles import generate_package_from_data

logger = logging.getLogger(__name__)

# ---------- Настройка ЮKassa ----------
Configuration.account_id = Config.YKASSA_SHOP_ID
Configuration.secret_key = Config.YKASSA_SECRET_KEY

# ---------- Команда /buy (перенаправление) ----------
async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎨 Для покупки фотосессии сначала выбери стиль через кнопку «🖼️ Стили» в главном меню.",
        reply_markup=get_main_menu_keyboard()
    )

# ---------- Команда /buy20 (пакет жетонов) ----------
async def buy_tokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    label = f"tokens20_{user_id}_{uuid.uuid4().hex[:8]}"
    amount = Config.PRICE_20_TOKENS

    db = await get_db()
    await db.create_order(user_id, label, amount, data={'token_pack': 20})

    try:
        payment = Payment.create({
            "amount": {"value": str(amount), "currency": "RUB"},
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/BozhokAI_bot?start=tokens_{label}"
            },
            "description": f"Пакет 20 жетонов – фотосессии со скидкой",
            "metadata": {"label": label, "user_id": user_id}
        }, uuid.uuid4())
        await db.update_order_payment_id(label, payment.id)
        payment_url = payment.confirmation.confirmation_url
    except Exception as e:
        logger.error(f"Ошибка создания платежа для пакета: {e}")
        await update.message.reply_text("❌ Не удалось создать ссылку.", reply_markup=get_main_menu_keyboard())
        return

    keyboard = [[InlineKeyboardButton(f"💳 Оплатить {amount}₽", url=payment_url)]]
    await update.message.reply_text(
        f"✨ Купи пакет из 20 жетонов!\nСтоимость пакета: {amount}₽",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------- Callback для inline-кнопки "💎 Купить жетоны" ----------
async def buy_tokens_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    label = f"tokens20_{user_id}_{uuid.uuid4().hex[:8]}"
    amount = Config.PRICE_20_TOKENS
    db = await get_db()
    await db.create_order(user_id, label, amount, data={'token_pack': 20})

    try:
        payment = Payment.create({
            "amount": {"value": str(amount), "currency": "RUB"},
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/BozhokAI_bot?start=tokens_{label}"
            },
            "description": f"Пакет 20 жетонов",
            "metadata": {"label": label, "user_id": user_id}
        }, uuid.uuid4())
        await db.update_order_payment_id(label, payment.id)
        payment_url = payment.confirmation.confirmation_url
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await query.edit_message_text("❌ Не удалось создать ссылку.")
        return

    keyboard = [[InlineKeyboardButton(f"💳 Оплатить {amount}₽", url=payment_url)]]
    await query.edit_message_text(
        f"✨ Купи пакет из 20 жетонов!\nСтоимость: {amount}₽",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------- Показать баланс жетонов (исправлено – динамически) ----------
async def my_tokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = await get_db()
    tokens = await db.get_user_tokens(user_id)

    # Формируем список моделей из PACKAGE_MODELS
    models_text = ""
    for model_key, model in Config.PACKAGE_MODELS.items():
        models_text += f"• {model['name']} – {model['price_tokens']} жетонов (пакет {model.get('batch_size', 4)} фото)\n"

    text = (
        f"💎 *Ваш баланс жетонов:* {tokens}\n\n"
        f"💰 *Стоимость пакетов:*\n"
        f"{models_text}\n"
        f"💎 Жетоны можно купить кнопкой ниже."
    )
    keyboard = [[InlineKeyboardButton("💎 Купить 20 жетонов за 700₽", callback_data="buy_tokens")]]
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------- Обработка вебхука ЮKassa ----------
async def process_yookassa_webhook(data: dict, bot: Bot, db):
    logger.info(f"Получено уведомление от ЮKassa: {data}")
    event = data.get('event')
    if event != 'payment.succeeded':
        logger.info(f"Игнорируем событие {event}")
        return

    payment = data.get('object')
    if not payment:
        logger.warning("Нет объекта payment")
        return

    metadata = payment.get('metadata', {})
    label = metadata.get('label')
    if not label:
        logger.warning("Нет label в метаданных")
        return

    if await db.is_order_processed(label):
        logger.info(f"Заказ {label} уже обработан, пропускаем")
        return

    user_id = metadata.get('user_id')
    if not user_id:
        parts = label.split('_')
        if len(parts) > 1 and parts[1].isdigit():
            user_id = int(parts[1])
    if not user_id:
        logger.error(f"Не удалось определить user_id для {label}")
        return

    if label.startswith("tokens20_"):
        await db.add_tokens(user_id, 20)
        await bot.send_message(user_id, "✅ Вам начислено 20 жетонов! Теперь вы можете заказать пакетную фотосессию.")
        await db.mark_order_processed(label)

    elif label.startswith("package_"):
        order_data = await db.get_order_data(label)
        if not order_data:
            logger.error(f"Нет данных для заказа {label}")
            return
        try:
            await generate_package_from_data(user_id, bot, db, order_data)
        except Exception as e:
            logger.error(f"Ошибка генерации пакета {label}: {e}", exc_info=True)
            # Начисляем компенсационные жетоны
            model_key = order_data.get('model_key', 'gemini')
            token_cost = Config.PACKAGE_MODELS.get(model_key, Config.PACKAGE_MODELS['gemini'])['price_tokens']
            await db.add_tokens(user_id, token_cost)
            await bot.send_message(user_id, f"⚠️ Ошибка генерации фотосессии. Вам начислено {token_cost} жетонов. Попробуйте позже.")
        finally:
            await db.mark_order_processed(label)
    else:
        logger.warning(f"Неизвестный тип заказа: {label}")

# ---------- Экспорт обработчиков ----------
buy_handler = CommandHandler("buy", buy_command)
buy_tokens_handler = CommandHandler("buy20", buy_tokens_command)
buy_tokens_callback_handler = CallbackQueryHandler(buy_tokens_callback, pattern="^buy_tokens$")