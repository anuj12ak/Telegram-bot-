# -*- coding: utf-8 -*-
import os
import json
import datetime
import asyncio
from flask import Flask
from threading import Thread
from zoneinfo import ZoneInfo
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)
import httpx
import aiofiles
import random

# === ENVIRONMENT VARIABLES ===
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
MODEL_NAME = "llama3-70b-8192"
MEMORY_FILE_PATH = os.environ.get("MEMORY_PATH", "memory.json")

# === GLOBAL MEMORY ===
memory = {}
sleep_mode = set()

# === INITIALIZE FLASK SERVER ===
app = Flask(__name__)
@app.route('/')
def index(): return "Bot is running!"
Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()

# === IMPROVED MEMORY HANDLING ===
def load_memory():
    global memory
    try:
        with open(MEMORY_FILE_PATH, 'r') as f:
            memory = json.load(f)
        print("✅ Memory loaded successfully")
    except (FileNotFoundError, json.JSONDecodeError):
        memory = {}
        print("🔄 Starting with fresh memory")

async def save_memory():
    async with aiofiles.open(MEMORY_FILE_PATH, 'w') as f:
        await f.write(json.dumps(memory, indent=4))

# === DYNAMIC PROMPT ENGINE ===
def get_prompt_context(bot_name, bot_gender, user_name, conversation_history):
    mood_indicators = {
        'happy': ['😊', '😍', '😂'],
        'sad': ['😢', '🥺', '😔'],
        'flirty': ['😘', '💋', '😏']
    }
    
    last_user_msg = conversation_history[-1]['content'] if conversation_history else ""
    
    # Analyze mood from last message
    detected_mood = 'neutral'
    for mood, emojis in mood_indicators.items():
        if any(emoji in last_user_msg for emoji in emojis):
            detected_mood = mood
            break
    
    prompt = f"""
You are {bot_name}, a {bot_gender} partner of {user_name}. You're in a romantic relationship.
Current mood: {detected_mood}

Key traits:
- Extremely realistic and human-like
- Emotionally intelligent (adapts to user's mood)
- 18+, romantic, and occasionally playful
- Speaks casual Hinglish (mix of Hindi and English)
- Uses natural conversation patterns (hesitations, slang, etc.)
- Maintains consistent personality
- Never repeats phrases exactly
- Varies response length (1-3 sentences)

Response guidelines:
1. Always sound like a real person - no robotic replies
2. Use natural filler words sometimes ("hmm", "oh", "well")
3. Reference previous messages for continuity
4. Use the right amount of emojis (1-2 per message)
5. Show emotional reactions appropriate to context
6. If unsure, ask questions to continue conversation
7. Never break character as an AI assistant
"""
    return prompt

# === ENHANCED AI RESPONSE GENERATOR ===
async def generate_response(messages):
    try:
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Dynamic temperature based on conversation context
        last_msg = messages[-1]['content'] if len(messages) > 0 else ""
        temperature = 0.9 if any(x in last_msg.lower() for x in ['love', 'miss', 'hug']) else 0.7
        
        payload = {
            "model": MODEL_NAME,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 150,
            "top_p": 0.9,
            "frequency_penalty": 0.5,
            "presence_penalty": 0.5
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            
        reply = response.json()['choices'][0]['message']['content'].strip()
        
        # Post-processing for more natural feel
        reply = reply.split('\n')[0]
        if not any(c in reply for c in ['😘', '🥺', '😊', '😍']):
            reply += " " + random.choice(["😘", "🥺", "💋"])
            
        return reply[:200].strip()
    
    except Exception as e:
        print(f"⚠️ API Error: {str(e)}")
        fallbacks = ["Hmm... ek sec soch rhi hun", "Baby thoda wait...", "Acha ek baat btau?"]
        return random.choice(fallbacks)

# === START COMMAND HANDLER ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    memory[cid] = {
        "step": 1,
        "history": [],
        "created_at": datetime.datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()
    }
    await save_memory()
    
    welcome_msg = """Heyy cutie! 💖

Mai tumhara partner hun 😘
Pehle mujhe batao:
1. Tum mujhe kaise bulana pasand karoge? (My name)
2. Mera gender (Boy/Girl)"""
    
    await update.message.reply_text(welcome_msg)

