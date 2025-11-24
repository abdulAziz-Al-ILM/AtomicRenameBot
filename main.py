# main.py – Tuzatilgan va himoyalangan versiya (aiogram 3.7+ uchun)
import os
import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
import asyncpg

# ───── SOZLAMALAR ─────
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # O'zingizning ID
DATABASE_URL = os.getenv("DATABASE_URL")  # Railway dan olingan
db_pool = None

# Bot ni to'g'ri sozlash (parse_mode xatosi tuzatildi)
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ───── GUARDIAN HIMIYA ─────
FLOOD_LIMIT = 6          # 3 soniyada 6 ta xabar → blok
FLOOD_WINDOW = 3
BANNED_USERS = set()     # Tez cache
USER_MSG_LOG = {}        # {user_id: [timestamp, ...]}
GROUP_MODE = {}          # {chat_id: True} — faqat admin qoʻshsa ishlaydi

INVALID_CHARS = r'\/:*?"<>|'

class RenameState(StatesGroup):
    waiting_for_new_name = State()

# ───── HIMIYA FUNKSIYALARI ─────
def get_now():
    return asyncio.get_event_loop().time()

async def is_flood(user_id: int, chat_id: int) -> bool:
    now = get_now()
    log = USER_MSG_LOG.get(user_id, [])
    log = [t for t in log if now - t < FLOOD_WINDOW]
    log.append(now)
    USER_MSG_LOG[user_id] = log
    return len(log) > FLOOD_LIMIT

async def block_user(user_id: int, username: str = "", chat_title=""):
    if user_id in BANNED_USERS:
        return
    BANNED_USERS.add(user_id)
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO banned (user_id) VALUES ($1) ON CONFLICT DO NOTHING", user_id)

    alert = (
        f"🛡️ GUARDIAN: Hujum aniqlandi!\n\n"
        f"👤 Foydalanuvchi: {username or 'NoName'} (<code>{user_id}</code>)\n"
        f"💬 Guruh: {chat_title or 'Shaxsiy'}\n"
        f"⚠️ Sabab: Flood / Spam\n"
        f"📅 Vaqt: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        f"🚫 Status: BLOKLANDI"
    )
    try:
        await bot.send_message(ADMIN_ID, alert)
    except: pass

# ───── DB ─────
async def init_db():
    global db_pool
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment o'zgaruvchisi topilmadi!")
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_seen TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS banned (
                user_id BIGINT PRIMARY KEY
            );
        ''')

async def add_user(user: types.User):
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO users (user_id, username, first_name) VALUES ($1,$2,$3)
            ON CONFLICT (user_id) DO UPDATE SET last_seen = NOW()
        ''', user.id, user.username, user.full_name)

async def is_banned(user_id: int) -> bool:
    if user_id in BANNED_USERS:
        return True
    async with db_pool.acquire() as conn:
        return await conn.fetchval("SELECT 1 FROM banned WHERE user_id = $1", user_id) is not None

async def get_stats():
    async with db_pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM users")
        today = await conn.fetchval("SELECT COUNT(*) FROM users WHERE last_seen::date = CURRENT_DATE")
        return total, today

