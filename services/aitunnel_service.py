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
            prompt = style.get('prompt_male')
            if not prompt:
                prompt = style.get('prompt', '').replace("{token}", "this man")
        elif gender == 'female':
            prompt = style.get('prompt_female')
            if not prompt:
                prompt = style.get('prompt', '').replace("{token}", "this woman")
        else:
            prompt = style.get('prompt', '').replace("{token}", "this person")

        # Добавляем горизонтальную ориентацию (если её нет в промпте)
        if "Landscape" not in prompt:
            prompt += " Landscape orientation, horizontal composition, aspect ratio 16:9, wide format."
        if "face clearly visible" not in prompt:
            prompt += " Face clearly visible, exact facial features as in the reference image."

        logger.info(f"Промпт (первые 200 символов): {prompt[:200]}...")

        # Берём первое существующее референсное фото
        ref_photo = next((p for p in user_photo_paths if os.path.exists(p)), None)
        if not ref_photo:
            logger.error("Нет доступных фото пользователя")
            return []

        with open(ref_photo, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")

        url = f"{self.base_url}/images/generations"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "image": image_b64,
            "n": self.batch_size,
            "size": self.size,
            "response_format": "b64_json"
        }

        images = []
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=payload, timeout=self.TIMEOUT) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if 'data' in data and data['data']:
                                for item in data['data']:
                                    b64 = item.get('b64_json')
                                    if b64:
                                        images.append(b64)
                                    else:
                                        url_img = item.get('url')
                                        if url_img and url_img.startswith('data:image/'):
                                            images.append(url_img.split(',')[1])
                                logger.info(f"Получено {len(images)} фото")
                                return images
                            else:
                                logger.warning("Нет data в ответе")
                        else:
                            text = await resp.text()
                            logger.error(f"Ошибка {resp.status}: {text[:300]}")
            except Exception as e:
                logger.error(f"Попытка {attempt+1}: {e}")
            await asyncio.sleep(1.5 * (2 ** attempt))

        logger.warning("Не удалось получить фото после всех попыток")
        return images