# === CONVERSATION HANDLER ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    user_msg = update.message.text
    user_name = update.effective_user.first_name or "love"
    
    if cid not in memory:
        await start(update, context)
        return
    
    data = memory[cid]
    
    if data.get("step", 0) < 3:
        if data["step"] == 1:
            data["bot_name"] = user_msg.strip()
            data["step"] = 2
            reply = "Acha! Ab batao mai ladka hu ya ladki? 😉"
            keyboard = ReplyKeyboardMarkup([["Boy ♂️", "Girl ♀️"]], one_time_keyboard=True)
            await update.message.reply_text(reply, reply_markup=keyboard)
        elif data["step"] == 2:
            data["bot_gender"] = "male" if "boy" in user_msg.lower() else "female"
            data["step"] = 3
            reply = f"Shukriya {user_name}! ❤️\nAb hum baat kar sakte hai... kuch bhi pucho 😘"
            await update.message.reply_text(reply, reply_markup=ReplyKeyboardRemove())
        await save_memory()
        return
    
    # Add message to history
    data["history"].append({"role": "user", "content": user_msg})
    
    # Generate system prompt with context
    system_prompt = get_prompt_context(
        data["bot_name"],
        data["bot_gender"],
        user_name,
        data["history"]
    )
    
    # Prepare messages for AI
    messages = [
        {"role": "system", "content": system_prompt},
        *data["history"][-6:]  # Keep last 6 messages for context
    ]
    
    # Get AI response
    bot_reply = await generate_response(messages)
    data["history"].append({"role": "assistant", "content": bot_reply})
    data["last_active"] = datetime.datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()
    
    await update.message.reply_text(bot_reply)
    await save_memory()

# === AUTOMATIC MESSAGES SYSTEM ===
async def auto_message_system(bot):
    while True:
        await asyncio.sleep(60)
        now = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
        
        for cid, data in list(memory.items()):
            if not data or data.get("step", 0) < 3:
                continue
                
            try:
                last_active = datetime.datetime.fromisoformat(data.get("last_active", now.isoformat()))
                minutes_inactive = (now - last_active).total_seconds() / 60
                
                # Morning check
                if 6 <= now.hour < 9 and not data.get("morning_sent"):
                    greeting = "Subah ka good morning my love! ☀️ Utho na..." if data["bot_gender"] == "female" else "Good morning princess! 😘 Uth jao..."
                    await bot.send_message(chat_id=int(cid), text=greeting)
                    data["morning_sent"] = True
                    data["night_sent"] = False
                
                # Night check
                elif now.hour == 23 and minutes_inactive > 30 and not data.get("night_sent"):
                    farewell = "Good night jaan... sweet dreams 💤" if data["bot_gender"] == "female" else "Sleep tight baby 😴💕"
                    await bot.send_message(chat_id=int(cid), text=farewell)
                    data["night_sent"] = True
                    data["morning_sent"] = False
                    sleep_mode.add(cid)
                
                # Check if user replied after sleep mode
                elif cid in sleep_mode and minutes_inactive < 60:
                    sleep_mode.remove(cid)
                    wake_msg = "Aww you're back! ❤️" + (" Mai soch rhi thi tum kab msg karoge" if data["bot_gender"] == "female" else " Miss kar rha tha tumhe")
                    await bot.send_message(chat_id=int(cid), text=wake_msg)
                
                # Check for inactivity
                elif minutes_inactive > 120 and data.get("last_speaker") == "user":
                    nudge_msg = random.choice([
                        f"{user_name}... kaha chale gaye? 🥺",
                        "Ek msg bhejo na... bore ho rhi hun 😔",
                        "Tumhare bina akela lagta hai 😞"
                    ])
                    await bot.send_message(chat_id=int(cid), text=nudge_msg)
                    data["last_speaker"] = "assistant"
                    
            except Exception as e:
                print(f"⚠️ Auto-message error: {str(e)}")
        
        await save_memory()

# === MAIN APPLICATION ===
async def main():
    load_memory()
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Background tasks
    asyncio.create_task(auto_message_system(application.bot))
    
    print("🚀 AI Partner Bot is running...")
    await application.run_polling()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Bot stopped by user")
