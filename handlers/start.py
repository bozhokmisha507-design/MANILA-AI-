import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from config import Config
from database.db import get_db
from handlers.menu import get_main_menu_keyboard
from handlers.payment import my_tokens_command
from yookassa import Configuration, Payment as YKPayment

logger = logging.getLogger(__name__)

WELCOME_MEDIA_FILE_ID = "BAACAgIAAxkBAAIBJ2n3gLzRDDXCJmYcMRd1bht-W1vHAAJmngACH-64S6dbeyxDvhZcOwQ"  # ваш file_id
OFFER_URL = "https://disk.yandex.ru/i/n9V2oNKPQ4Vbrw"

Configuration.account_id = Config.YKASSA_SHOP_ID
Configuration.secret_key = Config.YKASSA_SECRET_KEY

async def send_welcome_message(chat_id: int, first_name: str, bot):
    # Формируем текст с ценами динамически
    models_text = ""
    for key, m in Config.PACKAGE_MODELS.items():
        # Показываем, что пакет из 4 фото
        models_text += f"• {m['name']} – {m['price_rub']}₽ / {m['price_tokens']} жетонов (пакет 4 фото)\n"

    welcome_text = (
        f"🎨 *Привет, {first_name}!*\n\n"
        f"Добро пожаловать в *MANILA – AI Фотосессии*! 📸\n\n"
        f"Я превращу твои селфи в профессиональную фотосессию из **4 кадров**.\n\n"
        f"🔥 *Как это работает:*\n"
        f"1. Загрузи 2–5 своих фото\n"
        f"2. Выбери сценарий (интерьер, парк, набережная, кафе, студия, сквер)\n"
        f"3. Выбери модель генерации\n"
        f"4. Оплати и получи 4 уникальных фото в разных ракурсах!\n\n"
        f"💎 *Цены за 4 фото:*\n"
        f"{models_text}\n"
        f"💳 *Способы оплаты:*\n"
        f"• Банковские карты (Visa, Mastercard, МИР)\n"
        f"• SberPay – для клиентов Сбера (удобно через приложение)\n"
        f"• T-Pay – для клиентов Т-Банка\n"
        f"• СБП (Система быстрых платежей) – оплата по QR-коду\n\n"
        f"👇 Жми на кнопки ниже и создавай свою идеальную фотосессию!"
    )
    try:
        await bot.send_video(chat_id, video=WELCOME_MEDIA_FILE_ID, caption=welcome_text, parse_mode='Markdown', reply_markup=get_main_menu_keyboard())
    except Exception:
        try:
            await bot.send_photo(chat_id, photo=WELCOME_MEDIA_FILE_ID, caption=welcome_text, parse_mode='Markdown', reply_markup=get_main_menu_keyboard())
        except Exception as e:
            logger.error(f"Ошибка отправки приветствия: {e}")
            await bot.send_message(chat_id, text=welcome_text, parse_mode='Markdown', reply_markup=get_main_menu_keyboard())

async def send_offer_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📜 Публичная оферта\n\nОзнакомиться с условиями можно по ссылке:\n{OFFER_URL}\n\nНажимая «✅ Принимаю», вы соглашаетесь.",
        parse_mode=None,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Принимаю", callback_data="accept_offer")],
            [InlineKeyboardButton("❌ Не принимаю", callback_data="decline_offer")]
        ])
    )

async def offer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    db = await get_db()
    if query.data == "accept_offer":
        await db.set_user_agreed_to_offer(user_id, True)
        await query.message.reply_text("✅ Спасибо! Вы приняли условия оферты.")
        await show_gender_selection(update, context)
    else:
        await query.message.reply_text("❌ Вы не приняли оферту. К сожалению, без этого мы не можем предоставить услуги.")

