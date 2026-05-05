import os
import base64
import logging
import aiohttp
import asyncio
from config import Config

logger = logging.getLogger(__name__)

class AITunnelService:
    TIMEOUT = 120

    def __init__(self, model_key: str = "gpt"):
        info = Config.PACKAGE_MODELS.get(model_key, Config.PACKAGE_MODELS["gpt"])
        self.api_key = Config.AITUNNEL_API_KEY
        self.base_url = "https://api.aitunnel.ru/v1"
        self.model_name = info["api_model"]
        self.size = info.get("size", "1024x1024")
        self.quality = info.get("quality", "medium")
        logger.info(f"AITunnelService (GPT edits) init: model={self.model_name}")

    async def generate_package_photos(self, user_photo_paths: list, style_key: str, gender: str = None) -> list:
        logger.info(f"Генерация пакета: style={style_key}")

        style = Config.STYLES.get(style_key)
        if not style:
            raise ValueError(f"Неизвестный стиль: {style_key}")

        base_prompt = style["prompt"]
        subject = "this man" if gender == 'male' else "this woman" if gender == 'female' else "this person"
        prompt = base_prompt.replace("{token}", subject)
        prompt += " Landscape orientation, horizontal composition, aspect ratio 16:9, wide format. Do not change the person's identity."

        # Берём первое существующее фото
        ref_photo = next((p for p in user_photo_paths if os.path.exists(p)), None)
        if not ref_photo:
            logger.error("Нет доступных фото пользователя")
            return []

        TOTAL_NEEDED = 1   # ⬅️ ТЕСТ: 1 фото. После успеха замените на 8
        images = []
        url = f"{self.base_url}/images/edits"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with aiohttp.ClientSession() as session:
            for i in range(TOTAL_NEEDED):
                form_data = aiohttp.FormData()
                form_data.add_field('model', self.model_name)
                with open(ref_photo, 'rb') as f:
                    form_data.add_field('image', f, filename='photo.jpg', content_type='image/jpeg')
                form_data.add_field('prompt', prompt)
                form_data.add_field('n', '1')
                form_data.add_field('size', self.size)
                form_data.add_field('response_format', 'b64_json')
                form_data.add_field('quality', self.quality)
                form_data.add_field('strength', '0.85')  # сохранение лица

                logger.info(f"Запрос {i+1}/{TOTAL_NEEDED} (edits)")
                success = False
                for attempt in range(3):
                    try:
                        async with session.post(url, headers=headers, data=form_data, timeout=self.TIMEOUT) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if 'data' in data and len(data['data']):
                                    item = data['data'][0]
                                    b64 = item.get('b64_json')
                                    if b64:
                                        images.append(b64)
                                        success = True
                                        logger.info(f"Фото {i+1} получено (b64)")
                                        break
                                    url_img = item.get('url')
                                    if url_img and url_img.startswith('data:image/'):
                                        b64 = url_img.split(',')[1]
                                        images.append(b64)
                                        success = True
                                        logger.info(f"Фото {i+1} получено из url")
                                        break
                            else:
                                text = await resp.text()
                                logger.error(f"Ошибка {resp.status}: {text[:300]}")
                    except Exception as e:
                        logger.error(f"Попытка {attempt+1}: {e}")
                    await asyncio.sleep(1.5 * (2 ** attempt))
                if not success:
                    logger.warning(f"Фото {i+1} не получено")
                await asyncio.sleep(0.3)  # пауза между запросами

        logger.info(f"Сгенерировано {len(images)} фото")
        return images