import time
import requests
import random
import string
import asyncio
import os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- 🛠 CONFIGURATION ---
API_ID = int(os.getenv("API_ID", "33917975"))
# 👇 Yahan galti thi, bracket hata diya hai
API_HASH = os.getenv("API_HASH", "9ded8160307386acef2451d464e7a9b9")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# 🔥 YOUR DEPLOYER WEBSITE CONFIG
DEPLOYER_URL = "https://uptimebot-rvni.onrender.com/api/add_account" 
ADMIN_PANEL_URL = "https://uptimebot-rvni.onrender.com/admin"
ADMIN_SECRET = "sudeep_super_secret_key"

if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN missing! Add it to Heroku Config Vars.")

app = Client("render_pro_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

MAIL_TM_URL = "https://api.mail.tm"
RENDER_API_URL = "https://api.render.com/v1/owners"

# Sessions for Auto Flow and Manual Flow
user_sessions = {}
manual_sessions = {}

# --- 📧 MAIL FUNCTIONS ---
def get_mailtm_account():
    try:
        domain_resp = requests.get(f"{MAIL_TM_URL}/domains")
        if domain_resp.status_code != 200: return None
        
        domains = domain_resp.json()['hydra:member']
        if not domains: return None
        
        domain = random.choice(domains)['domain']
        username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        email = f"{username}@{domain}"
        password = "RenderPass" + ''.join(random.choices(string.digits, k=4)) + "!"
        
        create_resp = requests.post(f"{MAIL_TM_URL}/accounts", json={"address": email, "password": password})
        if create_resp.status_code == 201:
            token_resp = requests.post(f"{MAIL_TM_URL}/token", json={"address": email, "password": password})
            return email, password, token_resp.json()['token']
    except Exception as e:
        print(f"Mail Gen Error: {e}")
    return None, None, None

# --- 🤖 BOT COMMANDS ---

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "👋 **Welcome to Render Pro Bot!**\n\n"
        "I will automate your Render Account Setup.\n"
        "1. Generate High-Quality Email.\n"
        "2. Extract Owner ID from API Key.\n"
        "3. **Auto-Add to Deployer Panel**.\n\n"
        "👇 **Choose an option:**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Go to Register Page", url="https://dashboard.render.com/register")],
            [InlineKeyboardButton("⚡ Generate Fresh Email", callback_data="gen_mail")],
            [InlineKeyboardButton("➕ Manually Add to Panel", callback_data="manual_add_start")]
        ])
    )

# --- ✍️ MANUAL ADD FLOW ---
@app.on_callback_query(filters.regex("manual_add_start"))
async def manual_add_start(client, callback_query):
    chat_id = callback_query.message.chat.id
    manual_sessions[chat_id] = {"step": "waiting_manual_api"}
    
    await callback_query.message.edit_text(
        "✍️ **Manual Mode**\n\n"
        "Send your **Render API Key** (starts with `rnd_`).\n"
        "I will fetch the Owner ID and add it to the panel.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_manual")]])
    )

@app.on_callback_query(filters.regex("cancel_manual"))
async def cancel_manual(client, callback_query):
    chat_id = callback_query.message.chat.id
    if chat_id in manual_sessions: del manual_sessions[chat_id]
    await callback_query.message.edit_text("❌ Manual Add Cancelled.")

# --- ⚡ AUTO EMAIL FLOW ---
@app.on_callback_query(filters.regex("gen_mail"))
async def generate_mail(client, callback_query):
    chat_id = callback_query.message.chat.id
    if chat_id in manual_sessions: del manual_sessions[chat_id]
    
    await callback_query.message.edit_text("🔄 **Generating High-Quality Email...**")
    
    email, password, token = get_mailtm_account()
    
    if not email:
        await callback_query.message.edit_text(
            "❌ Server Error (Mail.tm). Please try again later.", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Retry", callback_data="gen_mail")]])
        )
        return

    user_sessions[chat_id] = {
        "email": email,
        "password": password,
        "step": "waiting_mail"
    }

    info_text = (
        f"🛠 **NEW IDENTITY CREATED**\n\n"
        f"📧 **Email:** `{email}`\n"
        f"🔑 **Pass:** `{password}`\n\n"
        "👉 **Steps:**\n"
        "1. Go to Render, Register & Solve Puzzle.\n"
        "2. Submit & Wait for Verification Mail here.\n"
        "👀 **Checking Inbox...**"
    )
    msg = await callback_query.message.edit_text(info_text)
    asyncio.create_task(check_inbox_loop(client, chat_id, token, msg))

