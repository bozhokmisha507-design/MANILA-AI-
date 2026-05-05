import os
import base64
import logging
import aiohttp
import asyncio
from config import Config

logger = logging.getLogger(__name__)

class AITunnelService:
    TIMEOUT_FLASH = 90
    TIMEOUT_MEDIUM = 120
    TIMEOUT_HIGH = 180

    def __init__(self, model_key: str = "flash"):
        self.api_key = Config.AITUNNEL_API_KEY
        self.base_url = "https://api.aitunnel.ru/v1"
        self.model_key = model_key
        info = Config.PACKAGE_MODELS.get(model_key, Config.PACKAGE_MODELS["flash"])
        self.model_name = info["api_model"]
        self.quality = info.get("quality", "standard")
        self.size = info.get("size", "1024x1024")
        self.timeout = {
            "flash": self.TIMEOUT_FLASH,
            "medium": self.TIMEOUT_MEDIUM,
            "high": self.TIMEOUT_HIGH
        }.get(model_key, self.TIMEOUT_FLASH)

    async def generate_package_photos(self, user_photo_paths: list, style_key: str, gender: str = None) -> list:
        style = Config.STYLES.get(style_key)
        if not style:
            raise ValueError(f"Неизвестный стиль: {style_key}")

        base_prompt = style["prompt"]
        if gender == 'male':
            subject = "this man"
        elif gender == 'female':
            subject = "this woman"
        else:
            subject = "this person"
        prompt = base_prompt.replace("{token}", subject)
        prompt += " Landscape orientation, horizontal composition, aspect ratio 16:9, wide format."

        # Найдём существующее фото
        ref_photo = next((p for p in user_photo_paths if os.path.exists(p)), None)
        if not ref_photo:
            logger.error("Нет доступных фото пользователя")
            return []

        try:
            with open(ref_photo, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.error(f"Ошибка кодирования фото: {e}")
            return []

        url = f"{self.base_url}/images/generations"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "n": 8,
            "size": self.size,
            "response_format": "b64_json",
            "image": image_b64
        }
        # Параметр quality добавляется только для моделей, которые его поддерживают.
        # Для dall-e-2 качество не нужно (оно определяется размером и количеством шагов),
        # но оставим для совместимости с GPT Image 2 – если API его не принимает,
        # он просто проигнорирует.
        if self.model_key in ("medium", "high"):
            payload["quality"] = self.quality

        timeout = aiohttp.ClientTimeout(total=self.timeout)
        images = []

        async with aiohttp.ClientSession() as session:
            for attempt in range(3):
                try:
                    async with session.post(url, headers=headers, json=payload, timeout=timeout) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if 'data' in data:
                                for item in data['data']:
                                    if 'b64_json' in item:
                                        images.append(item['b64_json'])
                                    elif 'url' in item:
                                        images.append(item['url'])
                                logger.info(f"Сгенерировано {len(images)} фото для пакета")
                                return images
                            else:
                                logger.warning(f"Ответ не содержит 'data': {data}")
                        else:
                            error_text = await resp.text()
                            logger.error(f"Попытка {attempt+1}: ошибка {resp.status} - {error_text[:200]}")
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.error(f"Попытка {attempt+1} не удалась: {e}")
                    if attempt == 2:
                        return []
                await asyncio.sleep(1.5 * (2 ** attempt))
        return []