async def show_gender_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🤵🏼‍♂️ Мужской", callback_data="set_gender_male")],
        [InlineKeyboardButton("🤵🏼‍♀️ Женский", callback_data="set_gender_female")]
    ]
    if update.callback_query:
        await update.callback_query.message.reply_text("Укажите ваш пол:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("Укажите ваш пол:", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await send_welcome_message(update.effective_chat.id, user.first_name, context.bot)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        arg = context.args[0]
        if arg.startswith("payment_"):
            label = arg.replace("payment_", "")
            user_id = update.effective_user.id
            db = await get_db()
            payment_id = await db.get_payment_id_by_label(label)
            if not payment_id:
                await update.message.reply_text("❌ Информация о платеже не найдена.", reply_markup=get_main_menu_keyboard())
                return
            try:
                payment = YKPayment.find_one(payment_id)
                if payment.status == 'succeeded':
                    from handlers.styles import generate_package_from_data
                    order_data = await db.get_order_data(label)
                    if order_data:
                        await generate_package_from_data(user_id, context.bot, db, order_data)
                    else:
                        await update.message.reply_text("❌ Ошибка: данные заказа не найдены.", reply_markup=get_main_menu_keyboard())
                else:
                    await update.message.reply_text(f"⏳ Ваш платёж в статусе «{payment.status}». Если вы оплатили, подождите.", reply_markup=get_main_menu_keyboard())
            except Exception as e:
                logger.error(f"Ошибка проверки платежа: {e}")
                await update.message.reply_text("❌ Не удалось проверить оплату.", reply_markup=get_main_menu_keyboard())
            return
        elif arg.startswith("tokens_"):
            await update.message.reply_text("⏳ Платёж за жетоны обрабатывается. Жетоны поступят автоматически.", reply_markup=get_main_menu_keyboard())
            return

    user = update.effective_user
    user_id = user.id
    db = await get_db()
    await db.get_or_create_user(user_id, user.username, user.first_name)
    agreed = await db.get_user_agreed_to_offer(user_id)
    if agreed:
        await show_gender_selection(update, context)
    else:
        await send_offer_file(update, context)

async def gender_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    gender = query.data.replace("set_gender_", "")
    user_id = update.effective_user.id
    db = await get_db()
    await db.set_user_gender(user_id, gender)
    await send_welcome_message(query.message.chat.id, update.effective_user.first_name, context.bot)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Формируем список моделей
    models_list = ""
    for key, m in Config.PACKAGE_MODELS.items():
        models_list += f"   • {m['name']} – {m['price_rub']}₽ / {m['price_tokens']} жетонов (пакет 4 фото)\n"

    help_text = (
        "📖 *Помощь по MANILA AI Фотосессии*\n\n"
        "**Как заказать фотосессию из 4 кадров?**\n"
        "1. Нажми «📤 Загрузить фото» и отправь 2–5 своих селфи.\n"
        "2. Нажми «🖼️ Стили» и выбери сценарий.\n"
        "3. Выбери модель:\n"
        f"{models_list}"
        "4. Оплати (рублями или жетонами) и через 1-2 минуты получи 4 фото.\n\n"
        "💳 *Способы оплаты:*\n"
        "• Банковские карты (Visa, Mastercard, МИР)\n"
        "• SberPay – для клиентов Сбера\n"
        "• T-Pay – для клиентов Т-Банка\n"
        "• СБП (Система быстрых платежей) – оплата по QR-коду\n\n"
        "**💎 Жетоны**\n"
        "• Пополнить баланс: /buy20 или кнопка «💎 Мои жетоны»\n"
        "• 1 пакет жетонов = 20 шт за 700₽\n\n"
        "**🛠️ Очистка фото**\n"
        "• Кнопка «🗑 Очистить селфи» удаляет загруженные фото.\n\n"
        "**📞 Поддержка**\n"
        "super-mike-4@yandex.ru\n\n"
        f"📜 [Публичная оферта]({OFFER_URL})"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown', reply_markup=get_main_menu_keyboard(), disable_web_page_preview=True)

async def handle_main_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📤 Загрузить фото":
        from handlers.upload import upload_command
        await upload_command(update, context)
    elif text == "🖼️ Стили":
        from handlers.styles import styles_command
        await styles_command(update, context)
    elif text == "❓ Помощь":
        await help_command(update, context)
    elif text == "🗑 Очистить селфи":
        from handlers.clean import clean_photos_command
        await clean_photos_command(update, context)
    elif text == "🏠 Главное меню":
        await show_main_menu(update, context)
    elif text == "💎 Мои жетоны":
        await my_tokens_command(update, context)
    else:
        await update.message.reply_text("Используйте кнопки меню.", reply_markup=get_main_menu_keyboard())

# Секретная команда /getlink (админы)
WAITING_MEDIA = 1
AUTHORIZED_USERS = Config.ADMIN_IDS

async def secret_get_link_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in AUTHORIZED_USERS:
        await update.message.reply_text("Команда не найдена.")
        return ConversationHandler.END
    await update.message.reply_text("🔒 Отправьте фото, видео или GIF.")
    return WAITING_MEDIA

async def secret_get_link_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in AUTHORIZED_USERS:
        return ConversationHandler.END
    file_id = update.message.photo[-1].file_id
    file = await context.bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{context.bot.token}/{file.file_path}"
    await update.message.reply_text(f"✅ File ID:\n`{file_id}`\n\n🔗 Ссылка:\n`{file_url}`", parse_mode='Markdown')
    return ConversationHandler.END

async def secret_get_link_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in AUTHORIZED_USERS:
        return ConversationHandler.END
    file_id = update.message.video.file_id
    file = await context.bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{context.bot.token}/{file.file_path}"
    await update.message.reply_text(f"✅ File ID:\n`{file_id}`\n\n🔗 Ссылка:\n`{file_url}`", parse_mode='Markdown')
    return ConversationHandler.END

async def secret_get_link_animation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in AUTHORIZED_USERS:
        return ConversationHandler.END
    file_id = update.message.animation.file_id
    file = await context.bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{context.bot.token}/{file.file_path}"
    await update.message.reply_text(f"✅ File ID:\n`{file_id}`\n\n🔗 Ссылка:\n`{file_url}`", parse_mode='Markdown')
    return ConversationHandler.END

async def secret_get_link_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END

secret_link_conv = ConversationHandler(
    entry_points=[CommandHandler("getlink", secret_get_link_start)],
    states={WAITING_MEDIA: [MessageHandler(filters.PHOTO, secret_get_link_photo), MessageHandler(filters.VIDEO, secret_get_link_video), MessageHandler(filters.ANIMATION, secret_get_link_animation), CommandHandler("cancel", secret_get_link_cancel)]},
    fallbacks=[CommandHandler("cancel", secret_get_link_cancel)], per_user=True, per_chat=True
)

start_handler = CommandHandler("start", start_command)
help_handler = CommandHandler("help", help_command)