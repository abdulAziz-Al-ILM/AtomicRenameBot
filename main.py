import asyncio
import logging
import os
import re
import sys
import aiosqlite
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ContentType

# --- SOZLAMALAR (ENVIRONMENT VARIABLES) ---
# Bularni Railway-da Variables bo'limiga kiritasiz
BOT_TOKEN = os.getenv("BOT_TOKEN") 
ADMIN_ID = int(os.getenv("ADMIN_ID")) # O'zingizning Telegram ID raqamingiz

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)

# --- FSM (HOLATLAR) ---
class RenameState(StatesGroup):
    waiting_for_file = State()
    waiting_for_name = State()

class AdminState(StatesGroup):
    waiting_for_broadcast = State()

# --- DATABASE INITIALIZATION ---
DB_NAME = "bot_users.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        await db.commit()

async def add_user(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.commit()

async def get_users_count():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        count = await cursor.fetchone()
        return count[0]

async def get_all_users():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id FROM users")
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

# --- TUGMALAR ---
def main_keyboard(user_id):
    buttons = [
        [KeyboardButton(text="📢 Reklama xizmati")],
        [KeyboardButton(text="ℹ️ Qo'llanma")]
    ]
    # Agar admin bo'lsa qo'shimcha tugmalar
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📨 Xabar yuborish")])
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)

# --- BOT INITIALIZATION ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# --- HANDLERS (FUNKSIYALAR) ---

@router.message(CommandStart())
async def cmd_start(message: Message):
    await add_user(message.from_user.id)
    await message.answer(
        f"Assalomu alaykum, {message.from_user.full_name}!\n\n"
        "Men fayllarni qayta nomlab beruvchi bepul botman. "
        "Menga istalgan hujjat, video yoki audio fayl yuboring.\n\n"
        "Agar reklama bo'yicha savollaringiz bo'lsa, menyudagi tugmadan foydalaning.",
        reply_markup=main_keyboard(message.from_user.id)
    )

@router.message(F.text == "ℹ️ Qo'llanma")
async def help_handler(message: Message):
    text = (
        "<b>Qanday ishlatish kerak?</b>\n\n"
        "1. Menga fayl (hujjat, video, musiqa) yuboring.\n"
        "2. Men sizdan yangi nom so'rayman.\n"
        "3. Yangi nomni yozasiz (kengaytmani yozish shart emas, masalan: `.pdf`, `.mp4` ni o'zim qo'yaman).\n"
        "4. Men faylni o'zgartirib sizga qaytaraman.\n\n"
        "⚠️ <i>Eslatma: Fayl nomida / \\ : * ? \" < > | belgilaridan foydalanmang! </i>"
    )
    await message.answer(text, parse_mode="HTML")

@router.message(F.text == "📢 Reklama xizmati")
async def ads_handler(message: Message):
    # Adminga bog'lanish uchun inline tugma
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Admin bilan bog'lanish", url=f"tg://user?id={ADMIN_ID}")]
    ])
    await message.answer(
        "Ushbu bot orqali minglab faol foydalanuvchilarga o'z reklamangizni tarqatishingiz mumkin.\n\n"
        "Batafsil ma'lumot va narxlar uchun admin bilan bog'laning:",
        reply_markup=kb
    )

# --- ADMIN FUNCTIONALITY ---

@router.message(F.text == "📊 Statistika", F.from_user.id == ADMIN_ID)
async def stats_handler(message: Message):
    count = await get_users_count()
    await message.answer(f"👥 <b>Bot foydalanuvchilari soni:</b> {count} ta\n\nReklama tarqatsangiz shuncha odamga borishi kutilmoqda.", parse_mode="HTML")

@router.message(F.text == "📨 Xabar yuborish", F.from_user.id == ADMIN_ID)
async def broadcast_ask(message: Message, state: FSMContext):
    await message.answer("Foydalanuvchilarga yuboriladigan xabar matnini (yoki rasm/video) yuboring:", reply_markup=cancel_kb)
    await state.set_state(AdminState.waiting_for_broadcast)

