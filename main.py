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
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# ────── MUHIT OʻZGARUVCHILARI ──────
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

if not BOT_TOKEN or not ADMIN_ID:
    raise ValueError("BOT_TOKEN va ADMIN_ID sozlanmagan!")

# REKLAMA SOZLAMLARI (oʻzgartiring)
REKLAMA_TEXT = """
Fayl nomi oʻzgartirildi!

Reklama va PR uchun:
@reklamauz_admin   t.me/reklamauz_admin
"""

CONTACT_BUTTON = "Reklama"

# ────── BOT VA DP ──────
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
DB = "bot.db"

# ────── STATES ──────
class Rename(StatesGroup):
    waiting_name = State()

class Broadcast(StatesGroup):
    waiting_msg = State()

# ────── DB ──────
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            is_blocked INTEGER DEFAULT 0
        )''')
        await db.commit()

async def add_user(user: types.User):
    async with aiosqlite.connect(DB) as db:
        await db.execute("""INSERT OR REPLACE INTO users 
            (user_id, username, first_name, is_blocked) 
            VALUES (?, ?, ?, 0)""",
            (user.id, user.username or "", user.first_name or ""))
        await db.commit()

async def active_users():
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 0")
        row = await cur.fetchone()
        return row[0]

async def all_users():
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT user_id FROM users WHERE is_blocked = 0")
        rows = await cur.fetchall()
        return [r[0] for r in rows]

# ────── MENULAR ──────
def user_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text=CONTACT_BUTTON)
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
async def start(m: Message):
    await add_user(m.from_user)
    if m.from_user.id == ADMIN_ID:
        await m.answer("Admin panel ochildi!", reply_markup=admin_menu())
    else:
        await m.answer(
            "Assalomu alaykum!\n\n"
            "Fayl yuboring → yangi nomini yozing → tayyor!",
            reply_markup=user_menu()
        )

@dp.message(F.text == CONTACT_BUTTON)
async def reklama(m: Message):
    await add_user(m.from_user)
    await m.answer(f"{CONTACT_BUTTON} uchun:\n@reklamauz_admin")

@dp.message(F.text == "Oddiy menu")
async def back_menu(m: Message):
    if m.from_user.id != ADMIN_ID: return
    await m.answer("Oddiy foydalanuvchi menusi", reply_markup=user_menu())

@dp.message(F.text == "Statistika")
async def stats(m: Message):
    if m.from_user.id != ADMIN_ID: return
    cnt = await active_users()
    await m.answer(f"Faol foydalanuvchilar: <b>{cnt}</b> ta")

@dp.message(F.text == "Hammaga xabar")
async def b_start(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    await m.answer("Xabarni yuboring (matn, rasm, video – hammasi boʻladi)")
    await state.set_state(Broadcast.waiting_msg)

@dp.message(Broadcast.waiting_msg)
async def b_send(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    users = await all_users()
    await m.answer(f"Boshlandi... Jami: {len(users)}")
    success = blocked = 0
    for uid in users:
        try:
            await m.copy_to(uid)
            success += 1
        except:
            blocked += 1
            async with aiosqlite.connect(DB) as db:
                await db.execute("UPDATE users SET is_blocked=1 WHERE user_id=?", (uid,))
                await db.commit()
        await asyncio.sleep(0.035)
    await m.answer(f"Yuborildi: {success}\nBloklagan: {blocked}")
    await state.clear()

# Fayl qabul qilish
@dp.message(F.document | F.photo | F.video | F.audio | F.voice | F.animation | F.video_note)
async def file_get(m: Message, state: FSMContext):
    await add_user(m.from_user)

    if m.document: file = m.document
    elif m.photo: file = m.photo[-1]
    elif m.video: file = m.video
    elif m.audio: file = m.audio
    elif m.voice: file = m.voice
    elif m.animation: file = m.animation
    elif m.video_note: file = m.video_note

    await state.update_data(file_id=file.file_id, type=m.content_type)
    await m.answer("Yangi nomni yozing (kengaytma bilan):\n<code>mening_fayl.pdf</code>")
    await state.set_state(Rename.waiting_name)

# Nom oʻzgartirish
@dp.message(Rename.waiting_name)
async def rename_file(m: Message, state: FSMContext):
    new_name = m.text.strip()
    if not new_name or len(new_name) > 100:
        await m.answer("Notoʻgʻri nom!")
        return

    data = await state.get_data()
    file = await bot.get_file(data["file_id"])
    downloaded = await bot.download_file(file.file_path)
    input_file = FSInputFile(downloaded, filename=new_name)

    try:
        if data["type"] == "photo":
            await m.answer_photo(input_file, caption=REKLAMA_TEXT)
        else:
            await m.answer_document(input_file, caption=REKLAMA_TEXT)
    except Exception as e:
        await m.answer(f"Xatolik: {e}")
    finally:
        await state.clear()

# ────── START ──────
async def main():
    await init_db()
    print("Bot ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
