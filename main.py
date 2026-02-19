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
from groq import AsyncGroq

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# --- ENV VARIABLES ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BASE_URL = os.getenv("BASE_URL")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GROQ_WHISPER_API_KEY = os.getenv("GROQ_WHISPER_API_KEY")

# --- MODEL CONFIGURATION ---
MODEL_NAME = os.getenv("MODEL_NAME", "google/gemini-2.0-flash-exp")

# --- DYNAMIC PORT CONFIGURATION ---
WEB_SERVER_PORT = int(os.getenv("PORT", 8000))
WEB_SERVER_HOST = "0.0.0.0"
WEBHOOK_PATH = "/webhook"

# Validation
if not TELEGRAM_TOKEN or not BASE_URL or not OPENROUTER_API_KEY or not GROQ_WHISPER_API_KEY:
    logger.error("❌ MISSING VARIABLES! Check tokens and API URLs.")
    sys.exit(1)

WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"
AUDIO_DOWNLOAD_TIMEOUT_SECONDS = 900

# --- INITIALIZATION ---
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)
groq_client = AsyncGroq(api_key=GROQ_WHISPER_API_KEY)

# --- UI TRANSLATIONS ---
UI_TEXTS = {
    "en": {
        "analyzing": "🔍 Thinking...",
        "no_food": "🤔 I couldn't understand the request or see any food.",
        "total": "Total",
        "verdict": "Health Verdict",
        "tip": "Recommendation",
        "kcal": "kcal"
    },
    "uk": {
        "analyzing": "🔍 Думаю...",
        "no_food": "🤔 Я не зрозумів запит або не бачу їжі.",
        "total": "ВСЬОГО",
        "verdict": "Вердикт нутриціолога",
        "tip": "Рекомендація",
        "kcal": "ккал"
    }
}

# --- AI PROMPT ---
SYSTEM_PROMPT_TEMPLATE = """
You are an expert AI Nutritionist. 
**Current Context:** {date_context}

**GOAL:** The user wants to eat **low calorie but nutritious** meals.

**LANGUAGE INSTRUCTION:** 1. Detect the language of the user's input.
2. **If Ukrainian:** Output ALL string values in Ukrainian. Return "lang": "uk".
3. **If English:** Output in English. Return "lang": "en".

**MODES:**
A. **IMAGE PROVIDED:**
   - Analyze Volume using cutlery/plates as scale.
   - Estimate Macros (Protein, Fat, Carbs).
   - Give a Health Check.

B. **TEXT ONLY (No Image):**
   - The user is asking for advice, a recipe, or a recommendation.
   - Ignore 'total_calories' and 'items' (leave empty/zero).
   - Put your answer in the 'tips' and 'health_verdict' fields.
   - Be helpful, specific, and concise.

**SAFETY & FORMATTING RULES:**
- **No Technical Tags:** Do not output tags like <tool_code> or <thinking>.
- **No Hallucinations:** Do not invent data. If you don't know, say so.
- **Conciseness:** Stop immediately after giving advice.
- **Formatting:** Do NOT use markdown bolding (asterisks like **text**). Telegram does not always render them well. Use plain text and emojis only.
- **Safety:** Decline to answer requests related to illegal acts or dangerous substances.

**Output strictly in JSON:**
{{
  "lang": "en" OR "uk",
  "total_calories": int,
  "total_macros": {{ "protein": int, "fat": int, "carbs": int }},
  "items": [
    {{"name": "string", "weight_g": int, "calories": int, "protein": float, "fat": float, "carbs": float}}
  ],
  "health_verdict": "string (Analysis or Main Answer - translated)",
  "tips": "string (Actionable advice or Additional Details - translated)"
}}
"""

# ==============================================================================
# 2. LOGIC (FUNCTIONS)
# ==============================================================================

async def transcribe_audio(file_url: str) -> str:
    """Download audio from Telegram and transcribe via Groq Whisper API."""
    timeout_config = aiohttp.ClientTimeout(total=AUDIO_DOWNLOAD_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout_config) as session:
        try:
            async with session.get(file_url) as response:
                if response.status != 200:
                    return f"Error: {response.status}"
                audio_data = await response.read()
        except Exception as e:
            return f"Connection Error: {e}"

    try:
        transcription = await groq_client.audio.transcriptions.create(
            file=("voice.ogg", audio_data),
            model="whisper-large-v3",
            temperature=0,
            response_format="verbose_json",
        )
        return transcription.text
    except Exception as e:
        logger.error(f"Groq Whisper Error: {e}")
        return "Groq Whisper Service Unavailable."

