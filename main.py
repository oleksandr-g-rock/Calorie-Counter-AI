import os
import sys
import logging
import asyncio
import json
import base64
from datetime import datetime
from aiohttp import web
import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ContentType
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from openai import AsyncOpenAI

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# --- ENV VARIABLES ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BASE_URL = os.getenv("BASE_URL")
WHISPER_API_URL = os.getenv("WHISPER_API_URL")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# --- MODEL CONFIGURATION ---
MODEL_NAME = os.getenv("MODEL_NAME", "google/gemini-3-flash-preview")

# --- DYNAMIC PORT CONFIGURATION ---
WEB_SERVER_PORT = int(os.getenv("PORT", 8000))
WEB_SERVER_HOST = "0.0.0.0"
WEBHOOK_PATH = "/webhook"

# Validation
if not TELEGRAM_TOKEN or not BASE_URL or not WHISPER_API_URL or not OPENROUTER_API_KEY:
    logger.error("❌ MISSING VARIABLES! Check tokens and API URLs.")
    sys.exit(1)

WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"
TRANSCRIPTION_ENDPOINT = f"{WHISPER_API_URL}/audio/transcriptions"
WHISPER_TIMEOUT_SECONDS = 900 

# --- INITIALIZATION ---
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# --- UI TRANSLATIONS ---
# Словник для заголовків бота
UI_TEXTS = {
    "en": {
        "analyzing": "🔍 Analyzing nutrients & health...",
        "no_food": "🤔 No food detected.",
        "total": "Total",
        "verdict": "Health Verdict",
        "tip": "Tip",
        "kcal": "kcal",
        "error": "Error"
    },
    "uk": {
        "analyzing": "🔍 Аналізую склад та корисність...",
        "no_food": "🤔 На фото їжі не виявлено.",
        "total": "ВСЬОГО",
        "verdict": "Вердикт нутриціолога",
        "tip": "Порада",
        "kcal": "ккал",
        "error": "Помилка"
    }
}

# --- AI PROMPT ---
SYSTEM_PROMPT_TEMPLATE = """
You are an expert AI Nutritionist using 3D visual analysis.
**Current Context:** {date_context}

**GOAL:** The user wants to eat **low calorie but nutritious** meals.

**LANGUAGE INSTRUCTION:** 1. Detect the language of the user's caption/voice.
2. **If Ukrainian:** Output ALL string values (names, verdict, tips) in Ukrainian. Return "lang": "uk".
3. **If English or No Text:** Output in English. Return "lang": "en".

**TASKS:**
1. **Analyze Volume:** Use cutlery/plates as scale reference.
2. **Estimate Macros:** Calculate Protein, Fat, Carbs for the WHOLE meal.
3. **Health Check:** Is this a good meal for the current time of day? Is it nutrient-dense?

**Output strictly in JSON:**
{{
  "lang": "en" OR "uk",
  "total_calories": int,
  "total_macros": {{
      "protein": int, 
      "fat": int, 
      "carbs": int
  }},
  "items": [
    {{"name": "string (translated)", "weight_g": int, "calories": int, "protein": float, "fat": float, "carbs": float}}
  ],
  "health_verdict": "string (Is it healthy? Why? Max 2 sentences - translated)",
  "tips": "string (Actionable advice - translated)"
}}

If no food is detected, return empty items and 0 totals.
"""

# ==============================================================================
# 2. LOGIC (FUNCTIONS)
# ==============================================================================

async def transcribe_audio(file_url: str) -> str:
    """Send audio to self-hosted Whisper"""
    timeout_config = aiohttp.ClientTimeout(total=WHISPER_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout_config) as session:
        try:
            async with session.get(file_url) as response:
                if response.status != 200:
                    return f"❌ Download Error: {response.status}"
                audio_data = await response.read()
        except Exception as e:
            return f"❌ Connection Error: {e}"

        form_data = aiohttp.FormData()
        form_data.add_field('file', audio_data, filename='voice.ogg')
        form_data.add_field('model', 'whisper-1')
        form_data.add_field('response_format', 'text')

        try:
            async with session.post(TRANSCRIPTION_ENDPOINT, data=form_data) as resp:
                if resp.status == 200:
                    return await resp.text()
                else:
                    return f"❌ Whisper Error ({resp.status})"
        except Exception as e:
            logger.error(f"Whisper Error: {e}")
            return "❌ Whisper Service Unavailable."

