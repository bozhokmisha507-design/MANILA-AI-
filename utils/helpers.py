import re
import base64
import logging
from telegram import Bot

logger = logging.getLogger(__name__)

async def send_photo_or_fallback(bot: Bot, chat_id: int, image_data: str, caption: str = ""):
    """
    Отправляет фото по base64 (с префиксом или без), URL или простой текст.
    При ошибке отправляет сообщение об ошибке.
    """
    try:
        # Если image_data уже содержит префикс data:image
        if image_data.startswith('data:image'):
            base64_str = re.sub('^data:image/.+;base64,', '', image_data)
            image_bytes = base64.b64decode(base64_str)
            await bot.send_photo(chat_id=chat_id, photo=image_bytes, caption=caption)
            return
        # Если это http URL
        if image_data.startswith('http://') or image_data.startswith('https://'):
            await bot.send_photo(chat_id=chat_id, photo=image_data, caption=caption)
            return
        # Если это чистый base64 (без префикса) – попробуем декодировать
        # Проверим, что строка длинная и состоит из допустимых символов base64
        if len(image_data) > 100 and re.match(r'^[A-Za-z0-9+/=]+$', image_data):
            image_bytes = base64.b64decode(image_data)
            await bot.send_photo(chat_id=chat_id, photo=image_bytes, caption=caption)
            return
        # В противном случае отправляем как текст (обрезаем, чтобы избежать 413)
        short_text = image_data[:1000] + ("..." if len(image_data) > 1000 else "")
        await bot.send_message(chat_id=chat_id, text=caption + "\n" + short_text)
    except Exception as e:
        logger.error(f"Ошибка отправки фото пользователю {chat_id}: {e}")
        await bot.send_message(chat_id=chat_id, text="❌ Не удалось отправить фото. Попробуйте позже.")

async def send_video_or_fallback(bot: Bot, chat_id: int, video_data: str | bytes, caption: str = ""):
    """
    Отправляет видео по URL, base64 или байтам.
    При ошибке отправляет сообщение об ошибке.
    """
    try:
        if isinstance(video_data, bytes):
            await bot.send_video(chat_id=chat_id, video=video_data, caption=caption)
            return
        if isinstance(video_data, str):
            if video_data.startswith('data:video'):
                base64_str = re.sub('^data:video/.+;base64,', '', video_data)
                video_bytes = base64.b64decode(base64_str)
                await bot.send_video(chat_id=chat_id, video=video_bytes, caption=caption)
                return
            if video_data.startswith('http://') or video_data.startswith('https://'):
                await bot.send_video(chat_id=chat_id, video=video_data, caption=caption)
                return
            # Если это чистый base64 (без префикса)
            if len(video_data) > 100 and re.match(r'^[A-Za-z0-9+/=]+$', video_data):
                video_bytes = base64.b64decode(video_data)
                await bot.send_video(chat_id=chat_id, video=video_bytes, caption=caption)
                return
        # Если ничего не подошло – как текст
        await bot.send_message(chat_id=chat_id, text=caption + "\n" + str(video_data)[:1000])
    except Exception as e:
        logger.error(f"Ошибка отправки видео пользователю {chat_id}: {e}")
        await bot.send_message(chat_id=chat_id, text="❌ Не удалось отправить видео. Попробуйте позже.")