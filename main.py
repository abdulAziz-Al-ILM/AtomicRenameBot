# main.py – CONFLICTGA QARSHI TEMIR KOD
import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN yo'q!")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

class State(StatesGroup):
    waiting = State()

def menu(admin=False):
    kb = [[KeyboardButton(text="Fayl nomini o'zgartirish")]]
    if admin:
        kb += [[KeyboardButton(text="Statistika")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Salom! Fayl yuboring — yangi nom so'rayman.\n\n"
        "Taqiqlangan belgilar: \\ / : * ? \" < > |",
        reply_markup=menu(message.from_user.id == 123456789)  # <--- ADMIN_ID o'rniga o'zingiznikini yozing
    )

@dp.message(F.text == "Fayl nomini o'zgartirish")
async def ask(message: types.Message):
    await message.answer("Fayl yuboring:", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Bekor")]], resize_keyboard=True))

@dp.message(F.text == "Bekor")
async def cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=menu(False))

@dp.message(F.document | F.photo | F.video | F.audio | F.voice)
async def file_got(message: types.Message, state: FSMContext):
    file = message.document or message.photo[-1] if message.photo else message.video or message.audio or message.voice
    name = getattr(file, "file_name", "fayl")
    ext = name[name.rfind("."):] if "." in name else ""
    await state.update_data(fid=file.file_id, ext=ext)
    await message.answer(f"Yangi nom kiriting:\n\nHozirgi: {name}", 
                        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Bekor")]], resize_keyboard=True))
    await state.set_state(State.waiting)

@dp.message(State.waiting)
async def rename(message: types.Message, state: FSMContext):
    if message.text == "Bekor":
        await state.clear()
        return await message.answer("Bekor qilindi.")

    new = message.text.strip()
    if any(c in new for c in r'\/:*?"<>|'):
        return await message.answer("Bunday belgilar bo'lmaydi!")

    data = await state.get_data()
    final_name = new + data["ext"]

    file = await bot.get_file(data["fid"])
    downloaded = await bot.download_file(file.file_path)

    await bot.send_document(message.chat.id, FSInputFile(downloaded, filename=final_name),
                           caption=f"{final_name}\n\n@FaylRenamerBot")
    await message.answer("Tayyor!", reply_markup=menu(False))
    await state.clear()

async def main():
    logging.basicConfig(level=logging.INFO)
    print("Bot ishga tushdi – hozir javob beradi!")
    await dp.start_polling(bot, polling_timeout=20)

if __name__ == "__main__":
    asyncio.run(main())
