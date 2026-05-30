"""Gemeinsame Fixtures für die Test-Suite des core-Pakets.

Bild-Helfer (make_png_bytes, make_uploaded_image) liegen in helpers.py
und werden bei Bedarf direkt importiert.
"""
import pytest
from decimal import Decimal

from core.models import Category, Ingredient, Recipe, RecipeIngredient


@pytest.fixture
def category(db):
    return Category.objects.create(name="Hauptgericht")


@pytest.fixture
def ingredient(db):
    return Ingredient.objects.create(name="Tomate")


@pytest.fixture
def recipe(db, category, ingredient):
    """Ein vollständig befülltes Standardrezept."""
    r = Recipe.objects.create(
        name="Tomatensuppe",
        servings=4,
        preparation_length=30,
        instructions="Tomaten kochen.",
        rating=3,
    )
    r.categories.add(category)
    RecipeIngredient.objects.create(
        recipe=r, ingredient=ingredient, amount=Decimal("500"), unit="g"
    )
    return r
