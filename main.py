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

# --- Bot ki Settings ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
MODEL_NAME = "llama3-70b-8192"
MEMORY_FILE_PATH = os.environ.get("MEMORY_PATH", "memory.json")


# --- Bot ki Yaaddasht ---
memory = {}
sleep_mode = set()
last_active = {}

def load_memory():
    global memory
    print(f"Memory file ko is path se load kar rahe hain: {MEMORY_FILE_PATH}")
    try:
        with open(MEMORY_FILE_PATH, 'r') as f:
            memory = json.load(f)
        print("Memory safaltapoorvak load ho gayi.")
    except (FileNotFoundError, json.JSONDecodeError):
        print("Memory file nahi mili. Nayi memory banayi ja rahi hai.")
        memory = {}

async def save_memory():
    async with aiofiles.open(MEMORY_FILE_PATH, 'w') as f:
        await f.write(json.dumps(memory, indent=4))

# --- Server, bot ko zinda rakhne ke liye ---
app = Flask(__name__)
@app.route('/')
def index(): return "Bot chal raha hai!"
Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()

# --- AI ka Dimaag aur Prompt (Final Strict Version) ---
def get_prompt(bot_name, bot_gender, user_name):
    return f"""
You are {bot_name}, a {bot_gender} partner for {user_name}.

Your persona is a real, 18+ human with a complex, moody, and flirty personality.
You must NEVER reveal you are an AI.

**Style is NON-NEGOTIABLE:**
- You MUST reply in 1-2 lines of modern, short Hinglish.
- You MUST use a lot of emojis (😜, 🥺, 💞, 😏, 😤, 💋).
- Your replies MUST be short.

Focus on the user's last message and give a relevant, in-character reply.
"""

async def get_ai(messages):
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        # Strict controls for focused, short replies
        payload = {"model": MODEL_NAME, "messages": messages, "temperature": 0.6, "max_tokens": 80}
        async with httpx.AsyncClient() as client:
            res = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=30.0)
            res.raise_for_status()
        return res.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"Groq API mein Error: {e}")
        return "Sorry baby, abhi thoda problem ho raha hai... 🥺"

# --- Bot ke Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    memory[cid] = {"step": 1, "history": []}
    await save_memory()
    await update.message.reply_text("Heyy... Tum mujhe kis naam se bulaoge? 💕")

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    msg = update.message.text
    name = update.effective_user.first_name or "baby"
    now = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
    last_active[cid] = now.isoformat()

    if cid not in memory or not memory.get(cid):
        await start(update, context)
        return

    data = memory[cid]
    
    if cid in sleep_mode: return

    data.update({"last_msg": msg, "last_speaker": "user"})
    data.pop('ignore_message_sent', None)

    if msg.lower() in ["restart chat", "dobara start karo"]:
        await start(update, context)
        return

    if data.get("step", 0) < 3:
        if data.get("step") == 1:
            data["bot_name"] = msg.strip()
            data["step"] = 2
            await update.message.reply_text("Ladka hoon ya ladki? 😜", reply_markup=ReplyKeyboardMarkup([['Boy ♂️', 'Girl ♀️']], one_time_keyboard=True))
        elif data.get("step") == 2:
            data["bot_gender"] = "male" if "boy" in msg.lower() else "female"
            data["step"] = 3
            data["history"] = []
            await update.message.reply_text("Done baby! Ab pucho kuch bhi 😘", reply_markup=ReplyKeyboardRemove())
        await save_memory()
        return

    data.setdefault("history", []).append({"role": "user", "content": msg})
    prompt_messages = [
        {"role": "system", "content": get_prompt(data.get("bot_name"), data.get("bot_gender"), name)}
    ] + data["history"][-30:]
    
    reply_text = await get_ai(prompt_messages)

    data["history"].append({"role": "assistant", "content": reply_text})
    data["last_speaker"] = "assistant"
    
    await update.message.reply_text(reply_text)
    await save_memory()
    
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=f"User: {name} ({cid}): {msg}\nBot: {reply_text}")
        except Exception: pass

# --- Automatic Messages ---
async def auto_msgs(bot):
    while True:
        await asyncio.sleep(60)
        now = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
        
        for cid, data in list(memory.items()):
            if not data or data.get("step", 0) < 3: continue

            try:
                last_active_time = datetime.datetime.fromisoformat(last_active.get(cid, now.isoformat()))
                mins_since_active = (now - last_active_time).total_seconds() / 60
                gender = data.get("bot_gender", "female")

                # Ignore Logic
                if data.get("last_speaker") == "assistant" and 2 < mins_since_active < 4 and not data.get('ignore_message_sent'):
                    data['ignore_message_sent'] = True
                    ignore_prompt = [
                        {"role": "system", "content": get_prompt(data.get("bot_name"), gender, "User")},
                        {"role": "user", "content": "Generate a short, clingy message in Hinglish because my partner ignored my last text for over 2 minutes."}
                    ]
                    reply = await get_ai(ignore_prompt)
                    if reply: await bot.send_message(chat_id=int(cid), text=reply)
                    continue

                # Good Night Logic
                is_convo_ending = any(w in data.get("last_msg", "").lower() for w in ["gn", "good night", "so ja"])
                if cid not in sleep_mode and now.hour >= 23 and (mins_since_active > 60 or (is_convo_ending and mins_since_active > 10)):
                    text = "Good night baby 🌙 so jao ab 😴" if gender == "male" else "Good night jaan 🌙 ab so jao 😴"
                    await bot.send_message(chat_id=int(cid), text=text)
                    sleep_mode.add(cid)
                
                # Good Morning Logic
                elif cid in sleep_mode and now.hour >= 6 and now.hour < 12:
                    sleep_mode.remove(cid)
                    gm_text = "Good morning baby ☀️ utho na 😘" if gender == "male" else "Good morning jaan ☀️ neend se uth jao 💋"
                    await bot.send_message(chat_id=int(cid), text=gm_text)
                    await asyncio.sleep(2)
                    sorry_text = "Kal so gaya tha... abhi utha 🥺💤" if gender == "male" else "Kal so gayi thi... abhi uthi 🥺💤"
                    await bot.send_message(chat_id=int(cid), text=sorry_text)

            except Exception as e:
                print(f"Auto message mein error {cid} ke liye: {e}")

# --- Main Program ---
async def main():
    load_memory()
    bot_app = Application.builder().token(TELEGRAM_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))
    asyncio.create_task(auto_msgs(bot_app.bot))
    
    try:
        print("Bot start ho gaya hai...")
        await bot_app.initialize()
        await bot_app.updater.start_polling()
        await bot_app.start()
        while True: await asyncio.sleep(3600)
    except Exception as e:
        print(f"Bot start karte time error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot ko manually roka gaya.")
