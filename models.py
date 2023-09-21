from sqlalchemy import Column, Integer, String, ForeignKey, Table, Enum, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

# Define the many-to-many relationship between recipes and ingredients
recipe_ingredient = Table('recipe_ingredient', Base.metadata,
                          Column('recipe_id', Integer, ForeignKey('recipes.id')),
                          Column('ingredient_id', Integer, ForeignKey('ingredients.id'))
                          )

States = Enum(
    'start',
    'ask_preferences',
    'restrictions_choice',
    'exclude_products',
    'include_products',
    'give_recipe',
    'continue_choice',
    'end'
)


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(255))
    name = Column(String(255))


class Conversation(Base):
    __tablename__ = 'conversations'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", backref='conversations')
    state = Column(States)


class Recipe(Base):
    __tablename__ = 'recipes'

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(String(500))
    url = Column(String(300))
    # Define the many-to-many relationship between recipes and ingredients
    ingredients = relationship('Ingredient', secondary=recipe_ingredient,
                               back_populates='recipes')


class Ingredient(Base):
    __tablename__ = 'ingredients'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)

    # Define the many-to-many relationship between recipes and ingredients
    recipes = relationship('Recipe', secondary=recipe_ingredient, back_populates='ingredients')


class Preferences(Base):
    __tablename__ = 'preferences'
    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey('conversations.id'))
    conversation = relationship('Conversation', backref='preferences')
    ingredient_id = Column(Integer, ForeignKey('ingredients.id'))
    ingredient = relationship('Ingredient', backref='preferences')
    preferable = Column(Boolean)
