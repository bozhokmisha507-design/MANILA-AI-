import os
import base64
import logging
import aiohttp
import asyncio
from config import Config

logger = logging.getLogger(__name__)

class AITunnelService:
    TIMEOUT_FLASH = 150
    TIMEOUT_MEDIUM = 120
    TIMEOUT_HIGH = 180
    TIMEOUT_PRO = 150

    def __init__(self, model_key: str = "flash"):
        self.api_key = Config.AITUNNEL_API_KEY
        self.base_url = "https://api.aitunnel.ru/v1"
        self.model_key = model_key
        info = Config.PACKAGE_MODELS.get(model_key, Config.PACKAGE_MODELS["flash"])
        self.model_name = info["api_model"]
        self.size = info.get("size", "1024x1024")
        # Таймаут
        if model_key == "flash":
            self.timeout = self.TIMEOUT_FLASH
        elif model_key == "pro":
            self.timeout = self.TIMEOUT_PRO
        elif model_key == "medium":
            self.timeout = self.TIMEOUT_MEDIUM
        elif model_key == "high":
            self.timeout = self.TIMEOUT_HIGH
        else:
            self.timeout = self.TIMEOUT_FLASH
        logger.info(f"AITunnelService init: model_key={model_key}, model={self.model_name}")

    async def generate_package_photos(self, user_photo_paths: list, style_key: str, gender: str = None) -> list:
        logger.info(f"Генерация пакета: model={self.model_key}, style={style_key}")

        style = Config.STYLES.get(style_key)
        if not style:
            raise ValueError(f"Неизвестный стиль: {style_key}")

        base_prompt = style["prompt"]
        subject = "this man" if gender == 'male' else "this woman" if gender == 'female' else "this person"
        prompt = base_prompt.replace("{token}", subject)
        logger.info(f"Промпт: {prompt[:150]}...")

        ref_photo = next((p for p in user_photo_paths if os.path.exists(p)), None)
        if not ref_photo:
            logger.error("Нет доступных фото пользователя")
            return []
        logger.info(f"Референс: {ref_photo}")

        try:
            with open(ref_photo, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")
                logger.info(f"Base64 длина: {len(image_b64)}")
        except Exception as e:
            logger.error(f"Ошибка чтения фото: {e}")
            return []

        images = []
        TOTAL_NEEDED = 2   # временно 2 фото

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/images/generations"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            for i in range(TOTAL_NEEDED):
                payload = {
                    "model": self.model_name,
                    "prompt": prompt,
                    "n": 1,
                    "size": self.size,
                    "image": image_b64,      # чистый base64
                    "strength": 0.8          # ключевой параметр для сохранения лица
                }
                # Для GPT модели качество можно добавить, но пока не будем
                logger.info(f"Запрос {i+1}/{TOTAL_NEEDED} (generations, модель {self.model_name})")
                success = False
                for attempt in range(3):
                    try:
                        async with session.post(url, headers=headers, json=payload, timeout=self.timeout) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                # Извлекаем изображение
                                b64 = None
                                if 'data' in data and len(data['data']):
                                    item = data['data'][0]
                                    if 'b64_json' in item:
                                        b64 = item['b64_json']
                                    elif 'url' in item:
                                        url_data = item['url']
                                        if url_data.startswith('data:image/'):
                                            b64 = url_data.split(',', 1)[1]
                                        else:
                                            # Если url обычный, можно попробовать скачать, но для простоты пропускаем
                                            logger.warning(f"Получен обычный URL: {url_data[:50]}")
                                if b64:
                                    images.append(b64)
                                    success = True
                                    logger.info(f"Фото {i+1} получено")
                                    break
                                else:
                                    logger.warning(f"Нет b64 в ответе: {data}")
                            else:
                                text = await resp.text()
                                logger.error(f"Ошибка {resp.status}: {text[:200]}")
                    except Exception as e:
                        logger.error(f"Попытка {attempt+1} не удалась: {e}")
                    await asyncio.sleep(1.5 * (2 ** attempt))
                if not success:
                    logger.warning(f"Не удалось получить фото {i+1}")
                await asyncio.sleep(0.5)

        logger.info(f"Итого сгенерировано {len(images)} фото")
        return images