@router.message(AdminState.waiting_for_broadcast)
async def broadcast_send(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Xabar yuborish bekor qilindi.", reply_markup=main_keyboard(message.from_user.id))
        return

    users = await get_all_users()
    count = 0
    blocked = 0
    
    status_msg = await message.answer("Xabar yuborilmoqda...")
    
    for user_id in users:
        try:
            # Admin yuborgan xabarni nusxalab foydalanuvchiga jo'natish
            await message.copy_to(chat_id=user_id)
            count += 1
        except Exception:
            blocked += 1
            
    await status_msg.edit_text(f"✅ Xabar yuborildi!\n\nYetib bordi: {count} ta\nBloklaganlar: {blocked} ta")
    await state.clear()
    await message.answer("Bosh menyu:", reply_markup=main_keyboard(message.from_user.id))

# --- FAYL QAYTA NOMLASH LOGIKASI ---

@router.message(F.document | F.video | F.audio)
async def file_handler(message: Message, state: FSMContext):
    # Fayl ID va asl nomini aniqlash
    if message.document:
        file_id = message.document.file_id
        orig_name = message.document.file_name or "document"
    elif message.video:
        file_id = message.video.file_id
        orig_name = message.video.file_name or "video.mp4"
    elif message.audio:
        file_id = message.audio.file_id
        orig_name = message.audio.file_name or "audio.mp3"
    else:
        return

    # Fayl kengaytmasini olish (ext)
    _, ext = os.path.splitext(orig_name)
    if not ext:
        ext = "" # Agar kengaytma bo'lmasa

    # State ga saqlaymiz
    await state.update_data(file_id=file_id, ext=ext)
    await state.set_state(RenameState.waiting_for_name)
    
    await message.reply(
        f"Fayl qabul qilindi!\nEski nomi: {orig_name}\n\n"
        "<b>Yangi nomni kiriting:</b> (kengaytmani yozish shart emas)",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )

@router.message(RenameState.waiting_for_name)
async def rename_handler(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Amal bekor qilindi.", reply_markup=main_keyboard(message.from_user.id))
        return

    new_name = message.text.strip()
    
    # Validatsiya: Tizim uchun xavfli belgilarni tekshirish
    invalid_chars = r'[<>:"/\\|?*]'
    if re.search(invalid_chars, new_name):
        await message.reply(
            "⚠️ <b>Xatolik!</b> Nomda quyidagi belgilar bo'lishi mumkin emas:\n"
            "<code>< > : \" / \\ | ? *</code>\n\n"
            "Iltimos, boshqa nom yozing:",
            parse_mode="HTML"
        )
        return # State o'zgarmaydi, qayta kutadi

    # Ma'lumotlarni olish
    data = await state.get_data()
    file_id = data['file_id']
    ext = data['ext']
    
    # Yakuniy fayl nomi
    if not new_name.endswith(ext):
        final_filename = new_name + ext
    else:
        final_filename = new_name

    wait_msg = await message.answer("⏳ Fayl qayta nomlanmoqda va yuklanmoqda...")
    
    try:
        # Faylni vaqtinchalik yuklab olish
        file = await bot.get_file(file_id)
        file_path = file.file_path
        
        # Serverga yuklash
        temp_path = f"downloads/{final_filename}"
        os.makedirs("downloads", exist_ok=True)
        
        await bot.download_file(file_path, temp_path)
        
        # Faylni foydalanuvchiga qaytarish
        input_file = FSInputFile(temp_path, filename=final_filename)
        await message.answer_document(input_file, caption=f"✅ Marhamat: {final_filename}")
        
        # Tozalash
        os.remove(temp_path)
        await wait_msg.delete()
        
    except Exception as e:
        await wait_msg.edit_text(f"Xatolik yuz berdi: {e}")
    
    await state.clear()
    # Admin bo'lsa admin panelga, user bo'lsa oddiy menyuga qaytish shart emas, shunchaki tugadi.
    # Lekin qulaylik uchun menyuni yana bir bor ko'rsatib qo'yish mumkin:
    if message.from_user.id == ADMIN_ID:
        await message.answer("Yana nima qilamiz?", reply_markup=main_keyboard(message.from_user.id))
    else:
        await message.answer("Yana fayl yuborishingiz mumkin.", reply_markup=main_keyboard(message.from_user.id))


# --- MAIN ENTRY POINT ---
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot to'xtatildi")
