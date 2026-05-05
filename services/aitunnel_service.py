import os
import base64
import logging
import aiohttp
import asyncio
import random
from config import Config

logger = logging.getLogger(__name__)

class AITunnelService:
    TIMEOUT_GEMINI = 90  # для каждого запроса

    def __init__(self, model_key: str = "flash"):
        self.api_key = Config.AITUNNEL_API_KEY
        self.base_url = "https://api.aitunnel.ru/v1"
        self.model_key = model_key
        info = Config.PACKAGE_MODELS.get(model_key, Config.PACKAGE_MODELS["flash"])
        self.model_name = info["api_model"]
        self.size = info.get("size", "1024x1024")
        # Таймаут (можно общий)
        self.timeout = self.TIMEOUT_GEMINI
        logger.info(f"AITunnelService init: model_key={model_key}, model={self.model_name}")

    async def _post_chat_completion(self, session, data_url: str, prompt: str) -> str | None:
        """Один запрос к /chat/completions, возвращает чистый base64 изображения или None."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
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

        for attempt in range(3):
            try:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if 'choices' in data and data['choices']:
                            message = data['choices'][0].get('message', {})
                            # Способ из PIXEL: ищем images
                            if 'images' in message and message['images']:
                                img_url = message['images'][0].get('image_url', {}).get('url')
                                if img_url and img_url.startswith('data:image/'):
                                    return img_url.split(',', 1)[1]
                            # Запасной вариант: content с data URL
                            if 'content' in message and message['content'].startswith('data:image'):
                                return message['content'].split(',', 1)[1]
                        logger.warning("Нет изображения в ответе")
                    else:
                        text = await resp.text()
                        logger.error(f"Ошибка {resp.status}: {text[:200]}")
            except Exception as e:
                logger.error(f"Попытка {attempt+1} не удалась: {e}")
            await asyncio.sleep(1.5 * (2 ** attempt))
        return None

    async def generate_package_photos(self, user_photo_paths: list, style_key: str, gender: str = None) -> list:
        """Генерация пакета из TOTAL_NEEDED фото (по умолчанию 8, можно изменить в коде)."""
        logger.info(f"Генерация пакета: model={self.model_key}, style={style_key}")

        style = Config.STYLES.get(style_key)
        if not style:
            raise ValueError(f"Неизвестный стиль: {style_key}")

        base_prompt = style["prompt"]
        subject = "this man" if gender == 'male' else "this woman" if gender == 'female' else "this person"
        prompt = base_prompt.replace("{token}", subject)
        # Добавляем указание на горизонтальный формат (как в PIXEL для Gemini)
        prompt += " Landscape orientation, horizontal composition, aspect ratio 16:9, wide format."

        # Берём первое существующее референсное фото
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
        TOTAL_NEEDED = 8   # изменяйте на 2 для теста, потом верните 8

        async with aiohttp.ClientSession() as session:
            for i in range(TOTAL_NEEDED):
                logger.info(f"Запрос {i+1}/{TOTAL_NEEDED}")
                b64 = await self._post_chat_completion(session, data_url, prompt)
                if b64:
                    images.append(b64)
                    logger.info(f"Фото {i+1} получено")
                else:
                    logger.warning(f"Фото {i+1} не получено")
                await asyncio.sleep(0.5)  # небольшая пауза между запросами

        logger.info(f"Сгенерировано {len(images)} фото")
        return images