async def analyze_content_with_openrouter(text_input, base64_image=None):
    """Handles both Image+Text AND Text-Only requests."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d, %A, %H:%M")
    
    formatted_system_prompt = SYSTEM_PROMPT_TEMPLATE.format(date_context=date_str)

    user_content = []
    
    # Add text context (required)
    prompt_text = text_input if text_input else "Analyze this."
    user_content.append({"type": "text", "text": prompt_text})

    # Add image if present
    if base64_image:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
        })

    logger.info(f"🧠 Model: {MODEL_NAME} | Input: {'Image+Text' if base64_image else 'Text Only'}")

    response = await client.chat.completions.create(
        model=MODEL_NAME, 
        messages=[
            {"role": "system", "content": formatted_system_prompt},
            {"role": "user", "content": user_content}
        ],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

async def process_ai_response(msg: types.Message, data: dict, status_msg: types.Message):
    """Common logic to format and send AI response"""
    
    # 1. Determine Language
    lang_code = data.get("lang", "en") 
    if lang_code not in ["uk", "en"]: 
        lang_code = "en"
    ui = UI_TEXTS[lang_code]

    # 2. Check content type (Food Analysis vs Text Advice)
    total_cals = data.get('total_calories', 0)
    has_items = len(data.get('items', [])) > 0
    
    # Scenario A: It's a Text Advice (Zero calories, no items, but has text)
    if total_cals == 0 and not has_items:
        verdict = data.get('health_verdict', '')
        tips = data.get('tips', '')
        
        # If response is empty, show error
        if not verdict and not tips:
            await status_msg.edit_text(ui["no_food"])
            return

        # Show Consult Response
        response_text = f"👩‍⚕️ **{ui['verdict']}**\n{verdict}\n\n"
        if tips:
            response_text += f"💡 **{ui['tip']}**\n{tips}"
            
        await status_msg.edit_text(response_text, parse_mode="Markdown")
        return

    # Scenario B: Food Analysis (Calories found)
    macros = data.get('total_macros', {'protein': 0, 'fat': 0, 'carbs': 0})
    
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
    
    if data.get('tips'):
        text_response += f"\n💡 **{ui['tip']}:** {data.get('tips', '')}"
    
    await status_msg.edit_text(text_response, parse_mode="Markdown")

# ==============================================================================
# 3. HANDLERS
# ==============================================================================

@dp.message(Command("start"))
async def start_handler(msg: types.Message):
    await msg.answer(
        "👋 **Calorie-Counter-AI**\n\n"
        "📸 **Send Photo:** I'll count calories.\n"
        "🎤 **Send Voice:** Ask what to eat, or describe your meal.\n"
        "💬 **Send Text:** Ask any nutrition question.\n\n"
        "🇺🇦 Я розумію українську!"
    , parse_mode="Markdown")

@dp.message(F.content_type == ContentType.VOICE)
async def handle_voice(message: types.Message):
    # 1. Start processing (First message)
    transcript_msg = await message.reply("👂 ...")
    
    try:
        # 2. Transcribe
        file = await bot.get_file(message.voice.file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"
        
        transcribed_text = await transcribe_audio(file_url)
        
        if "Error" in transcribed_text:
            await transcript_msg.edit_text(f"❌ {transcribed_text}")
            return

        # 3. Show Transcription PERMANENTLY
        await transcript_msg.edit_text(f"📝 {transcribed_text}")
        
        # 4. Start AI Analysis in a NEW message
        ai_msg = await message.answer("🔍 ...")

        # 5. Ask AI (Text Only Mode)
        data = await analyze_content_with_openrouter(text_input=transcribed_text, base64_image=None)
        
        # 6. Fill the NEW message with AI response
        await process_ai_response(message, data, ai_msg)
            
    except Exception as e:
        logger.error(f"Voice Handler Error: {e}")
        try:
             await message.answer("❌ Error getting AI response.")
        except:
             pass

@dp.message(F.photo)
async def handle_photo(msg: types.Message):
    status_msg = await msg.answer("🔍 ...")
    
    try:
        # 1. Process Image
        photo = msg.photo[-1]
        file = await bot.get_file(photo.file_id)
        binary_io = await bot.download_file(file.file_path)
        base64_image = base64.b64encode(binary_io.read()).decode('utf-8')

        caption = msg.caption if msg.caption else None

        # 2. Ask AI (Image + Text Mode)
        data = await analyze_content_with_openrouter(text_input=caption, base64_image=base64_image)
        
        # 3. Format and Send Result
        await process_ai_response(msg, data, status_msg)
        
    except Exception as e:
        logger.error(f"Photo Handler Error: {e}")
        await status_msg.edit_text(f"❌ Error: {str(e)}")

@dp.message(F.text)
async def handle_text(msg: types.Message):
    """Handles plain text questions like 'Is this healthy?'"""
    status_msg = await msg.reply("🔍 ...")
    
    try:
        # Ask AI (Text Only Mode)
        data = await analyze_content_with_openrouter(text_input=msg.text, base64_image=None)
        
        # Format and Send Result
        await process_ai_response(msg, data, status_msg)
        
    except Exception as e:
        logger.error(f"Text Handler Error: {e}")
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
