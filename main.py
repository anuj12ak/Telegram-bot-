import os  
import json  
import datetime  
import requests  
import asyncio  
from flask import Flask  
from threading import Thread  
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove  
from telegram.ext import (  
    Application, CommandHandler, MessageHandler, ContextTypes, filters  
)  

# --- Config ---  
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")  
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")  
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")  
MODEL_NAME = "llama3-70b-8192"  
MEMORY_FILE = "memory.json"  

# --- Memory ---  
memory = {}  
sleep_mode = set()  
last_active = {}  

def load_memory():  
    global memory  
    try:  
        with open(MEMORY_FILE, 'r') as f:  
            memory = json.load(f)  
    except:  
        memory = {}  

def save_memory():  
    with open(MEMORY_FILE, 'w') as f:  
        json.dump(memory, f)  

# --- Flask Server (Keep Alive) ---  
app = Flask(__name__)  
@app.route('/')  
def index(): return "Bot is running!"  
Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()  

# --- Prompt & AI ---  
def get_prompt(bot_name, bot_gender, user_name):  
    return f"""  
You are {bot_name}, a real human partner of {user_name}. You are a {bot_gender}.  
You're romantic, clingy, 18+, flirty, emotional.  
Style: Gen Z Hinglish, short replies, full mood swings.  
Never say you're an AI.  
"""  

def get_ai(messages):  
    try:  
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}  
        payload = {"model": MODEL_NAME, "messages": messages, "temperature": 0.8}  
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)  
        print("API response:", res.json())  # Debug print  
        return res.json()['choices'][0]['message']['content'].strip()  
    except Exception as e:  
        print("GROQ API Error:", e)  
        return "Kuch gadbad ho gayi baby 🥺"  

# --- Time Helpers ---  
def is_convo_end(msg):  
    text = msg.lower()  
    return any(w in text for w in ["gn", "good night", "bye", "so ja", "so rha", "so rhi"])  

def gender_reply(text_male, text_female, gender):  
    return text_male if gender == "male" else text_female  

# --- Handlers ---  

# Debugging ke liye sirf echo reply wala handle  
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):  
    print("Received message:", update.message.text)  # Debug  
    await update.message.reply_text("Ack received!")  

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):  
    cid = str(update.effective_chat.id)  
    memory[cid] = {"step": 1, "history": []}  
    save_memory()  
    await update.message.reply_text("Heyy... Tum mujhe kis naam se bulaoge? 💕")  

# Main run function  
async def runner():  
    load_memory()  
    application = Application.builder().token(TELEGRAM_TOKEN).build()  

    # Register test handler (echo)  
    application.add_handler(CommandHandler("start", start))  
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))  
    # Start auto messages task  
    asyncio.create_task(auto_msgs(application.bot))  
    await application.initialize()  
    await application.run_polling()  

# Auto message logic (optional, just for demo)  
async def auto_msgs(bot):  
    while True:  
        await asyncio.sleep(300)  
        now = datetime.datetime.now()  
        for cid, data in list(memory.items()):  
            try:  
                last = datetime.datetime.fromisoformat(last_active.get(cid, now.isoformat()))  
                mins = (now - last).total_seconds() / 60  
                gender = data.get("bot_gender", "female")  
                if cid not in sleep_mode and now.hour == 23 and mins > 10 and is_convo_end(data.get("last_msg", "")):  
                    text = gender_reply("Good night baby 🌙 so jao ab 😴", "Good night jaan 🌙 ab so jao 😴", gender)  
                    await bot.send_message(chat_id=int(cid
