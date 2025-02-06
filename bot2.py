import asyncio
import logging
import os
import aiosqlite
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
import pytz  
import matplotlib.pyplot as plt
import io
from datetime import datetime, timedelta
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, CallbackQuery
import random
from dotenv import load_dotenv

load_dotenv()  

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")


logging.basicConfig(level=logging.INFO)

async def get_temperature(city: str):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&units=metric&appid={OPENWEATHER_API_KEY}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                temp = data["main"]["temp"]
                return temp 
            else:
                print(f"Ошибка API OpenWeatherMap: {response.status}")
                return None

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
DB_NAME = "bot_database.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                weight INTEGER,
                height INTEGER,
                age INTEGER,
                activity INTEGER,
                city TEXT,
                calorie_goal INTEGER,
                water_goal INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS water_logs (
                user_id INTEGER,
                date TEXT,
                amount INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS food_logs (
                user_id INTEGER,
                date TEXT,
                food_name TEXT,
                calories REAL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS workout_logs (
                user_id INTEGER,
                date TEXT,
                workout_type TEXT,
                duration INTEGER,
                calories_burned INTEGER
            )
        """)
        await db.commit()

class ProfileSetup(StatesGroup):
    weight = State()
    height = State()
    age = State()
    activity = State()
    city = State()

def get_main_menu():
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="/set_profile"), KeyboardButton(text="/log_water")],
        [KeyboardButton(text="/log_food"), KeyboardButton(text="/log_workout")],
        [KeyboardButton(text="/check_progress"), KeyboardButton(text="📋 Рекомендации")],  
        [KeyboardButton(text="📋 Профиль"), KeyboardButton(text="🔄 Перезапуск")]
    ], resize_keyboard=True)
    return keyboard


# /start
def get_start_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Заполнить профиль", callback_data="set_profile")]
    ])
    return keyboard

@dp.message(Command("start"))
async def start_command(message: Message):
    await message.answer(
        "👋 Привет! Я твой помощник по здоровому образу жизни!\n"
        "Заполни профиль, чтобы я мог рассчитывать твои нормы воды и калорий.",
        reply_markup=get_start_keyboard()
    )

#/set_profile
@dp.callback_query(lambda c: c.data == "set_profile")
async def start_profile_setup(callback: CallbackQuery, state: FSMContext):
    await callback.answer()  
    await set_profile(callback.message, state=state)  

# Перезапуск
@dp.message(F.text == "🔄 Перезапуск")
async def restart_bot(message: Message):
    await message.answer("🔄 Бот перезапускается...")
    await asyncio.sleep(2)
    await start_command(message)

# Заполнение профиля
@dp.message(Command("set_profile"))
async def set_profile(message: Message, state: FSMContext):
    await message.answer("Введите ваш вес (в кг):")
    await state.set_state(ProfileSetup.weight)

@dp.message(ProfileSetup.weight)
async def set_weight(message: Message, state: FSMContext):
    await state.update_data(weight=int(message.text))
    await message.answer("Введите ваш рост (в см):")
    await state.set_state(ProfileSetup.height)

@dp.message(ProfileSetup.height)
async def set_height(message: Message, state: FSMContext):
    await state.update_data(height=int(message.text))
    await message.answer("Введите ваш возраст:")
    await state.set_state(ProfileSetup.age)

@dp.message(ProfileSetup.age)
async def set_age(message: Message, state: FSMContext):
    await state.update_data(age=int(message.text))
    await message.answer("Сколько минут активности у вас в день?")
    await state.set_state(ProfileSetup.activity)

@dp.message(ProfileSetup.activity)
async def set_activity(message: Message, state: FSMContext):
    await state.update_data(activity=int(message.text))
    await message.answer("В каком городе вы находитесь?")
    await state.set_state(ProfileSetup.city)

@dp.message(ProfileSetup.city)
async def set_city(message: Message, state: FSMContext):
    data = await state.update_data(city=message.text)
    city = data["city"]

    temp = await get_temperature(city)
    if temp is None:
        await message.answer("⚠ Не удалось получить температуру. Норма воды будет рассчитана без учёта погоды.")
        temp = 20  

    weight = data["weight"]
    height = data["height"]
    age = data["age"]
    activity = data["activity"]

    # Расчёт нормы воды
    water_goal = weight * 25
    water_goal += (activity // 30) * 150  # +150 мл за каждые 30 мин активности

    if temp > 25:
        water_goal += 250  # Жара больше воды
    elif temp < 0:
        water_goal -= 200  # Мороз меньше воды

    water_goal = min(water_goal, 4000) 
    water_goal = round(water_goal, 2)  


    #   Расчёт нормы калорий
    bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5  # Основной обмен

    if activity < 30:
        calorie_goal = bmr * 1.2  # Малоподвижный образ жизни
    elif activity < 60:
        calorie_goal = bmr * 1.375  # Лёгкая активность
    elif activity < 120:
        calorie_goal = bmr * 1.55  # Средняя активность
    elif activity < 180:
        calorie_goal = bmr * 1.725  # Высокая активность
    else:
        calorie_goal = bmr * 1.9  # Очень активный образ жизни

    calorie_goal = round(calorie_goal, 2) 

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR REPLACE INTO users (user_id, weight, height, age, activity, city, calorie_goal, water_goal) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (message.from_user.id, weight, height, age, activity, city, calorie_goal, water_goal)
        )
        await db.commit()

    await state.clear()
    await message.answer(
        f"✅ Профиль сохранён!\n"
        f"📍 Город: {city} (Температура: {temp}°C)\n"
        f"💧 Ваша дневная норма воды: {water_goal} мл\n"
        f"🔥 Ваша дневная норма калорий: {calorie_goal} ккал",
        reply_markup=get_main_menu()
    )


# выбор даты
class CheckProgress(StatesGroup):
    waiting_for_date = State()

def get_date_keyboard():
    today = datetime.now().strftime("%d-%m-%Y")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%d-%m-%Y") 

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Сегодня", callback_data=f"progress:{today}")],
        [InlineKeyboardButton(text="📆 Вчера", callback_data=f"progress:{yesterday}")],
        [InlineKeyboardButton(text="📅 Ввести дату", callback_data="progress:custom")]
    ])
    return keyboard

# /check_progress
@dp.message(Command("check_progress"))
async def check_progress_request(message: Message):
    await message.answer("📊 Выберите дату для просмотра прогресса:", reply_markup=get_date_keyboard())

# сегодня/вчера
@dp.callback_query(lambda c: c.data.startswith("progress:"))
async def check_progress(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    selected_date = callback.data.split(":")[1]

    if selected_date == "custom":
        await callback.message.answer("📅 Введите дату в формате ДД-ММ-ГГГГ (например, 05-02-2025):")
        await state.set_state(CheckProgress.waiting_for_date) 
    else:
        await show_progress(callback.message, user_id, selected_date)
        await plot_progress_graph(callback.message, user_id, selected_date)
        await callback.answer()

# ввод даты
@dp.message(CheckProgress.waiting_for_date)
async def process_custom_date(message: Message, state: FSMContext):
    user_id = message.from_user.id
    date_input = message.text

    try:
        datetime.strptime(date_input, "%d-%m-%Y")
        await show_progress(message, user_id, date_input)
        await plot_progress_graph(message, user_id, date_input)  
        await state.clear() 
    except ValueError:
        await message.answer("❌ Неверный формат даты. Введите в формате ДД-ММ-ГГГГ (например, 05-02-2025):")

# отчет
async def show_progress(message: Message, user_id: int, selected_date: str):
    db_date = datetime.strptime(selected_date, "%d-%m-%Y").strftime("%Y-%m-%d") 

    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT water_goal, calorie_goal FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user_data = await cursor.fetchone()

        async with db.execute("SELECT SUM(amount) FROM water_logs WHERE user_id = ? AND DATE(date) = ?", (user_id, db_date)) as water_cursor:
            water_total = await water_cursor.fetchone()

        async with db.execute("SELECT SUM(calories) FROM food_logs WHERE user_id = ? AND DATE(date) = ?", (user_id, db_date)) as food_cursor:
            food_total = await food_cursor.fetchone()

        async with db.execute("SELECT SUM(calories_burned) FROM workout_logs WHERE user_id = ? AND DATE(date) = ?", (user_id, db_date)) as workout_cursor:
            burned_total = await workout_cursor.fetchone()

    if not user_data:
        await message.answer("❌ У тебя нет профиля. Используй /set_profile")
        return
    
    water_goal, calorie_goal = user_data
    burned_goal = 500

    water_total = water_total[0] if water_total[0] else 0
    food_total = food_total[0] if food_total[0] else 0
    burned_total = burned_total[0] if burned_total[0] else 0
    balance = food_total - burned_total

    progress_text = f"""📊 Прогресс за {selected_date}:
💧 Вода: {water_total} мл / {water_goal} мл  
🍏 Калории съедено: {food_total} ккал / {calorie_goal} ккал  
🔥 Сожжено калорий: {burned_total} ккал / {burned_goal} ккал  
⚖ Баланс: {balance} ккал  
"""

    await message.answer(progress_text)

# графики
async def plot_progress_graph(message: Message, user_id: int, selected_date: str):
    db_date = datetime.strptime(selected_date, "%d-%m-%Y").strftime("%Y-%m-%d")

    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT water_goal, calorie_goal FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user_data = await cursor.fetchone()

        async with db.execute("SELECT SUM(amount) FROM water_logs WHERE user_id = ? AND DATE(date) = ?", (user_id, db_date)) as water_cursor:
            water_total = await water_cursor.fetchone()

        async with db.execute("SELECT SUM(calories) FROM food_logs WHERE user_id = ? AND DATE(date) = ?", (user_id, db_date)) as food_cursor:
            food_total = await food_cursor.fetchone()

        async with db.execute("SELECT SUM(calories_burned) FROM workout_logs WHERE user_id = ? AND DATE(date) = ?", (user_id, db_date)) as workout_cursor:
            burned_total = await workout_cursor.fetchone()

    water_goal, calorie_goal = user_data
    burned_goal = 500

    water_total = water_total[0] if water_total[0] else 0
    food_total = food_total[0] if food_total[0] else 0
    burned_total = burned_total[0] if burned_total[0] else 0

    categories = ["💧 Вода", "🍏 Калории", "🔥 Сожжено"]
    goal_values = [water_goal, calorie_goal, burned_goal]
    actual_values = [water_total, food_total, burned_total]

    fig, ax = plt.subplots(figsize=(6, 4))
    bar_width = 0.4
    x = range(len(categories))

    ax.bar(x, goal_values, width=bar_width, label="Норма", alpha=0.6)
    ax.bar([i + bar_width for i in x], actual_values, width=bar_width, label="Фактически", alpha=0.8)

    ax.set_xticks([i + bar_width / 2 for i in x])
    ax.set_xticklabels(categories)
    ax.set_ylabel("Единицы измерения")
    ax.set_title(f"📊 Прогресс за {selected_date}")
    ax.legend()

    filename = f"progress_{user_id}.png"
    plt.savefig(filename, format="png")
    plt.close()

    graph = FSInputFile(filename)
    await message.answer_photo(graph, caption=f"📊 График прогресса за {selected_date}")
    os.remove(filename)


LOCAL_TZ = pytz.timezone("Europe/Moscow")  
# логирование воды
class LogWater(StatesGroup):
    amount = State()

#  /log_water
@dp.message(Command("log_water"))
async def ask_water_amount(message: Message, state: FSMContext):
    await message.answer("💦 Сколько мл воды вы выпили?")
    await state.set_state(LogWater.amount)

#Пользователь вводит количество воды
@dp.message(LogWater.amount)
async def save_water_log(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if not message.text.isdigit():
        await message.answer("❌ Пожалуйста, введите число (количество мл воды).")
        return

    amount = int(message.text)
    db_date = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO water_logs (user_id, date, amount) VALUES (?, ?, ?)", (user_id, db_date, amount))
        await db.commit()

        async with db.execute("SELECT SUM(amount) FROM water_logs WHERE user_id = ? AND strftime('%Y-%m-%d', date) = ?", (user_id, db_date[:10])) as water_cursor:
            water_total = await water_cursor.fetchone()

        async with db.execute("SELECT water_goal FROM users WHERE user_id = ?", (user_id,)) as user_cursor:
            user_data = await user_cursor.fetchone()

    water_total = water_total[0] if water_total[0] else 0
    water_goal = user_data[0] if user_data else 2000  
    water_remaining = max(0, water_goal - water_total)

    await state.clear()

    progress_text = f"""💦 Прогресс по воде ({db_date[:10]}):
✅ Добавлено: {amount} мл  
💧 Выпито всего: {water_total} мл / {water_goal} мл  
🔹 Осталось: {water_remaining} мл  
"""

    await message.answer(progress_text)


# логирование еды   
class LogFood(StatesGroup):
    food_name = State()
    food_weight = State()

# данные о калориях из OpenFoodFacts
async def get_food_info(product_name):
    url = f"https://world.openfoodfacts.org/cgi/search.pl?action=process&search_terms={product_name}&json=true"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            products = data.get("products", [])
            if products:
                first_product = products[0]
                return {
                    "name": first_product.get("product_name", "Неизвестно"),
                    "calories": first_product.get("nutriments", {}).get("energy-kcal_100g", 0)
                }
    return None

# /log_food
@dp.message(Command("log_food"))
async def log_food(message: Message, state: FSMContext):
    await message.answer("🍽 Введите название продукта:")
    await state.set_state(LogFood.food_name)

# Получение данных о калориях
@dp.message(LogFood.food_name)
async def get_food_weight(message: Message, state: FSMContext):
    food_name = message.text
    food_info = await get_food_info(food_name)

    if food_info:
        await state.update_data(food_name=food_info["name"], calories_per_100g=food_info["calories"])
        await message.answer(f"🍏 {food_info['name']} содержит {food_info['calories']} ккал на 100 г.\nВведите вес продукта (г):")
        await state.set_state(LogFood.food_weight)
    else:
        await message.answer("❌ Не удалось найти продукт. Попробуйте снова.")
        await state.clear()


LOCAL_TZ = pytz.timezone("Europe/Moscow") 

@dp.message(LogFood.food_weight)
async def save_food_log(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    food_name = data["food_name"]
    calories_per_100g = data["calories_per_100g"]

    try:
        food_weight = int(message.text)
        total_calories = (calories_per_100g * food_weight) / 100 

        db_date = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")  
        display_date = datetime.now(LOCAL_TZ).strftime("%d-%m-%Y")  

        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("INSERT INTO food_logs (user_id, date, food_name, calories) VALUES (?, ?, ?, ?)",
                            (user_id, db_date, food_name, total_calories))
            await db.commit()
            async with db.execute("SELECT SUM(calories) FROM food_logs WHERE user_id = ? AND date = ?", (user_id, db_date)) as food_cursor:
                food_total = await food_cursor.fetchone()

            async with db.execute("SELECT calorie_goal FROM users WHERE user_id = ?", (user_id,)) as user_cursor:
                user_data = await user_cursor.fetchone()

        food_total = food_total[0] if food_total[0] else 0
        calorie_goal = user_data[0] if user_data else 2000  
        calories_remaining = max(0, calorie_goal - food_total)

        await state.clear()

        progress_text = f"""🍽Прогресс по калориям ({display_date}):
✅ Добавлено: {total_calories:.2f} ккал ({food_weight} г {food_name})  
🔥 Потреблено всего: {food_total:.2f} ккал / {calorie_goal} ккал  
🔹 Осталось: {calories_remaining:.2f} ккал  
"""
        await message.answer(progress_text)

    except ValueError:
        await message.answer("❌ Пожалуйста, введите число (вес в граммах).")



# просмотр профиля
@dp.message(Command("profile"))
@dp.message(F.text.casefold() == "📋 профиль")
async def view_profile(message: Message):
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT weight, height, age, activity, city, calorie_goal, water_goal FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()

    if user:
        profile_info = f"""
        👤 ВАШ ПРОФИЛЬ
        ━━━━━━━━━━━━━━━━━━━━
        ⚖️ ВЕС: {user[0]} кг
        📏 РОСТ: {user[1]} см
        🎂 ВОЗРАСТ: {user[2]} лет
        🚴 АКТИВНОСТЬ: {user[3]} мин/день
        📍 ГОРОД: {user[4]}
        ━━━━━━━━━━━━━━━━━━━━
        🍽 ЦЕЛЬ ПО КАЛОРИЯМ: {user[5]} ккал
        💦 ЦЕЛЬ ПО ВОДЕ: {user[6]} мл
        ━━━━━━━━━━━━━━━━━━━━
        """

        await message.answer(profile_info)
    else:
        await message.answer("❌ У тебя пока нет профиля. Используй /set_profile.")


# логирование тренировок
class LogWorkout(StatesGroup):
    workout_type = State()
    duration = State()

# кнопока выбора тренировки
def get_workout_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏃 Кардио тренировка", callback_data="workout:cardio")],
        [InlineKeyboardButton(text="🏋 Силовая тренировка", callback_data="workout:strength")],
        [InlineKeyboardButton(text="🧘 Другое", callback_data="workout:other")]
    ])
    return keyboard

# /log_workout
@dp.message(Command("log_workout"))
async def log_workout(message: Message):
    await message.answer("🏋 Выберите тип тренировки:", reply_markup=get_workout_keyboard())

# выбор типа тренировки
@dp.callback_query(lambda c: c.data.startswith("workout:"))
async def ask_duration(callback: CallbackQuery, state: FSMContext):
    workout_type = callback.data.split(":")[1]
    workout_dict = {
        "cardio": "Кардио тренировка 🏃",
        "strength": "Силовая тренировка 🏋",
        "other": "Другое 🧘"
    }

    await state.update_data(workout_type=workout_dict[workout_type])
    await callback.message.answer(f"⏳ Введите длительность тренировки (в минутах) для {workout_dict[workout_type]}:")
    await state.set_state(LogWorkout.duration)
    await callback.answer()

# длительности тренировки
@dp.message(LogWorkout.duration)
async def save_workout_log(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    workout_type = data["workout_type"]

    try:
        duration = int(message.text)

        # расчет калорий: 
        # Кардио - 10 ккал/мин, 
        # Силовая - 8 ккал/мин, 
        # Другое - 5 ккал/мин
        calories_burned = {
            "Кардио тренировка 🏃": duration * 10,
            "Силовая тренировка 🏋": duration * 8,
            "Другое 🧘": duration * 5
        }[workout_type]

        # Получаем текущую дату в формате БД
        local_date = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")

        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("INSERT INTO workout_logs (user_id, date, workout_type, duration, calories_burned) VALUES (?, ?, ?, ?, ?)",
                            (user_id, local_date, workout_type, duration, calories_burned))
            await db.commit()

            async with db.execute("SELECT SUM(calories_burned) FROM workout_logs WHERE user_id = ? AND date = ?", (user_id, local_date)) as workout_cursor:
                burned_total = await workout_cursor.fetchone()

        burned_total = burned_total[0] if burned_total[0] else 0

        await state.clear()

        progress_text = f"""🔥 Прогресс по тренировкам:
✅ Добавлено: {calories_burned} ккал ({duration} мин {workout_type})  
🏋 Всего сожжено: {burned_total} ккал  
"""
        await message.answer(progress_text)

    except ValueError:
        await message.answer("❌ Введите число (продолжительность тренировки в минутах).")


@dp.message(Command("id"))
async def send_user_id(message: Message):
    await message.answer(f"Твой ID: `{message.from_user.id}`")

LOW_CALORIE_FOODS = [
    "🥒 Огурец (15 ккал / 100 г)",
    "🥦 Брокколи (34 ккал / 100 г)",
    "🍏 Яблоко (52 ккал / 100 г)",
    "🥗 Салат (25 ккал / 100 г)",
    "🍓 Клубника (33 ккал / 100 г)",
    "🍊 Апельсин (47 ккал / 100 г)",
    "🍅 Помидор (18 ккал / 100 г)"
]

LOW_INTENSITY_WORKOUTS = [
    "🚶 Прогулка 30 минут",
    "🧘 Йога 20 минут",
    "🏊 Плавание 15 минут",
    "🚴 Велосипед 20 минут",
    "🏋 Силовая тренировка 10 минут"
]

@dp.message(F.text == "📋 Рекомендации")
async def get_recommendations(message: Message):
    user_id = message.from_user.id
    db_date = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT SUM(calories) FROM food_logs WHERE user_id = ? AND date = ?", (user_id, db_date)) as food_cursor:
            food_total = await food_cursor.fetchone()
        async with db.execute("SELECT calorie_goal FROM users WHERE user_id = ?", (user_id,)) as user_cursor:
            user_data = await user_cursor.fetchone()
        async with db.execute("SELECT SUM(calories_burned) FROM workout_logs WHERE user_id = ? AND date = ?", (user_id, db_date)) as workout_cursor:
            burned_total = await workout_cursor.fetchone()

    calorie_goal = user_data[0] if user_data else 2000
    food_total = food_total[0] if food_total[0] else 0
    burned_total = burned_total[0] if burned_total[0] else 0
    balance = food_total - burned_total

    # рекомендации
    food_recommendation = ""
    if food_total > calorie_goal:
        food_recommendation = f"⚠️ Ты превысил лимит калорий! Попробуй вместо этого {random.choice(LOW_CALORIE_FOODS)}."

    workout_recommendation = ""
    if burned_total < 300:  # Если сожжено < 300 ккал, рекомендуем тренировку
        workout_recommendation = f"💡 Для баланса попробуй {random.choice(LOW_INTENSITY_WORKOUTS)}!"

    recommendations_text = f"""📋 Рекомендации на {db_date}:
🍏 Питание: {food_recommendation if food_recommendation else "✅ Калории в пределах нормы!"}
🏋 Тренировки: {workout_recommendation if workout_recommendation else "✅ Ты хорошо потренировался!"}
"""

    await message.answer(recommendations_text)


async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
