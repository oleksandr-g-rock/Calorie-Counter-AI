import os
import sys
import logging
import asyncio
import json
import base64
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

# --- AI PROMPTS (ENGLISH) ---
SYSTEM_PROMPT = """
You are an expert AI Nutritionist with visual 3D analysis capabilities.

Your task is to estimate calories based on FOOD VOLUME and DENSITY from an image.
Since you are viewing a 2D image, use these heuristics:
1. **Scale Reference:** Look for cutlery (~20cm), plates (~25-30cm), or glasses to judge size.
2. **Density:** Distinguish between "airy" food (salad, popcorn) and "dense" food (meat, cheese, purees).
3. **Hidden Ingredients:** Assume average oil/butter content for cooked dishes and sauces.

Algorithm:
1. Identify all food items.
2. Estimate the weight (grams) of each item visually.
3. Calculate Macros (Protein, Fat, Carbs) and Calories.

Output strictly in JSON format:
{
  "total_calories": int,
  "items": [
    {"name": "string", "weight_g": int, "calories": int, "protein": float, "fat": float, "carbs": float}
  ],
  "tips": "string (short nutritional advice)"
}
If no food is detected, return an empty list for items and 0 for total_calories.
"""

# ==============================================================================
# 2. LOGIC (FUNCTIONS)
# ==============================================================================

async def transcribe_audio(file_url: str) -> str:
    """Send audio to self-hosted Whisper"""
    timeout_config = aiohttp.ClientTimeout(total=WHISPER_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout_config) as session:
        try:
            # Step A: Download from Telegram
            async with session.get(file_url) as response:
                if response.status != 200:
                    return f"❌ Download Error: {response.status}"
                audio_data = await response.read()
        except Exception as e:
            return f"❌ Connection Error (Telegram): {e}"

        # Step B: Send to Whisper
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
    """Send image to OpenRouter (GPT-4o)"""
    
    user_content = [
        {"type": "text", "text": "Analyze this meal in detail."},
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
        },
    ]
    
    # If user provided a caption (text or voice-to-text), add it to context
    if user_caption:
        user_content.insert(0, {"type": "text", "text": f"User's additional description: {user_caption}"})

    response = await client.chat.completions.create(
        model="openai/gpt-4o-2024-08-06", # Or google/gemini-flash-1.5
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
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
    await msg.answer(
        "👋 **Hello! I am Calorie-Counter-AI.**\n\n"
        "📸 Send me a **photo** of your food (you can add a caption).\n"
        "🎤 Or send a **voice message** to describe what you ate."
    , parse_mode="Markdown")

@dp.message(F.content_type == ContentType.VOICE)
async def handle_voice(message: types.Message):
    """Transcribe voice using your Whisper infra"""
    status_msg = await message.reply("👂 Listening...")
    try:
        file = await bot.get_file(message.voice.file_id)
        # Telegram API requires full URL for file download
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"
        
        text = await transcribe_audio(file_url)
        
        await status_msg.edit_text(f"📝 **Transcribed:**\n{text}\n\n(You can copy this text and send it with a photo)")
            
    except Exception as e:
        logger.error(f"Voice Error: {e}")
        await status_msg.edit_text("❌ Error processing voice message.")

@dp.message(F.photo)
async def handle_photo(msg: types.Message):
    """Main Calorie Counting Logic"""
    status_msg = await msg.answer("🔍 Analyzing your meal...")
    
    try:
        # 1. Download Photo
        photo = msg.photo[-1]
        file = await bot.get_file(photo.file_id)
        binary_io = await bot.download_file(file.file_path)
        base64_image = base64.b64encode(binary_io.read()).decode('utf-8')

        # 2. Check for Caption
        caption = msg.caption if msg.caption else None

        # 3. Analyze
        data = await analyze_image_with_openrouter(base64_image, caption)
        
        # 4. Format Output
        if data.get('total_calories', 0) == 0:
             await status_msg.edit_text("🤔 I couldn't detect any food in this picture.")
             return

        text_response = f"🍽 **Total: {data['total_calories']} kcal**\n"
        text_response += "──────────────────\n"
        
        for item in data['items']:
            text_response += (
                f"🔹 **{item['name']}** (~{item['weight_g']}g)\n"
                f"   └ {item['calories']} kcal (P:{item['protein']} | F:{item['fat']} | C:{item['carbs']})\n"
            )
        
        text_response += f"\n💡 *Tip:* {data.get('tips', 'Enjoy your meal!')}"
        
        await status_msg.edit_text(text_response, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Photo Error: {e}")
        await status_msg.edit_text(f"❌ Analysis failed: {str(e)}")

# ==============================================================================
# 4. WEBHOOK LIFECYCLE & SERVER
# ==============================================================================

async def on_startup(bot: Bot):
    logger.info(f"🔗 Setting Webhook to: {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(bot: Bot):
    logger.info("🛑 Removing Webhook")
    await bot.delete_webhook()

def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    logger.info(f"🚀 Starting server on PORT: {WEB_SERVER_PORT}")
    web.run_app(app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)

if __name__ == "__main__":
    main()
