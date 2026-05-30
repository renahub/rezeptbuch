"""Unit-Tests für das Datenbankmodell (models.py).

Getestet werden:
- Constraints (unique, blank, CASCADE)
- __str__-Verhalten
- Pflichtfelder
"""
import pytest
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from core.models import (
    Category, Ingredient, Recipe, RecipeIngredient, RecipeImage,
)
from core.tests.helpers import make_uploaded_image


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestCategoryModel:
    def test_str_returns_name(self):
        cat = Category.objects.create(name="Dessert")
        assert str(cat) == "Dessert"

    def test_name_is_unique(self):
        Category.objects.create(name="Vegan")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Category.objects.create(name="Vegan")

    def test_name_is_required(self):
        cat = Category(name="")
        with pytest.raises(ValidationError):
            cat.full_clean()


# ---------------------------------------------------------------------------
# Ingredient
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestIngredientModel:
    def test_str_returns_name(self):
        ing = Ingredient.objects.create(name="Zucker")
        assert str(ing) == "Zucker"

    def test_name_is_unique(self):
        Ingredient.objects.create(name="Mehl")
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Ingredient.objects.create(name="Mehl")

    def test_name_is_required(self):
        ing = Ingredient(name="")
        with pytest.raises(ValidationError):
            ing.full_clean()


# ---------------------------------------------------------------------------
# Recipe
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestRecipeModel:
    def test_str_returns_name(self, recipe):
        assert str(recipe) == "Tomatensuppe"

    def test_name_is_unique(self):
        Recipe.objects.create(
            name="Pasta", servings=2, preparation_length=15,
            instructions="Kochen.", rating=2,
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Recipe.objects.create(
                    name="Pasta", servings=2, preparation_length=15,
                    instructions="Kochen.", rating=2,
                )

    def test_default_servings_is_two(self):
        r = Recipe.objects.create(
            name="Salat", preparation_length=10, instructions="X", rating=2,
        )
        assert r.servings == 2

    def test_default_rating_is_two(self):
        r = Recipe.objects.create(
            name="Brot", preparation_length=10, instructions="X",
        )
        assert r.rating == 2

    def test_preparation_length_required(self):
        r = Recipe(name="X", instructions="Y")
        with pytest.raises(ValidationError):
            r.full_clean()

    def test_instructions_required(self):
        r = Recipe(name="X", preparation_length=10)
        with pytest.raises(ValidationError):
            r.full_clean()

    def test_categories_blank_allowed(self):
        """ManyToMany Kategorien sind optional (blank=True)."""
        r = Recipe.objects.create(
            name="Tee", preparation_length=5, instructions="Aufgießen.",
        )
        r.full_clean()  # darf nicht werfen
        assert r.categories.count() == 0

    def test_invalid_rating_raises(self):
        r = Recipe(
            name="X", preparation_length=10, instructions="Y", rating=99,
        )
        with pytest.raises(ValidationError):
            r.full_clean()

    def test_timestamps_auto_set(self, recipe):
        assert recipe.created_at is not None
        assert recipe.updated_at is not None


# ---------------------------------------------------------------------------
# RecipeIngredient (M2M-Through)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestRecipeIngredientModel:
    def test_str_format(self, recipe, ingredient):
        ri = recipe.recipe_ingredients.first()
        assert str(ri) == f"{ri.amount} g Tomate für Tomatensuppe"

    def test_amount_is_required(self, recipe, ingredient):
        ri = RecipeIngredient(recipe=recipe, ingredient=ingredient, unit="g")
        with pytest.raises(ValidationError):
            ri.full_clean()

    def test_unit_is_required(self, recipe, ingredient):
        ri = RecipeIngredient(
            recipe=recipe, ingredient=ingredient, amount=Decimal("100"),
        )
        with pytest.raises(ValidationError):
            ri.full_clean()

    def test_cascade_delete_on_recipe(self, recipe):
        """Wird ein Rezept gelöscht, verschwinden auch seine RecipeIngredients."""
        assert RecipeIngredient.objects.filter(recipe=recipe).exists()
        recipe.delete()
        assert not RecipeIngredient.objects.filter(recipe_id=recipe.pk).exists()

    def test_cascade_delete_on_ingredient(self, recipe, ingredient):
        """Wird eine Zutat gelöscht, verschwinden auch ihre RecipeIngredients."""
        assert RecipeIngredient.objects.filter(ingredient=ingredient).exists()
        ingredient.delete()
        assert not RecipeIngredient.objects.filter(ingredient_id=ingredient.pk).exists()


# ---------------------------------------------------------------------------
# RecipeImage
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestRecipeImageModel:
    def test_str_format(self, recipe):
        img = RecipeImage.objects.create(
            recipe=recipe, image=make_uploaded_image(), is_title=True,
        )
        assert str(img) == f"Bild für {recipe.name}"

    def test_cascade_delete_on_recipe(self, recipe):
        img = RecipeImage.objects.create(
            recipe=recipe, image=make_uploaded_image(),
        )
        recipe.delete()
        assert not RecipeImage.objects.filter(pk=img.pk).exists()

    def test_ordering_title_first(self, recipe):
        """Bilder werden so sortiert, dass Titelbild zuerst kommt (Meta.ordering)."""
        normal = RecipeImage.objects.create(
            recipe=recipe, image=make_uploaded_image("a.png"), is_title=False, order=0,
        )
        title = RecipeImage.objects.create(
            recipe=recipe, image=make_uploaded_image("b.png"), is_title=True, order=1,
        )
        images = list(recipe.images.all())
        assert images[0] == title
        assert images[1] == normal
