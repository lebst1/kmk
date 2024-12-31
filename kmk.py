import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import exceptions
import sqlite3
import re

API_TOKEN = '7718675941:AAGX2yhPnuXtcbnVyTQO07pgHAmAzRV-aS8'
CHANNEL_ID = -1002348804504
LOG_CHANNEL_ID = -4606061260
DATABASE_NAME = 'bot.db'
ADMIN_ID = 7307366104
CHANNEL_ID_TO_DELETE = 'vkmklove'

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

class Mode(StatesGroup):
    mode = State()
    send_message = State()

conn = sqlite3.connect(DATABASE_NAME)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS users
    (id INTEGER PRIMARY KEY, mode TEXT DEFAULT 'Не выбран')
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS banned_words
    (word TEXT PRIMARY KEY)
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS banned_users
    (id INTEGER PRIMARY KEY)
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_stats
    (id INTEGER PRIMARY KEY, total INTEGER DEFAULT 0, anonymous INTEGER DEFAULT 0, public INTEGER DEFAULT 0)
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS telegram_users
    (id INTEGER PRIMARY KEY, username TEXT)
''')

conn.commit()

def is_banned(user_id):
    cursor.execute('SELECT * FROM banned_users WHERE id = ?', (user_id,))
    return cursor.fetchone() is not None


def get_mode(user_id):
    cursor.execute('SELECT mode FROM users WHERE id = ?', (user_id,))
    mode = cursor.fetchone()
    if mode is None:
        return 'Не выбран'
    else:
        return mode[0]

def set_mode(user_id, mode):
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    if user is None:
        cursor.execute('INSERT INTO users (id, mode) VALUES (?, ?)', (user_id, mode))
    else:
        cursor.execute('UPDATE users SET mode = ? WHERE id = ?', (mode, user_id))
    conn.commit()

def get_banned_words():
    cursor.execute('SELECT word FROM banned_words')
    words = cursor.fetchall()
    return [word[0] for word in words]

def add_banned_word(word):
    cursor.execute('INSERT INTO banned_words (word) VALUES (?)', (word,))
    conn.commit()

def remove_banned_word(word):
    cursor.execute('DELETE FROM banned_words WHERE word = ?', (word,))
    conn.commit()

add_word = ''
remove_word = ''

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    cursor.execute('SELECT * FROM telegram_users WHERE id = ?', (message.from_user.id,))
    if cursor.fetchone() is None:
        cursor.execute('INSERT INTO telegram_users (id, username) VALUES (?, ?)', (message.from_user.id, message.from_user.username))
        conn.commit()
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton('📨 Отправить сообщение'))
    keyboard.add(types.KeyboardButton('🛠️ Настройки'))
    await message.reply('👋 Добро пожаловать в нашего бота! 🤖\nВыберите действие:', reply_markup=keyboard)

@dp.message_handler(lambda message: message.text == '📨 Отправить сообщение')
async def send_message(message: types.Message, state: FSMContext):
    mode = get_mode(message.from_user.id)
    if mode == 'Не выбран':
        await message.reply('🚨 Пожалуйста, выберите режим отправки в настройках! 🚨')
    else:
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton('🚫 Отменить', callback_data='cancel_send'))
        await message.reply(f'📝 Введите сообщение ({mode}):', reply_markup=keyboard)
        await Mode.send_message.set()

@dp.callback_query_handler(lambda callback_query: callback_query.data == 'cancel_send', state=Mode.send_message)
async def cancel_send(callback_query: types.CallbackQuery, state: FSMContext):
    await state.finish()
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton('📨 Отправить сообщение'))
    keyboard.add(types.KeyboardButton('🛠️ Настройки'))
    await callback_query.message.reply('🚫 Отправка сообщения отменена!', reply_markup=keyboard)

@dp.message_handler(lambda message: message.text not in ['📨 Отправить сообщение', '🛠️ Настройки', '📝 Режим отправки', '🔒 Анонимный режим', '📢 Публичный режим', '🔙 Назад в настройки', '🔙 Назад'], state=Mode.send_message)
async def handle_message(message: types.Message, state: FSMContext):
    if is_banned(message.from_user.id):
        await message.reply('🚫 Вы забанены!')
        return
    text = message.text
    banned_words = get_banned_words()
    for word in banned_words:
        if re.search(r'\b' + re.escape(word) + r'\b', text, re.IGNORECASE):
            await message.reply('🚫 Это слово запрещено!')
            return
    if re.search(r'\b(https?://|www\.)\S+\b', text):
        await message.reply('🚫 Ссылки не допускаются!')
        return
    if re.search(r'\b\+\d{1,3}\s?\(?\d{1,3}\)?[\s.-]?\d{1,5}[\s.-]?\d{1,9}\b', text):
        await message.reply('🚫 Номера телефонов не допускаются!')
        return
    if re.search(r'@\w+', text):
        await message.reply('🚫 Юзернеймы телеграмма не допускаются!')
        return
    mode = get_mode(message.from_user.id)
    cursor.execute('SELECT * FROM user_stats WHERE id = ?', (message.from_user.id,))
    stats = cursor.fetchone()
    if stats is None:
        stats = (message.from_user.id, 0, 0, 0)
        cursor.execute('INSERT INTO user_stats (id, total, anonymous, public) VALUES (?, ?, ?, ?)', stats)
        conn.commit()
    if mode == 'Анонимный':
        await bot.send_message(CHANNEL_ID, text)
        user = message.from_user
        log_message = f'✉️ Новое сообщение от 👤 {user.mention} ({user.full_name})\n 🆔 ID: {user.id}\n 💬Анонимно отправил:\n\n{text}'
        await bot.send_message(LOG_CHANNEL_ID, log_message)
        await message.reply('📨 Сообщение отправлено анонимно!')
        cursor.execute('UPDATE user_stats SET total = total + 1, anonymous = anonymous + 1 WHERE id = ?', (message.from_user.id,))
        conn.commit()
    elif mode == 'Публичный':
        await bot.forward_message(CHANNEL_ID, message.from_user.id, message.message_id)
        user = message.from_user
        log_message = f'✉️ Новое сообщение от 👤 {user.mention} ({user.full_name})\n 🆔 ID: {user.id}\n 💬Публично отправил:\n\n{text}'
        await bot.send_message(LOG_CHANNEL_ID, log_message)
        await message.reply('📢 Сообщение отправлено публично!')
        cursor.execute('UPDATE user_stats SET total = total + 1, public = public + 1 WHERE id = ?', (message.from_user.id,))
        conn.commit()
    await state.finish()

@dp.message_handler(lambda message: message.text == '🛠️ Настройки')
async def settings(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton('📝 Режим отправки'))
    keyboard.add(types.KeyboardButton('📊 Статистика'))
    keyboard.add(types.KeyboardButton('📈 Всеобщий топ'))
    keyboard.add(types.KeyboardButton('🔙 Назад'))
    if message.from_user.id == ADMIN_ID:
        keyboard.add(types.KeyboardButton('🔒 Настройки админа'))
    await message.reply('🛠️ Настройки:', reply_markup=keyboard)

@dp.message_handler(lambda message: message.text == '📈 Всеобщий топ')
async def top(message: types.Message):
    cursor.execute('SELECT id, public FROM user_stats ORDER BY public DESC LIMIT 10')
    top_users = cursor.fetchall()
    text = '📈 Всеобщий топ:\n'
    for i, user in enumerate(top_users):
        cursor.execute('SELECT username FROM telegram_users WHERE id = ?', (user[0],))
        username = cursor.fetchone()
        if username is not None:
            text += f'{i+1}. @{username[0]} - {user[1]} публичных сообщений\n'
        else:
            text += f'{i+1}. Пользователь не найден - {user[1]} публичных сообщений\n'
    await bot.send_message(CHANNEL_ID, text)
    await message.reply('📈 Всеобщий топ отправлен в канал!')

@dp.message_handler(lambda message: message.text == '📊 Статистика')
async def statistics(message: types.Message):
    cursor.execute('SELECT * FROM user_stats WHERE id = ?', (message.from_user.id,))
    stats = cursor.fetchone()
    if stats is None:
        stats = (message.from_user.id, 0, 0, 0)
        cursor.execute('INSERT INTO user_stats (id, total, anonymous, public) VALUES (?, ?, ?, ?)', stats)
        conn.commit()
    total = stats[1]
    anonymous = stats[2]
    public = stats[3]
    await message.reply(f'📊 Статистика:\nВсего сообщений: {total}\nАнонимных сообщений: {anonymous}\nПубличных сообщений: {public}')

@dp.message_handler(lambda message: message.text == '📝 Режим отправки')
async def send_mode(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton('🔒 Анонимный режим'))
    keyboard.add(types.KeyboardButton('📢 Публичный режим'))
    keyboard.add(types.KeyboardButton('🔙 Назад в настройки'))
    await message.reply('📝 Выберите режим:', reply_markup=keyboard)

@dp.message_handler(lambda message: message.text == '🔒 Анонимный режим', state='*')
async def anonymous_mode(message: types.Message, state: FSMContext):
    set_mode(message.from_user.id, 'Анонимный')
    await message.reply('🔒 Режим установлен: Анонимный')

@dp.message_handler(lambda message: message.text == '📢 Публичный режим', state='*')
async def public_mode(message: types.Message, state: FSMContext):
    set_mode(message.from_user.id, 'Публичный')
    await message.reply('📢 Режим установлен: Публичный')

@dp.message_handler(lambda message: message.text == '🔙 Назад в настройки')
async def back_to_settings(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton('📝 Режим отправки'))
    keyboard.add(types.KeyboardButton('🔙 Назад'))
    if message.from_user.id == ADMIN_ID:
        keyboard.add(types.KeyboardButton('🔒 Настройки админа'))
    await message.reply('🛠️ Настройки:', reply_markup=keyboard)

@dp.message_handler(lambda message: message.text == '🔙 Назад')
async def back(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton('📨 Отправить сообщение'))
    keyboard.add(types.KeyboardButton('🛠️ Настройки'))
    await message.reply('👋 Главное меню', reply_markup=keyboard)

@dp.message_handler(lambda message: message.text == '🔒 Настройки админа')
async def admin_settings(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add(types.KeyboardButton('📝 Добавить запрещенное слово'))
        keyboard.add(types.KeyboardButton('📝 Удалить запрещенное слово'))
        keyboard.add(types.KeyboardButton('📝 Список запрещенных слов'))
        keyboard.add(types.KeyboardButton('🚫 Забанить пользователя'))
        keyboard.add(types.KeyboardButton('🔙 Назад'))
        await message.reply('🔒 Настройки админа:', reply_markup=keyboard)
    else:
        await message.reply('🚫 Вы не админ!')

@dp.message_handler(lambda message: message.text == '🚫 Забанить пользователя')
async def ban_user(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.reply('🚫 Введите ID пользователя для бана:')
        @dp.message_handler(lambda message: message.text.isdigit())
        async def ban_user_handler(message: types.Message):
            user_id = int(message.text)
            cursor.execute('INSERT INTO banned_users (id) VALUES (?)', (user_id,))
            conn.commit()
            await message.reply(f'🚫 Пользователь с ID {user_id} забанен!')
    else:
        await message.reply('🚫 Вы не админ!')  

@dp.message_handler(commands=['addword'])
async def add_banned_word_command(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        word = message.get_args()
        if word:
            add_banned_word(word)
            await message.reply(f'🚫 Слово "{word}" добавлено в список запрещенных слов!')
        else:
            await message.reply('🚫 Пожалуйста, укажите слово для добавления!')
    else:
        await message.reply('🚫 Вы не админ!')

@dp.message_handler(commands=['delword'])
async def remove_banned_word_command(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        word = message.get_args()
        if word:
            if word in get_banned_words():
                remove_banned_word(word)
                await message.reply(f'🚫 Слово "{word}" удалено из списка запрещенных слов!')
            else:
                await message.reply(f'🚫 Слово "{word}" не найдено в списке запрещенных слов!')
        else:
            await message.reply('🚫 Пожалуйста, укажите слово для удаления!')
    else:
        await message.reply('🚫 Вы не админ!')

@dp.message_handler(commands=['getword'])
async def get_banned_words_command(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        banned_words = get_banned_words()
        if banned_words:
            text = '🚫 Список запрещенных слов:\n'
            for word in banned_words:
                text += word + '\n'
            await message.reply(text)
        else:
            await message.reply('🚫 Список запрещенных слов пуст!')
    else:
        await message.reply('🚫 Вы не админ!')

@dp.message_handler(lambda message: message.text.startswith(f'https://t.me/{CHANNEL_ID_TO_DELETE}'))
async def delete_message(message: types.Message):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton('Да', callback_data='yes'))
    keyboard.add(types.InlineKeyboardButton('Нет', callback_data='no'))
    await message.reply('Вы желаете удалить данное сообщение?', reply_markup=keyboard)

link = ''

@dp.callback_query_handler(lambda callback_query: callback_query.data == 'yes')
async def delete_message_yes(callback_query: types.CallbackQuery):
    global link
    link = callback_query.message.reply_to_message.text
    await bot.send_message(ADMIN_ID, f'Пользователь {callback_query.from_user.username} попросил удалить сообщение: {link}')
    await callback_query.message.delete()
    await callback_query.answer('Сообщение отправлено ADMINу для удаления')

@dp.callback_query_handler(lambda callback_query: callback_query.data == 'no')
async def delete_message_no(callback_query: types.CallbackQuery):
    await callback_query.answer('Отмена удаления сообщения')


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
