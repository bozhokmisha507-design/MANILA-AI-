import os
import base64
import logging
import aiohttp
import asyncio
from config import Config

logger = logging.getLogger(__name__)

class AITunnelService:
    TIMEOUT_FLASH = 150   # увеличен, так как 8 отдельных запросов
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

        # Найдём существующее фото
        ref_photo = next((p for p in user_photo_paths if os.path.exists(p)), None)
        if not ref_photo:
            logger.error("Нет доступных фото пользователя")
            return []

        try:
            with open(ref_photo, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")
                image_data_url = f"data:image/png;base64,{image_b64}"
        except Exception as e:
            logger.error(f"Ошибка кодирования фото: {e}")
            return []

        url = f"{self.base_url}/images/generations"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        timeout = aiohttp.ClientTimeout(total=self.timeout)
        images = []

        async with aiohttp.ClientSession() as session:
            if self.model_key == "flash":
                # Gemini Flash: 8 отдельных запросов
                total_needed = 8
                for i in range(total_needed):
                    payload = {
                        "model": self.model_name,
                        "prompt": prompt,
                        "n": 1,
                        "size": self.size,
                        "response_format": "b64_json",
                        "image": image_data_url
                    }
                    success = False
                    for attempt in range(3):
                        try:
                            async with session.post(url, headers=headers, json=payload, timeout=timeout) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                                    if data.get('data') and len(data['data']) > 0:
                                        b64 = data['data'][0].get('b64_json')
                                        if b64:
                                            images.append(b64)
                                            success = True
                                            logger.info(f"Flash: фото {i+1}/8 получено")
                                            break
                                else:
                                    error_text = await resp.text()
                                    logger.error(f"Flash попытка {attempt+1} для фото {i+1}: {resp.status} - {error_text[:200]}")
                        except Exception as e:
                            logger.error(f"Flash попытка {attempt+1} для фото {i+1}: {e}")
                        await asyncio.sleep(1.5 * (2 ** attempt))
                    if not success:
                        logger.warning(f"Flash: не удалось получить фото {i+1}")
                    await asyncio.sleep(0.5)  # пауза между запросами
            else:
                # GPT Image 2: один запрос на все 8 фото
                payload = {
                    "model": self.model_name,
                    "prompt": prompt,
                    "n": 8,
                    "size": self.size,
                    "response_format": "b64_json",
                    "image": image_data_url
                }
                if self.model_key in ("medium", "high") and self.quality:
                    payload["quality"] = self.quality

                for attempt in range(3):
                    try:
                        async with session.post(url, headers=headers, json=payload, timeout=timeout) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if 'data' in data:
                                    for item in data['data']:
                                        b64 = item.get('b64_json')
                                        if b64:
                                            images.append(b64)
                                    logger.info(f"GPT: сгенерировано {len(images)} фото")
                                    return images
                            else:
                                error_text = await resp.text()
                                logger.error(f"GPT попытка {attempt+1}: {resp.status} - {error_text[:200]}")
                    except Exception as e:
                        logger.error(f"GPT попытка {attempt+1}: {e}")
                    await asyncio.sleep(1.5 * (2 ** attempt))

        logger.info(f"Итого сгенерировано {len(images)} фото для пакета (model={self.model_key})")
        return images