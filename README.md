<div align="center">
<img src="https://img.icons8.com/color/200/avocado.png" alt="Calorie AI Logo" width="200"/>

# 🥗 Calorie-Counter-AI
**Your Smart Nutrition Assistant powered by Vision & Voice AI**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Aiogram](https://img.shields.io/badge/Aiogram-3.x-blueviolet.svg?logo=telegram)](https://docs.aiogram.dev/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![OpenRouter](https://img.shields.io/badge/AI-OpenRouter-74aa9c.svg)](https://openrouter.ai/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
</div>

---

## 🚀 The Mission
Stop guessing macros or manually logging food. **Calorie-Counter-AI** is a high-performance Telegram bot that "looks" at your food and tells you exactly what's on the plate.

Built with **Aiogram 3.x**, it combines **Vision Models** (like Gemini 2.0 Flash) with **Whisper Audio Transcription** to act as your personal nutritionist.

### 🎯 Why this bot?
Unlike rigid apps, **this is a conversation**.
1.  **See:** Snap a photo, and the AI estimates volume, weight, and calories using 3D logic.
2.  **Hear:** Send a voice note to describe ingredients or ask for advice.
3.  **Chat:** Ask general nutrition questions ("Is this healthy?") in plain text.

---

## ✨ Superpowers

* **👁️ Visual 3D Analysis:** Uses advanced Vision AI to estimate food volume based on reference objects (cutlery, plates).
* **🗣️ Voice-First:** Integrated with self-hosted **Whisper** to transcribe your meal descriptions or questions instantly.
* **🧠 Context Aware:** Knows the current date and time to give relevant advice (e.g., "It's late for a heavy meal").
* **🌍 Bilingual:** Automatically detects **English** or **Ukrainian** input and responds in the correct language.
* **⚡ Webhook Powered:** Zero-latency response using Aiohttp architecture.

---

## 🛠️ Quick Start (Docker)

The project is fully containerized. You can run it in seconds.

### 1. Build the Image
    docker build -t calorie-bot .

### 2. Run the Container
Replace the variables with your actual data.

    docker run -d \
      --name calorie-bot \
      -p 8000:8000 \
      -e TELEGRAM_TOKEN="123456:ABC-DEF1234ghIkl..." \
      -e BASE_URL="https://your-public-domain.com" \
      -e WHISPER_API_URL="http://whisper-service:9000/v1" \
      -e OPENROUTER_API_URL="sk-or-v1-..." \
      -e MODEL_NAME="google/gemini-2.0-flash-exp" \
      -e PORT=8000 \
      calorie-bot

---

## ⚙️ Configuration

Control the bot using Environment Variables.

| Variable | Required | Description |
| :--- | :---: | :--- |
| **TELEGRAM_TOKEN** | ✅ | Your bot token from [@BotFather](https://t.me/BotFather). |
| **BASE_URL** | ✅ | Your public HTTPS domain (SSL required for Webhooks). |
| **OPENROUTER_API_KEY** | ✅ | API Key from OpenRouter (to access LLMs). |
| **WHISPER_API_URL** | ✅ | Address of your Whisper backend (internal or cloud). |
| **MODEL_NAME** | ❌ | AI Model to use (Default: `google/gemini-2.0-flash-exp`). |
| **PORT** | ❌ | Internal app port (Default: `8000`). |

---

## 🔌 The "Backend Magic"

This bot is a **Gateway**. It orchestrates different AI services to provide a seamless experience.

**1. Vision & Reasoning (OpenRouter)**
We use OpenRouter to access top-tier models like **Gemini 2.0 Flash** or **GPT-4o**.
* *Task:* Analyze image pixels, estimate density/volume, calculate macros, and translate text.
* *Config:* Change `MODEL_NAME` to swap models without redeploying code.

**2. Ears (Whisper)**
We use a dedicated Whisper service for privacy and speed.
* *Task:* Transcribe voice notes into text before sending them to the LLM.
* *Setup:* Run a local docker container (e.g., `onerahmet/openai-whisper-asr-webservice`).

---

## 🏗️ Architecture Flow

1.  **User** sends a **Photo**, **Voice**, or **Text** 📤
2.  **Bot** receives Webhook ⚡
3.  **If Voice:** Bot sends audio to `WHISPER_API_URL` -> gets text 📝
4.  **If Photo:** Bot encodes image to Base64 🖼️
5.  **Bot** sends payload (Image + Text + Date) to `OPENROUTER_API_KEY` 🧠
6.  **AI** analyzes calories, healthiness, and detects language 🇺🇦/🇺🇸
7.  **Bot** formats the JSON response and replies to user 💬

---

## 🤝 Contributing
Got a cool idea? Maybe adding a database for history tracking or user profiles?
Fork the repo, make your changes, and open a **Pull Request**.

## 📄 License
This project is open-source and available under the **MIT License**.

---
<div align="center">
  Built with ❤️ for a healthier life.
</div>