async def analyze_image_with_openrouter(base64_image, user_caption=None):
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d, %A, %H:%M")
    
    formatted_system_prompt = SYSTEM_PROMPT_TEMPLATE.format(date_context=date_str)

    user_content = [
        {"type": "text", "text": "Analyze this meal strictly."},
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
        },
    ]
    
    if user_caption:
        user_content.insert(0, {"type": "text", "text": f"User's input: {user_caption}"})

    logger.info(f"🧠 Using Model: {MODEL_NAME} | Date: {date_str}")

    response = await client.chat.completions.create(
        model=MODEL_NAME, 
        messages=[
            {"role": "system", "content": formatted_system_prompt},
            {"role": "user", "content": user_content}
        ],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

# ==============================================================================
# 3. HANDLERS
# ==============================================================================

@dp.message(Command("start"))
async def start_handler(msg: types.Message):
    # Bilingual start message
    await msg.answer(
        "👋 **Calorie-Counter-AI**\n\n"
        "🇺🇸 Send a photo. I speak English by default.\n"
        "🇺🇦 Надішліть фото. Якщо напишете/скажете українською, я відповім українською!\n\n"
        "📸 Photo + Caption = Better Accuracy."
    , parse_mode="Markdown")

@dp.message(F.content_type == ContentType.VOICE)
async def handle_voice(message: types.Message):
    status_msg = await message.reply("👂 ...")
    try:
        file = await bot.get_file(message.voice.file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"
        
        text = await transcribe_audio(file_url)
        
        await status_msg.edit_text(f"📝 **Note:**\n{text}\n\n(Now send the photo / Тепер надішли фото)")
            
    except Exception as e:
        logger.error(f"Voice Error: {e}")
        await status_msg.edit_text("❌ Error processing voice.")

@dp.message(F.photo)
async def handle_photo(msg: types.Message):
    # Початкове повідомлення нейтральне, поки не знаємо мову
    status_msg = await msg.answer("🔍 ...")
    
    try:
        photo = msg.photo[-1]
        file = await bot.get_file(photo.file_id)
        binary_io = await bot.download_file(file.file_path)
        base64_image = base64.b64encode(binary_io.read()).decode('utf-8')

        caption = msg.caption if msg.caption else None

        # Call AI
        data = await analyze_image_with_openrouter(base64_image, caption)
        
        # --- LANGUAGE SWITCHER LOGIC ---
        # Отримуємо код мови з відповіді AI (uk або en), дефолт en
        lang_code = data.get("lang", "en") 
        if lang_code not in ["uk", "en"]: 
            lang_code = "en" # Fallback
            
        # Вибираємо правильні слова з нашого словника
        ui = UI_TEXTS[lang_code]

        # Перевірка чи є їжа
        if data.get('total_calories', 0) == 0:
             await status_msg.edit_text(ui["no_food"])
             return

        macros = data.get('total_macros', {'protein': 0, 'fat': 0, 'carbs': 0})
        
        # Формуємо відповідь мовою юзера
        text_response = (
            f"🍽 **{ui['total']}: {data['total_calories']} {ui['kcal']}**\n"
            f"🥩 P: {macros['protein']}g | 🥑 F: {macros['fat']}g | 🍞 C: {macros['carbs']}g\n"
            f"──────────────────\n"
        )
        
        for item in data['items']:
            text_response += f"🔹 {item['name']} (~{item['weight_g']}g)\n"
            text_response += f"   └ {item['calories']} {ui['kcal']}\n"
        
        text_response += f"\n📊 **{ui['verdict']}:**\n"
        text_response += f"{data.get('health_verdict', 'N/A')}\n"
        
        text_response += f"\n💡 **{ui['tip']}:** {data.get('tips', '')}"
        
        await status_msg.edit_text(text_response, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Photo Error: {e}")
        await status_msg.edit_text(f"❌ Error: {str(e)}")


# ==============================================================================
# 4. SERVER
# ==============================================================================

async def on_startup(bot: Bot):
    logger.info(f"🔗 Webhook: {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()

def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    logger.info(f"🚀 Server running on PORT: {WEB_SERVER_PORT}")
    web.run_app(app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)

if __name__ == "__main__":
    main()
