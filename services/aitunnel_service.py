import os
import base64
import logging
import aiohttp
import asyncio
import random
from config import Config

logger = logging.getLogger(__name__)

class AITunnelService:
    TIMEOUT_FLASH = 150
    TIMEOUT_PRO = 150
    TIMEOUT_MEDIUM = 120
    TIMEOUT_HIGH = 120

    def __init__(self, model_key: str = "flash"):
        self.api_key = Config.AITUNNEL_API_KEY
        self.base_url = "https://api.aitunnel.ru/v1"
        self.model_key = model_key
        info = Config.PACKAGE_MODELS.get(model_key, Config.PACKAGE_MODELS["flash"])
        self.model_name = info["api_model"]
        self.size = info.get("size", "1024x1024")
        if model_key in ("flash", "pro"):
            self.timeout = self.TIMEOUT_FLASH if model_key == "flash" else self.TIMEOUT_PRO
        else:
            self.timeout = self.TIMEOUT_MEDIUM
        logger.info(f"AITunnelService init: model_key={model_key}, model={self.model_name}")

    async def generate_package_photos(self, user_photo_paths: list, style_key: str, gender: str = None) -> list:
        logger.info(f"Генерация пакета: model={self.model_key}, style={style_key}")

        style = Config.STYLES.get(style_key)
        if not style:
            raise ValueError(f"Неизвестный стиль: {style_key}")

        base_prompt = style["prompt"]
        subject = "this man" if gender == 'male' else "this woman" if gender == 'female' else "this person"
        prompt = base_prompt.replace("{token}", subject)
        # Добавляем ориентацию для горизонтального формата (как в PIXEL)
        if self.model_key in ("flash", "pro"):
            prompt += " Landscape orientation, horizontal composition, aspect ratio 16:9, wide format."

        # Берём первое существующее фото
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

        images = []
        TOTAL_NEEDED = 2   # для теста 2 фото, потом замените на 8

        async with aiohttp.ClientSession() as session:
            if self.model_key in ("flash", "pro"):
                # Метод PIXEL: чат-эндпоинт
                url = f"{self.base_url}/chat/completions"
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                for i in range(TOTAL_NEEDED):
                    payload = {
                        "model": self.model_name,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "image_url", "image_url": {"url": data_url}},
                                    {"type": "text", "text": f"Сгенерируй фото на основе этого человека: {prompt}"}
                                ]
                            }
                        ],
                        "modalities": ["image", "text"],
                        "max_tokens": 1000,
                        "seed": random.randint(1, 1000000),
                        "candidate_count": 1
                    }
                    logger.info(f"Запрос {i+1}/{TOTAL_NEEDED} (chat)")
                    success = False
                    for attempt in range(3):
                        try:
                            async with session.post(url, headers=headers, json=payload, timeout=self.timeout) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                                    if 'choices' in data and data['choices']:
                                        message = data['choices'][0].get('message', {})
                                        # Извлекаем изображение из message['images'] (основной путь)
                                        if 'images' in message and message['images']:
                                            for img in message['images']:
                                                if 'image_url' in img and 'url' in img['image_url']:
                                                    img_url = img['image_url']['url']
                                                    if img_url.startswith('data:image/'):
                                                        b64 = img_url.split(',', 1)[1]
                                                        images.append(b64)
                                                        success = True
                                                        logger.info(f"Фото {i+1} получено из images")
                                                        break
                                            if success:
                                                break
                                        # Запасной вариант: content содержит data URL
                                        elif 'content' in message and message['content'].startswith('data:image'):
                                            b64 = message['content'].split(',', 1)[1]
                                            images.append(b64)
                                            success = True
                                            logger.info(f"Фото {i+1} получено из content")
                                            break
                                        else:
                                            logger.warning("Нет изображения в ответе")
                                    else:
                                        logger.warning("Нет choices в ответе")
                                else:
                                    text = await resp.text()
                                    logger.error(f"Ошибка {resp.status}: {text[:200]}")
                        except Exception as e:
                            logger.error(f"Попытка {attempt+1} не удалась: {e}")
                        await asyncio.sleep(1.5 * (2 ** attempt))
                    if not success:
                        logger.warning(f"Не удалось получить фото {i+1}")
                    await asyncio.sleep(0.5)

            else:
                # Для GPT Image 2 (medium/high) – пока не реализовано, можно закомментировать
                logger.warning(f"Модель {self.model_key} временно отключена. Используйте flash или pro.")
                # Временно возвращаем пустой список
                return []

        logger.info(f"Сгенерировано {len(images)} фото")
        return images