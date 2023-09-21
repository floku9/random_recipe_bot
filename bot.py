import configparser
import random

import telebot
from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker
from models import Recipe, Ingredient, Base, User, Conversation, Preferences
from telebot.types import ReplyKeyboardMarkup
import configparser


config = configparser.ConfigParser()
config.read("config.ini")
# Set up the database connection

engine = create_engine(config["db"]["connection_string"])
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)
session = DBSession()

# Set up the Telegram bot
TOKEN = config["bot"]["token"]
bot = telebot.TeleBot(TOKEN)


# Define the /start command handler
@bot.message_handler(commands=['start'])
def start_handler(message):
    user = session.query(User).filter(User.telegram_id == str(message.chat.id)).first()
    if not user:
        user = User(telegram_id=str(message.chat.id))
        session.add(user)
        session.commit()
    bot.send_message(chat_id=message.chat.id,
                     text='Я рецептный бот, помогу тебе, если ты не знаешь что приготовить.'
                          'Напиши /help чтобы увидеть список команд')


# Define the /help command handler
@bot.message_handler(commands=['help'])
def help_handler(message):
    help_text = """
    Available commands:
    /start - Старт бота
    /help - Показать help сообщение
    /recipe - Получить рандомный рецепт
    """
    bot.send_message(chat_id=message.chat.id, text=help_text)


@bot.message_handler(commands=['recipe'])
def random_recipe_handler(message):
    current_user = session.query(User).filter(User.telegram_id == str(message.chat.id)).first()
    conversation = Conversation(user_id=current_user.id, state='ask_preferences')
    unfinished_conversations = session.query(Conversation).join(User).filter(
        Conversation.user_id == current_user.id and Conversation.state != 'end').all()
    if unfinished_conversations:
        for conv in unfinished_conversations:
            conv.state = 'end'
    session.add(conversation)
    session.commit()
    state_router(message, conversation)


def state_router(message, conversation: Conversation, **kwargs):
    match conversation.state:
        case 'ask_preferences':
            ask_preferences_handler(message=message,
                                    conversation=conversation)
        case 'restrictions_choice':
            bot.register_next_step_handler(message=message, callback=preferences_choice_handler,
                                           conversation=conversation)
        case 'exclude_products':
            bot.register_next_step_handler(message=message, callback=product_preferences_handler,
                                           conversation=conversation, preferable=False)
        case 'include_products':
            bot.register_next_step_handler(message=message, callback=product_preferences_handler,
                                           conversation=conversation, preferable=True)
        case 'give_recipe':
            give_recipe_handler(message, conversation)
        case 'continue_choice':
            bot.register_next_step_handler(message, callback=continue_conversation_choice_handler,
                                           conversation=conversation,
                                           unfinished_conversation=kwargs['unfinished_conversation'])
        case _:
            handle_message(message)


def ask_preferences_handler(message, conversation: Conversation):
    restrictions_kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    restrictions_kb.add("Исключить продукты", 'Обязательные продукты',
                        'Получить рецепт')
    bot.send_message(chat_id=message.chat.id,
                     text="Хотите добавить ограничения для рецепта?",
                     reply_markup=restrictions_kb)
    conversation.state = 'restrictions_choice'
    state_router(message, conversation)


def preferences_choice_handler(message, conversation: Conversation):
    if message.text == 'Исключить продукты':
        bot.send_message(chat_id=message.chat.id,
                         text='Напишите продукты которые вы не хотите видеть в рецепте через ",".')
        conversation.state = 'exclude_products'
    elif message.text == "Обязательные продукты":
        bot.send_message(chat_id=message.chat.id,
                         text='Напишите продукты которые вы хотите обязательно '
                              'видеть в рецепте через ",".')
        conversation.state = 'include_products'
    elif message.text == "Получить рецепт":
        conversation.state = 'give_recipe'
    state_router(message, conversation)


def product_preferences_handler(message, conversation: Conversation, preferable: bool):
    given_products: str = message.text.split(',')
    for product in given_products:
        product = product.strip().lower()
        db_product = session.query(Ingredient).filter(Ingredient.name == product).first()
        if db_product:
            preference = Preferences(conversation=conversation, ingredient=db_product, preferable=preferable)
            session.add(preference)

        else:
            bot.send_message(chat_id=message.chat.id,
                             text=f'Продукт с названием {product} не был найден.')
        session.commit()
    bot.send_message(chat_id=message.chat.id,
                     text='Продукты были успешно исключены.')
    conversation.state = 'ask_preferences'
    state_router(message, conversation)


def give_recipe_handler(message, conversation: Conversation):
    preferences: list = session.query(Preferences).join(Conversation).filter(
        Conversation.id == int(conversation.id)).all()
    exclude_ingredient_ids = [pref.ingredient_id for pref in preferences if not pref.preferable]
    include_ingredient_ids = [pref.ingredient_id for pref in preferences if pref.preferable]

    valid_recipes = (
        session.query(Recipe)
        .join(Recipe.ingredients)
        .filter(
            ~Ingredient.id.in_(exclude_ingredient_ids),
            or_(
                len(include_ingredient_ids) == 0,
                Ingredient.id.in_(include_ingredient_ids)
            )
        )
    ).all()
    if valid_recipes:
        recipe = random.choice(valid_recipes)
        bot.send_message(message.chat.id, "Мы нашли рецепт для вас!")
        bot.send_message(message.chat.id, f"Название: {recipe.title}\n"
                                          f"Описание: {recipe.description}\n"
                                          f"Ссылка: {recipe.url}")
        conversation.state = 'end'
    else:
        bot.send_message(message.chat.id, "Мы не смогли найти рецепт для вас. "
                                          "Попробуйте еще раз с другими ограничениями")


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    bot.send_message(message.chat.id, "Извините, я вас не понимаю")
    unfinished_conversation = session.query(Conversation).join(User).filter(
        Conversation.user_id == message.chat.id and Conversation.state != 'end').first()
    if unfinished_conversation:
        current_conversation = Conversation(user_id=message.chat.id, state='continue_choice')
        yes_no_kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        yes_no_kb.add("Да", "Нет")
        bot.send_message(message.chat.id,
                         "Кажется у вас есть незаконченый запрос рецепта. Хотите продолжить?",
                         reply_markup=yes_no_kb)
        session.add(current_conversation)
        session.commit()
        state_router(message, current_conversation, unfinished_conversation=unfinished_conversation)

    else:
        bot.send_message(message.chat.id, "Если вы хотите получить новый рецепт, напишите /recipe")


def continue_conversation_choice_handler(message, conversation, unfinished_conversation):
    conversation.state = 'end'
    if message.text == 'Да':
        state_router(message, unfinished_conversation)
    else:
        bot.send_message(message.chat.id, "Если вы хотите получить новый рецепт, напишите /recipe")


bot.polling()
