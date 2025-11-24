import asyncio
import aiosqlite
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# ────── MUHIT OʻZGARUVCHILARIDAN OLISH ──────
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

if not BOT_TOKEN or not ADMIN_ID:
    raise ValueError("BOT_TOKEN va ADMIN_ID muhit oʻzgaruvchilarini sozlang!")

# ────── REKLAMA SOZLAMLARI (oʻzgartiring) ──────
AD_TEXT = """
Fayl nomi muvaffaqiyatli oʻzgartirildi!

Reklama va PR uchun:
@sizning_username   t.me/sizning_username
"""

CONTACT_BTN_TEXT = "Reklama joylashtirish"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

DB_NAME = "renamer_bot.db"

# ────── STATE ──────
class RenameStates(StatesGroup):
    waiting_for_new_name = State()

class Broadcast(StatesGroup):
    waiting_message = State()

# ────── DB ──────
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            is_blocked INTEGER DEFAULT 0,
            last_active REAL
        )''')
        await db.commit()

async def add_user(user: types.User):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""INSERT INTO users 
            (user_id, username, first_name, last_name, last_active, is_blocked)
            VALUES (?, ?, ?, ?, ?, 0)
            ON CONFLICT(user_id) DO UPDATE SET
            last_active = excluded.last_active,
            username = excluded.username,
            is_blocked = 0
        """, (user.id, user.username, user.first_name, user.last_name, asyncio.get_event_loop().time()))
        await db.commit()

async def get_active_count():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 0") as cur:
            row = await cur.fetchone()
            return row[0] or 0

async def get_all_users():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users WHERE is_blocked = 0") as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]

# ────── KEYBOARDS ──────
def user_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text=CONTACT_BTN_TEXT)
    return kb.as_markup(resize_keyboard=True)

def admin_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text="Statistika")
    kb.button(text="Hammaga xabar")
    kb.button(text="Oddiy menu")
    kb.adjust(2, 1)
    return kb.as_markup(resize_keyboard=True)

# ────── HANDLERS ──────
@dp.message(Command("start"))
async def start(message: types.Message):
    await add_user(message.from_user)
    if message.from_user.id == ADMIN_ID:
        await message.answer("Admin panel ochildi!", reply_markup=admin_menu())
    else:
        await message.answer(
            "Assalomu alaykum!\n\n"
            "Menga fayl yuboring → yangi nomini yozing → tayyor boʻladi!",
            reply_markup=user_menu()
        )

@dp.message(F.text == "Oddiy menu")
async def to_user_menu(m: Message):
    if m.from_user.id != ADMIN_ID: return
    await m.answer("Oddiy menu", reply_markup=user_menu())

@dp.message(F.text == CONTACT_BTN_TEXT)
async def reklama(m: Message):
    await add_user(m.from_user)
    await m.answer(f"{CONTACT_BTN_TEXT}\n@sizning_username")

@dp.message(F.text == "Statistika")
async def stats(m: Message):
    if m.from_user.id != ADMIN_ID: return
    cnt = await get_active_count()
    await m.answer(f"Faol foydalanuvchilar: {cnt} ta")

@dp.message(F.text == "Hammaga xabar")
async def broadcast_start(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    await m.answer("Xabarni yuboring (foto, video, matn – hammasi boʻladi)\nBeko qilish: /cancel")
    await state.set_state(Broadcast.waiting_message)

@dp.message(Broadcast.waiting_message)
async def broadcast_send(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    users = await get_all_users()
    await m.answer(f"Boshlandi... Jami: {len(users)} ta")
    ok = blocked = 0
    for uid in users:
        try:
            await m.copy_to(uid)
            ok += 1
        except Exception as e:
            if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                blocked += 1
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("UPDATE users SET is_blocked=1 WHERE user_id=?", (uid,))
                    await db.commit()
        await asyncio.sleep(0.035)  # 30 msg/sek limit
    await m.answer(f"Yuborildi: {ok}\nBloklagan: {blocked}")
    await state.clear()

# Fayl qabul qilish
@dp.message(F.document | F.photo | F.video | F.audio | F.voice | F.animation | F.video_note)
async def file_received(m: Message, state: FSMContext):
    await add_user(m.from_user)

    if m.document: file = m.document
    elif m.photo: file = m.photo[-1]
    elif m.video: file = m.video
    elif m.audio: file = m.audio
    elif m.voice: file = m.voice
    elif m.animation: file = m.animation
    elif m.video_note: file = m.video_note
    else: file = m.document

    await state.update_data(file_id=file.file_id, ctype=m.content_type)
    await m.answer("Yangi nomni yozing (kengaytmasi bilan):\nmasalan: <code>video.mp4</code>", parse_mode="HTML")
    await state.set_state(RenameStates.waiting_for_new_name)

# Yangi nom bilan qaytarish
@dp.message(RenameStates.waiting_for_new_name)
async def rename(m: Message, state: FSMContext):
    new_name = m.text.strip()
    if len(new_name) > 120:
        await m.answer("Nom juda uzun!")
        return

    data = await state.get_data()
    file = await bot.get_file(data["file_id"])
    dl = await bot.download_file(file.file_path)
    input_file = FSInputFile(dl, filename=new_name)

    try:
        if data["ctype"] == "photo":
            await m.answer_photo(input_file, caption=AD_TEXT)
        elif data["ctype"] == "document":
            await m.answer_document(input_file, caption=AD_TEXT)
        elif data["ctype"] in ["video", "audio", "voice", "animation", "video_note"]:
            await m.answer_document(input_file, caption=AD_TEXT)
        else:
            await m.answer_document(input_file, caption=AD_TEXT)
    except Exception as e:
        await m.answer(f"Xatolik: {e}")
    finally:
        await state.clear()

# ────── START ──────
async def on_startup():
    await init_db()
    print("Bot ishga tushdi!")

async def main():
    await on_startup()
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