# ───── KLAVIATURA ─────
def main_menu(is_admin=False):
    kb = [[KeyboardButton(text="📁 Fayl nomini o'zgartirish")]]
    if is_admin:
        kb.append([KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📤 Xabar yuborish")])
    kb.append([KeyboardButton(text="❌ Bekor qilish")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=False)

# ───── HANDLERLAR ─────
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user = message.from_user
    chat = message.chat

    # Guruh himoyasi
    if chat.type in [types.ChatType.GROUP, types.ChatType.SUPERGROUP]:
        if chat.id not in GROUP_MODE:
            try:
                admins = await bot.get_chat_administrators(chat.id)
                if user.id not in [a.user.id for a in admins]:
                    return  # Jim o'tkazib yuborish
            except:
                return
        GROUP_MODE[chat.id] = True

    # Blok va flood tekshiruvi
    if await is_banned(user.id):
        return
    if await is_flood(user.id, chat.id):
        await block_user(user.id, user.full_name, chat.title or "")
        return await message.answer("🚫 Siz spam uchun bloklandingiz. Botdan foydalana olmaysiz.")

    await add_user(user)
    text = (
        "🤖 <b>Fayl Nom Renamer Bot</b> ga xush kelibsiz!\n\n"
        "📋 <b>Qanday ishlaydi:</b>\n"
        "1. Istalgan faylni yuboring (📷 rasm, 🎥 video, 📄 hujjat...)\n"
        "2. Men yangi nom so'rayman\n"
        "3. Nom kiriting → tayyor faylni olasiz!\n\n"
        "⚠️ <b>Taqiqlangan belgilar (Windows uchun):</b>\n"
        f"<code>{INVALID_CHARS}</code>\n\n"
        "💎 Bepul xizmat! Reklama: @SizningKanalingiz"
    )
    await message.answer(text, reply_markup=main_menu(user.id == ADMIN_ID))

@dp.message(F.text == "📁 Fayl nomini o'zgartirish")
async def ask_file(message: types.Message):
    await message.answer(
        "✅ Tayyor! Endi istalgan faylni yuboring:\n"
        "(📷 Rasm, 🎥 Video, 📄 Hujjat, 🎵 Audio...)",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
            resize_keyboard=True
        )
    )

@dp.message(F.text == "❌ Bekor qilish")
async def cancel_action(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Amal bekor qilindi.", reply_markup=main_menu(message.from_user.id == ADMIN_ID))

@dp.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    total, today = await get_stats()
    text = (
        f"📊 <b>Bot Statistika</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{total}</b>\n"
        f"🔥 Bugun faol: <b>{today}</b>\n"
        f"🛡️ Bloklangan: <code>{len(BANNED_USERS)}</code>\n\n"
        f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    await message.answer(text, reply_markup=main_menu(True))

@dp.message(F.text == "📤 Xabar yuborish")
async def broadcast_ask(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "📤 Hamma foydalanuvchilarga yuborish uchun xabarni yozing yoki fayl yuboring:\n"
        "(Matn, rasm, video...)",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
            resize_keyboard=True
        )
    )
    await state.set_state(RenameState.waiting_for_new_name)  # Reuse state for broadcast

# Fayl qabul qilish (himoyalangan)
@dp.message(F.document | F.photo | F.video | F.audio | F.voice | F.video_note | F.sticker)
async def receive_file(message: types.Message, state: FSMContext):
    user = message.from_user
    chat = message.chat

    # Himoya tekshiruvi
    if await is_banned(user.id):
        return
    if await is_flood(user.id, chat.id):
        await block_user(user.id, user.full_name, chat.title or "")
        return await message.answer("🚫 Spam! Bloklandingiz.")

    if chat.type in [types.ChatType.GROUP, types.ChatType.SUPERGROUP] and chat.id not in GROUP_MODE:
        return

    await add_user(user)

    # Faylni aniqlash
    file_obj = None
    file_name = "fayl"
    if message.document:
        file_obj = message.document
        file_name = file_obj.file_name or file_name
    elif message.photo:
        file_obj = message.photo[-1]
        file_name = f"rasm_{file_obj.file_id}.jpg"
    elif message.video:
        file_obj = message.video
        file_name = file_obj.file_name or "video.mp4"
    elif message.audio:
        file_obj = message.audio
        file_name = file_obj.file_name or "audio.mp3"
    elif message.voice:
        file_obj = message.voice
        file_name = "voice.ogg"
    elif message.video_note:
        file_obj = message.video_note
        file_name = "video_note.mp4"
    elif message.sticker:
        file_obj = message.sticker
        file_name = "sticker.webp"

    if not file_obj:
        return await message.answer("❌ Bu fayl turi qo'llab-quvvatlanmaydi.")

    await state.update_data(file_id=file_obj.file_id, file_name=file_name)
    ext = os.path.splitext(file_name)[1]
    text = (
        f"📁 <b>Joriy fayl:</b> <code>{file_name}</code>\n\n"
        f"✏️ <b>Yangi nom kiriting (faqat ism, extension avto qo'shiladi):</b>\n\n"
        f"💡 <b>Misol:</b> <code>Mening_Dokumentim{ext}</code>\n\n"
        f"⚠️ <b>Taqiqlangan belgilar:</b> <code>{INVALID_CHARS}</code>\n"
        f"(Bular bo'lsa, Windowsda xato chiqadi!)"
    )
    await message.answer(
        text,
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
            resize_keyboard=True
        )
    )
    await state.set_state(RenameState.waiting_for_new_name)

# Nom kiritish (fayl renamer yoki broadcast)
@dp.message(RenameState.waiting_for_new_name)
async def process_rename_or_broadcast(message: types.Message, state: FSMContext):
    user = message.from_user
    if user.id != ADMIN_ID and message.text == "❌ Bekor qilish":
        await state.clear()
        return await message.answer("❌ Bekor qilindi.", reply_markup=main_menu(False))

    data = await state.get_data()
    if "file_id" in data:  # Fayl renamer
        new_name = message.text.strip() if message.text != "❌ Bekor qilish" else None
        if not new_name:
            await state.clear()
            return await message.answer("❌ Nom kiritilmadi. Bekor qilindi.", reply_markup=main_menu(False))

        if any(c in new_name for c in INVALID_CHARS):
            return await message.answer(f"❌ Xato! Taqiqlangan belgi bor: <code>{INVALID_CHARS}</code>\nQaytadan urinib ko'ring.")

        ext = os.path.splitext(data["file_name"])[1]
        if not new_name.endswith(ext):
            new_name += ext

        try:
            # Fayl yuklash va qayta yuborish
            file_info = await bot.get_file(data["file_id"])
            file_path = await bot.download_file(file_info.file_path)

            await bot.send_document(
                chat_id=message.chat.id,
                document=FSInputFile(file_path, filename=new_name),
                caption=f"✅ <b>{new_name}</b>\n\n🤖 Renamed by @SizningBotingiz\n💎 Bepul xizmat!"
            )
            await message.answer("🎉 Fayl muvaffaqiyatli o'zgartirildi!", reply_markup=main_menu(user.id == ADMIN_ID))
        except Exception as e:
            await message.answer(f"❌ Xato yuz berdi: {str(e)}")
        finally:
            await state.clear()
    else:  # Broadcast (admin uchun)
        if user.id != ADMIN_ID:
            return
        if message.text == "❌ Bekor qilish":
            await state.clear()
            return await message.answer("❌ Broadcast bekor qilindi.", reply_markup=main_menu(True))

        # Broadcast yuborish
        await message.answer("⏳ Xabar yuborilmoqda... (Bu biroz vaqt olishi mumkin)")
        success, failed = 0, 0
        async with db_pool.acquire() as conn:
            users = await conn.fetch("SELECT user_id FROM users")
        for row in users:
            try:
                if message.text:
                    await bot.send_message(row['user_id'], message.text)
                elif message.document:
                    await bot.send_document(row['user_id'], message.document)
                # Boshqa media turlari uchun ham qo'shishingiz mumkin
                success += 1
                await asyncio.sleep(0.05)  # Telegram limit
            except:
                failed += 1
        await message.answer(
            f"✅ <b>Broadcast tugadi!</b>\n\n"
            f"Muvaffaqiyat: {success}\n"
            f"Xato: {failed}",
            reply_markup=main_menu(True)
        )
        await state.clear()

# Umumiy himoya (barcha xabarlar uchun)
@dp.message()
async def global_protect(message: types.Message, state: FSMContext):
    user = message.from_user
    chat = message.chat

    # Himoya
    if await is_banned(user.id):
        return
    if await is_flood(user.id, chat.id):
        await block_user(user.id, user.full_name, chat.title or "")
        return await message.answer("🚫 Spam! Siz bloklandingiz.")

    if chat.type in [types.ChatType.GROUP, types.ChatType.SUPERGROUP] and chat.id not in GROUP_MODE:
        return

    # Bekor qilish
    if message.text == "❌ Bekor qilish":
        await state.clear()
        return await message.answer("❌ Bekor qilindi.", reply_markup=main_menu(user.id == ADMIN_ID))

# ───── START ─────
async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment o'zgaruvchisi topilmadi!")
    await init_db()
    logging.basicConfig(level=logging.INFO)
    print("🤖 Bot ishga tushdi | Guardian himoyasi faol | ParseMode: HTML")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
