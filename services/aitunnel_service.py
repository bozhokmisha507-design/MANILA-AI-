import os
import base64
import logging
import aiohttp
import asyncio
import random
from config import Config

logger = logging.getLogger(__name__)

class AITunnelService:
    TIMEOUT = 90

    def __init__(self, model_key: str = "flash"):
        info = Config.PACKAGE_MODELS.get(model_key, Config.PACKAGE_MODELS["flash"])
        self.api_key = Config.AITUNNEL_API_KEY
        self.base_url = "https://api.aitunnel.ru/v1"
        self.model_name = info["api_model"]
        self.batch_size = info.get("batch_size", 8)
        logger.info(f"AITunnelService init: model={self.model_name}, batch={self.batch_size}")

    async def generate_package_photos(self, user_photo_paths: list, style_key: str, gender: str = None) -> list:
        logger.info(f"Генерация пакета: style={style_key}, gender={gender}, batch={self.batch_size}")

        style = Config.STYLES.get(style_key)
        if not style:
            raise ValueError(f"Неизвестный стиль: {style_key}")

        # Берём промпт
        prompt = style.get('prompt', '')
        if gender == 'male':
            prompt = prompt.replace("{token}", "this man")
        elif gender == 'female':
            prompt = prompt.replace("{token}", "this woman")
        else:
            prompt = prompt.replace("{token}", "this person")

        # Добавляем ориентацию, требование лица и ЗАПРЕТ КОЛЛАЖА
        if "Landscape" not in prompt:
            prompt += " Landscape orientation, horizontal composition, aspect ratio 16:9, wide format."
        if "face clearly visible" not in prompt:
            prompt += " Face clearly visible, exact facial features as in the reference image."
        # Ключевая строка против коллажей
        prompt += " One single image, no collages, no grids, no multiple frames. Single photograph."

        logger.info(f"Промпт: {prompt[:300]}...")

        # Референсное фото
        ref_photo = next((p for p in user_photo_paths if os.path.exists(p)), None)
        if not ref_photo:
            logger.error("Нет доступных фото пользователя")
            return []

        with open(ref_photo, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
            data_url = f"data:image/jpeg;base64,{image_b64}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        images = []

        async with aiohttp.ClientSession() as session:
            for i in range(self.batch_size):
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
                logger.info(f"Запрос {i+1}/{self.batch_size} (chat)")
                success = False
                for attempt in range(3):
                    try:
                        async with session.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=self.TIMEOUT) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if 'choices' in data and data['choices']:
                                    message = data['choices'][0].get('message', {})
                                    if 'images' in message and message['images']:
                                        img_url = message['images'][0].get('image_url', {}).get('url')
                                        if img_url and img_url.startswith('data:image/'):
                                            b64 = img_url.split(',')[1]
                                            images.append(b64)
                                            success = True
                                            logger.info(f"Фото {i+1} получено (images)")
                                            break
                                    if 'content' in message and isinstance(message['content'], str) and message['content'].startswith('data:image'):
                                        b64 = message['content'].split(',')[1]
                                        images.append(b64)
                                        success = True
                                        logger.info(f"Фото {i+1} получено (content)")
                                        break
                            else:
                                text = await resp.text()
                                logger.error(f"Ошибка {resp.status}: {text[:200]}")
                    except Exception as e:
                        logger.error(f"Попытка {attempt+1}: {e}")
                    await asyncio.sleep(1.5 * (2 ** attempt))
                if not success:
                    logger.warning(f"Фото {i+1} не получено")
                await asyncio.sleep(0.3)

        logger.info(f"Сгенерировано {len(images)} фото")
        return images