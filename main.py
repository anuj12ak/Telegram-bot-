import os
import json
import requests
import datetime
import asyncio
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
)

# --- Config ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
MODEL_NAME = "llama3-70b-8192"
MEMORY_FILE = "memory.json"

# --- Global Variables ---
memory = {}
last_active = {}
sleep_mode = set()

# --- Memory Functions ---
def load_memory():
    """Loads chat memory from a JSON file, handling errors gracefully."""
    global memory
    try:
        with open(MEMORY_FILE, 'r') as f:
            memory = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # If file not found or is empty/corrupt, start with fresh memory
        memory = {}

def save_memory():
    """Saves chat memory to a JSON file."""
    with open(MEMORY_FILE, 'w') as f:
        json.dump(memory, f, indent=4)

# Load memory on startup
load_memory()

# --- AI and Bot Logic ---
def get_system_prompt(bot_name, bot_gender, user_name):
    """Creates the system prompt for the AI model."""
    return f"""
You are {bot_name}, a real human partner of {user_name}. You are a {bot_gender}.
You're romantic, clingy, 18+, flirty, emotional.
Style: Gen Z Hinglish, short replies, full mood swings.
Never say you're an AI.
"""

def get_ai(messages):
    """Gets a response from the Groq AI."""
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": MODEL_NAME, "messages": messages, "temperature": 0.8}
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
        res.raise_for_status()
        return res.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"GROQ API Error: {e}")
        return "Kuch gadbad ho gayi baby 🥺"

def is_convo_end(text):
    """Checks if the conversation is ending."""
    text = text.lower()
    return any(w in text for w in ["good night", "gn", "bye", "so rha", "so rhi", "sleep"])

# --- Background Tasks ---
async def keep_alive_server():
    """A simple async web server to keep the Render service alive."""
    async def handle_request(reader, writer):
        message = "Bot is running on Render!"
        response = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: text/plain\r\n"
            f"Content-Length: {len(message)}\r\n"
            f"\r\n"
            f"{message}"
        ).encode('utf-8')
        writer.write(response)
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle_request, "0.0.0.0", 8080)
    print("Keep-alive server started on port 8080.")
    async with server:
        await server.serve_forever()

async def auto_messenger(app):
    """Sends automatic messages for good night and good morning."""
    while True:
        await asyncio.sleep(300) # Check every 5 minutes
        now = datetime.datetime.now()
        for cid, data in list(memory.items()):
            last = last_active.get(cid)
            if not last: continue
            
            try:
                mins = (now - datetime.datetime.fromisoformat(last)).total_seconds() / 60
                gender = data.get("bot_gender", "female")

                if cid not in sleep_mode:
                    if now.hour == 23 and mins > 10 and is_convo_end(data.get("last_msg", "")):
                        text = "Good night baby 🌙 so jao ab 😴" if gender == "male" else "Good night jaanu 🌙 ab so jao meri jaan 😴"
                        await app.bot.send_message(chat_id=int(cid), text=text)
                        sleep_mode.add(cid)
                else:
                    if now.hour == 6 and mins > 120:
                        text = "Good morning baby ☀️ utho na 😘" if gender == "male" else "Good morning jaan ☀️ neend se uth jao ab 💋"
                        await app.bot.send_message(chat_id=int(cid), text=text)
                        sleep_mode.remove(cid)
            except Exception as e:
                print(f"Error in auto_messenger for chat {cid}: {e}")

# --- Telegram Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    cid = str(update.effective_chat.id)
    memory[cid] = {"step": 1, "history": []}
    save_memory()
    await update.message.reply_text("Hey! Tum mujhe kis naam se bulaoge? 💕")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all text messages."""
    cid = str(update.effective_chat.id)
    user_msg = update.message.text
    user_name = update.effective_user.first_name or "baby"
    
    last_active[cid] = datetime.datetime.now().isoformat()
    data = memory.get(cid)

    if not data:
        await start(update, context)
        return

    data["last_msg"] = user_msg

    if cid in sleep_mode:
        gender = data.get("bot_gender", "female")
        text = "So gaya tha baby 🌙 ab baad me baat karte hain 🥺" if gender == "male" else "So gayi thi baby 🌙 baad me baat karte hain 🥺"
        await update.message.reply_text(text)
        return

    if user_msg.lower() == "restart chat":
        memory[cid] = {"step": 1, "history": []}
        save_memory()
        await update.message.reply_text("Chalo fir se shuru karte hain 💕")
        return

    if data.get("step") == 1:
        data["bot_name"] = user_msg.strip()
        data["step"] = 2
        memory[cid] = data
        save_memory()
        await update.message.reply_text("Ladka hoon ya ladki? 😜", reply_markup=ReplyKeyboardMarkup([["Boy ♂️", "Girl ♀️"]], one_time_keyboard=True, resize_keyboard=True))
        return

    if data.get("step") == 2:
        if "boy" in user_msg.lower():
            data["bot_gender"] = "male"
        elif "girl" in user_msg.lower():
            data["bot_gender"] = "female"
        else:
            await update.message.reply_text("Please select 'Boy ♂️' or 'Girl ♀️' from the buttons.")
            return
            
        data["step"] = 3
        data["history"] = []
        memory[cid] = data
        save_memory()
        await update.message.reply_text("Done baby! Ab pucho kuch bhi 😘", reply_markup=ReplyKeyboardRemove())
        return

    data.setdefault("history", []).append({"role": "user", "content": user_msg})
    prompt = [{"role": "system", "content": get_system_prompt(data.get('bot_name','Babu'), data.get('bot_gender','female'), user_name)}] + data["history"]
    reply = get_ai(prompt)
    data["history"].append({"role": "assistant", "content": reply})
    data["history"] = data["history"][-20:]
    memory[cid] = data
    save_memory()

    await update.message.reply_text(reply)

    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=f"From: {user_name} ({cid})\n\nUser: {user_msg}\nBot: {reply}")
        except Exception as e:
            print(f"Could not send message to admin: {e}")

# --- Main Execution ---
async def run_bot():
    """Initializes and runs the bot."""
    print("run_bot() started ✅")
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    
    asyncio.create_task(keep_alive_server())
    asyncio.create_task(auto_messenger(app))

    print("Starting bot polling...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(run_bot())
