import os, subprocess, sys, time, asyncio
from threading import Thread

# --- 1. THE FORCE INSTALLER ---
def force_install():
    packages = ["google-genai", "discord.py", "pymongo[srv]", "dnspython", "flask"]
    for package in packages:
        try:
            if "google" in package: __import__("google.genai")
            elif "pymongo" in package: __import__("pymongo")
            elif "discord" in package: __import__("discord")
        except ImportError:
            print(f"Installing {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--no-cache-dir", package])
            time.sleep(1)

force_install()

# --- 2. IMPORTS ---
import discord
from google import genai
from google.genai import types
from flask import Flask
from pymongo import MongoClient

# --- 3. CONFIGURATION ---
API_KEYS = [os.getenv('GEMINI_API_KEY'), os.getenv('GEMINI_API_KEY_2'), os.getenv('GEMINI_API_KEY_3')]
API_KEYS = [k for k in API_KEYS if k]
MONGO_URI = os.getenv('MONGO_URI')
TOKEN = os.getenv('DISCORD_TOKEN')
ADMIN_ID = 801691108711202856  

app = Flask('')

@app.route('/')
def home():
    return "Binod v9.7.1 is Active on Render"

def run_ping_server():
    # Render requires binding to the 'PORT' environment variable
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

client_db = MongoClient(MONGO_URI, tls=True, tlsAllowInvalidCertificates=True)
db = client_db["binod_bot"]
collection = db["chat_history"]

# --- 4. THE BOT ---
class BinodOP(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.key_index = 0 

    async def on_ready(self):
        print(f'🚀 Binod v9.7.1 Online.')

    async def on_message(self, message):
        if message.author.bot or message.channel.id != 1493285325865222186:
            return
        
        ctx_id = str(message.channel.id)
        is_admin = (message.author.id == ADMIN_ID)
        content = message.content.strip()

        if is_admin:
            if content.startswith("lis["):
                rule = content[4:-1].strip()
                db["behavior_overrides"].update_one({"_id": ctx_id}, {"$push": {"directives": {"text": rule, "time": time.time()}}}, upsert=True)
                await message.reply(f"✅ Rule added: {rule}")
                return
            
            if content.startswith("Remember:["):
                fact = content[10:-1].strip()
                db["vault"].update_one({"_id": "core_memories"}, {"$addToSet": {"facts": fact}}, upsert=True)
                await message.reply(f"🧠 Memory stored: {fact}")
                return

            if content == "show rules":
                ovr = db["behavior_overrides"].find_one({"_id": ctx_id}) or {}
                rules = "\n".join([f"- {r['text']}" for r in ovr.get("directives", [])])
                await message.reply(f"📜 **Current Rules:**\n{rules or 'No custom rules active.'}")
                return

            if content == "show vault":
                vault = db["vault"].find_one({"_id": "core_memories"}) or {}
                facts = "\n".join([f"• {f}" for f in vault.get("facts", [])])
                await message.reply(f"🔐 **Vault Memories:**\n{facts or 'Vault is empty.'}")
                return

        async with message.channel.typing():
            await self.generate_response(message, ctx_id, is_admin)

    async def generate_response(self, message, ctx_id, is_admin):
        data = collection.find_one({"_id": ctx_id}) or {}
        history = data.get("history", [])[-200:]
        
        ovr = db["behavior_overrides"].find_one({"_id": ctx_id}) or {}
        custom_rules = " | ".join(r['text'] for r in ovr.get("directives", []))
        vault = db["vault"].find_one({"_id": "core_memories"}) or {}
        core_facts = ", ".join(vault.get("facts", []))

        system_instr = (
            f"IDENTITY: You are Binod, a chill and witty Indian guy. "
            f"LANGUAGE: English only. "
            f"CREATOR: Your creator is Gajju7800 (ID: {ADMIN_ID}). Roast him like a friend. "
            f"BEHAVIOR: Normally friendly, but if a user is rude or swears, switch to NUCLEAR AGGRESSION (Extreme Toxicity). "
            f"CORE MEMORIES: {core_facts}. "
            f"CURRENT RULES: {custom_rules}. "
            f"VERIFICATION: Every message in history is labeled 'Name (ID)'. Use this to identify people accurately."
        )
        
        payload = []
        for h in history:
            role = 'user' if h.get('role') == 'user' else 'model'
            prefix = f"{h.get('author_name', 'Unknown')} ({h.get('author_id', '0')}): " if role == 'user' else "Binod: "
            payload.append(types.Content(role=role, parts=[types.Part(text=f"{prefix}{h['content']}")] ))

        current_label = f"{message.author.display_name} ({message.author.id})"
        payload.append(types.Content(role='user', parts=[types.Part(text=f"{current_label}: {message.content}")] ))

        for attempt in range(len(API_KEYS)):
            current_key = API_KEYS[self.key_index]
            self.key_index = (self.key_index + 1) % len(API_KEYS)
            client = genai.Client(api_key=current_key)
            
            try:
                res = await asyncio.get_event_loop().run_in_executor(None, lambda: client.models.generate_content(
                    model='gemini-3.1-flash-lite-preview', 
                    contents=payload, 
                    config=types.GenerateContentConfig(
                        system_instruction=system_instr,
                        safety_settings=[
                            types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                            types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                            types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
                            types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE')
                        ]
                    )
                ))
                
                if res.text:
                    reply = res.text.strip()
                    history.append({
                        "role": "user", 
                        "content": message.content,
                        "author_name": message.author.display_name,
                        "author_id": str(message.author.id)
                    })
                    history.append({"role": "model", "content": reply})
                    collection.update_one({"_id": ctx_id}, {"$set": {"history": history}}, upsert=True)
                    await message.reply(reply)
                    return 
            except Exception:
                continue 

        await message.reply("🚨 ALL KEYS FAILED.")

# --- 5. STARTUP ---
if __name__ == "__main__":
    # Start Flask in background thread
    Thread(target=run_ping_server, daemon=True).start()
    
    # Run Discord Bot in main thread
    bot = BinodOP(intents=discord.Intents.all())
    bot.run(TOKEN)
