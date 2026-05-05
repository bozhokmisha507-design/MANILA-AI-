import os
import base64
import logging
import aiohttp
import asyncio
from config import Config

logger = logging.getLogger(__name__)

class AITunnelService:
    TIMEOUT = 90

    def __init__(self, model_key: str = "pro"):
        info = Config.PACKAGE_MODELS.get(model_key, Config.PACKAGE_MODELS["pro"])
        self.api_key = Config.AITUNNEL_API_KEY
        self.base_url = "https://api.aitunnel.ru/v1"
        self.model_name = info["api_model"]
        self.size = info.get("size", "1024x1024")
        logger.info(f"AITunnelService init: model={self.model_name}")

    async def generate_package_photos(self, user_photo_paths: list, style_key: str, gender: str = None) -> list:
        logger.info(f"Генерация пакета: style={style_key}")

        style = Config.STYLES.get(style_key)
        if not style:
            raise ValueError(f"Неизвестный стиль: {style_key}")

        base_prompt = style["prompt"]
        subject = "this man" if gender == 'male' else "this woman" if gender == 'female' else "this person"
        prompt = base_prompt.replace("{token}", subject)
        prompt += " Landscape orientation, horizontal composition, aspect ratio 16:9, wide format."

        ref_photo = next((p for p in user_photo_paths if os.path.exists(p)), None)
        if not ref_photo:
            logger.error("Нет доступных фото пользователя")
            return []
        logger.info(f"Референс: {ref_photo}")

        try:
            with open(ref_photo, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")
                data_url = f"data:image/jpeg;base64,{image_b64}"
        except Exception as e:
            logger.error(f"Ошибка кодирования фото: {e}")
            return []

        TOTAL_NEEDED = 8   # количество фото (для теста поставьте 2)
        images = []
        url = f"{self.base_url}/images/generations"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            for i in range(TOTAL_NEEDED):
                payload = {
                    "model": self.model_name,
                    "prompt": prompt,
                    "n": 1,
                    "size": self.size,
                    "image": data_url,
                    "strength": 0.8,
                    "response_format": "b64_json"
                }
                logger.info(f"Запрос {i+1}/{TOTAL_NEEDED}")
                success = False
                for attempt in range(3):
                    try:
                        async with session.post(url, headers=headers, json=payload, timeout=self.TIMEOUT) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if 'data' in data and len(data['data']):
                                    item = data['data'][0]
                                    b64 = item.get('b64_json')
                                    if b64:
                                        images.append(b64)
                                        success = True
                                        logger.info(f"Фото {i+1} получено")
                                        break
                                    # Запасной вариант: из url
                                    img_url = item.get('url')
                                    if img_url and img_url.startswith('data:image/'):
                                        b64 = img_url.split(',')[1]
                                        images.append(b64)
                                        success = True
                                        logger.info(f"Фото {i+1} получено из url")
                                        break
                            else:
                                text = await resp.text()
                                logger.error(f"Ошибка {resp.status}: {text[:200]}")
                    except Exception as e:
                        logger.error(f"Попытка {attempt+1}: {e}")
                    await asyncio.sleep(1.5 * (2 ** attempt))
                if not success:
                    logger.warning(f"Фото {i+1} не получено")
                await asyncio.sleep(0.5)

        logger.info(f"Сгенерировано {len(images)} фото")
        return images