# --- 📨 MAIL LOOP ---
async def check_inbox_loop(client, chat_id, token, message):
    headers = {"Authorization": f"Bearer {token}"}
    for i in range(120): 
        try:
            if chat_id not in user_sessions: break
            resp = requests.get(f"{MAIL_TM_URL}/messages", headers=headers)
            if resp.status_code == 200:
                data = resp.json()['hydra:member']
                if data:
                    msg_id = data[0]['id']
                    full_msg = requests.get(f"{MAIL_TM_URL}/messages/{msg_id}", headers=headers).json()
                    subject = full_msg.get('subject', 'No Subject')
                    body = full_msg.get('text') or full_msg.get('html') or "Empty Body"
                    if len(body) > 3500: body = body[:3500] + "...(truncated)"

                    await message.edit_text(
                        f"📩 **MAIL RECEIVED!**\n\n"
                        f"**Subject:** {subject}\n"
                        f"---------------------------------\n"
                        f"{body}\n"
                        f"---------------------------------\n\n"
                        "👆 **Click link to Verify!**\n\n"
                        "👇 **Now send API Key (starts with rnd_...)**"
                    )
                    user_sessions[chat_id]['step'] = 'waiting_api'
                    return 
        except: pass
        await asyncio.sleep(5)

# --- 🧠 MAIN INPUT HANDLER (Auto & Manual) ---
@app.on_message(filters.text & ~filters.command("start"))
async def handle_inputs(client, message):
    chat_id = message.chat.id
    text = message.text.strip()
    
    is_manual = False
    
    # Identify Flow
    if chat_id in manual_sessions and manual_sessions[chat_id].get("step") == "waiting_manual_api":
        is_manual = True
    elif chat_id in user_sessions and user_sessions[chat_id].get('step') == 'waiting_api':
        is_manual = False
    else:
        return # Ignore random messages

    # Validate Key
    if not text.startswith("rnd_"):
        await message.reply_text("⚠️ **Invalid API Key!** Must start with `rnd_`.")
        return

    api_key = text
    wait_msg = await message.reply_text("🔄 **Fetching Owner ID & Syncing...**")

    try:
        # Fetch Owner ID
        headers = {"Accept": "application/json", "Authorization": f"Bearer {api_key}"}
        response = requests.get(RENDER_API_URL, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            owner_id = data[0]['owner']['id'] if data else "Unknown"
            
            # 🔥 AUTO-ADD TO WEBSITE LOGIC
            sync_msg = "❌ Sync Failed"
            try:
                payload = {"api_key": api_key, "owner_id": owner_id, "secret": ADMIN_SECRET}
                res = requests.post(DEPLOYER_URL, json=payload, timeout=5)
                if res.status_code == 200:
                    sync_msg = "✅ **Auto-Added to Deployer DB**"
                else:
                    sync_msg = f"⚠️ Website Error: {res.status_code}"
            except:
                sync_msg = "⚠️ Website Unreachable"

            # Result Message Construction
            if is_manual:
                final_text = (
                    f"✅ **MANUAL ADD SUCCESS**\n\n"
                    f"**Sync Status:** {sync_msg}\n"
                    f"**Owner ID:** `{owner_id}`"
                )
                del manual_sessions[chat_id]
                await wait_msg.edit_text(final_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Start", callback_data="cancel_manual")]]))
            else:
                email = user_sessions[chat_id]['email']
                password = user_sessions[chat_id]['password']
                final_text = (
                    f"✅ **ALL SET!**\n\n"
                    f"**Sync Status:** {sync_msg}\n\n"
                    f"```\n"
                    f"email={email}\n"
                    f"password={password}\n"
                    f"owner_id={owner_id}\n"
                    f"render_api_key={api_key}\n"
                    f"```"
                )
                del user_sessions[chat_id]
                await wait_msg.edit_text(final_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Start New", callback_data="gen_mail")]]))
            
        else:
            await wait_msg.edit_text("❌ **Error fetching Owner ID.** Check API Key.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Retry", callback_data="gen_mail")]]))

    except Exception as e:
        await wait_msg.edit_text(f"❌ **Crash:** {str(e)}")

print("🤖 HEROKU BOT STARTED!")
app.run()
