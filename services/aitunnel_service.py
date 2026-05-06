import os
import base64
import logging
import aiohttp
import asyncio
from config import Config

logger = logging.getLogger(__name__)

class AITunnelService:
    TIMEOUT = 120

    def __init__(self, model_key: str = "gpt_image_2"):
        info = Config.PACKAGE_MODELS.get(model_key, Config.PACKAGE_MODELS["gpt_image_2"])
        self.api_key = Config.AITUNNEL_API_KEY
        self.base_url = "https://api.aitunnel.ru/v1"
        self.model_name = info["api_model"]
        self.size = info.get("size", "1024x1024")
        self.batch_size = info.get("batch_size", 8)
        logger.info(f"AITunnelService init: model={self.model_name}, batch={self.batch_size}")

    async def generate_package_photos(self, user_photo_paths: list, style_key: str, gender: str = None) -> list:
        logger.info(f"Генерация пакета: style={style_key}, gender={gender}, batch={self.batch_size}")

        style = Config.STYLES.get(style_key)
        if not style:
            raise ValueError(f"Неизвестный стиль: {style_key}")

        # Выбираем промпт в зависимости от пола
        if gender == 'male':
            prompt = style.get('prompt_male', style.get('prompt', ''))
            if '{token}' in prompt:
                prompt = prompt.replace("{token}", "this man")
        elif gender == 'female':
            prompt = style.get('prompt_female', style.get('prompt', ''))
            if '{token}' in prompt:
                prompt = prompt.replace("{token}", "this woman")
        else:
            prompt = style.get('prompt', '')
            if '{token}' in prompt:
                prompt = prompt.replace("{token}", "this person")

        if "Landscape" not in prompt:
            prompt += " Landscape orientation, horizontal composition, aspect ratio 16:9, wide format."
        if "face clearly visible" not in prompt:
            prompt += " Face clearly visible, exact facial features as in the reference image."

        logger.info(f"Промпт: {prompt[:200]}...")

        ref_photo = next((p for p in user_photo_paths if os.path.exists(p)), None)
        if not ref_photo:
            logger.error("Нет доступных фото")
            return []

        with open(ref_photo, "rb") as f:
            image_bytes = f.read()
        logger.info(f"Референс фото: {len(image_bytes)} байт")

        url = f"{self.base_url}/images/edits"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        images = []

        async with aiohttp.ClientSession() as session:
            for i in range(self.batch_size):
                form_data = aiohttp.FormData()
                form_data.add_field('model', self.model_name)
                form_data.add_field('image', image_bytes, filename='photo.jpg', content_type='image/jpeg')
                form_data.add_field('prompt', prompt)
                form_data.add_field('n', '1')
                form_data.add_field('size', self.size)
                # Не добавляем response_format, пусть возвращает URL
                logger.info(f"Запрос {i+1}/{self.batch_size} (edits)")
                success = False
                for attempt in range(3):
                    try:
                        async with session.post(url, headers=headers, data=form_data, timeout=self.TIMEOUT) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if 'data' in data and len(data['data']):
                                    item = data['data'][0]
                                    # Получаем URL
                                    img_url = item.get('url')
                                    if img_url:
                                        if img_url.startswith('data:image/'):
                                            b64 = img_url.split(',')[1]
                                            images.append(b64)
                                            success = True
                                            logger.info(f"Фото {i+1} получено (data URL)")
                                            break
                                        else:
                                            # Скачиваем по обычному URL
                                            async with session.get(img_url) as img_resp:
                                                if img_resp.status == 200:
                                                    img_bytes = await img_resp.read()
                                                    b64 = base64.b64encode(img_bytes).decode()
                                                    images.append(b64)
                                                    success = True
                                                    logger.info(f"Фото {i+1} получено (скачано)")
                                                    break
                                else:
                                    logger.warning(f"Нет data в ответе: {data}")
                            else:
                                text = await resp.text()
                                logger.error(f"Ошибка {resp.status}: {text[:300]}")
                    except Exception as e:
                        logger.error(f"Попытка {attempt+1}: {e}")
                    await asyncio.sleep(1.5 * (2 ** attempt))
                if not success:
                    logger.warning(f"Фото {i+1} не получено")
                await asyncio.sleep(0.3)

        logger.info(f"Сгенерировано {len(images)} фото")
        return images