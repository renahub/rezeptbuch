"""Unit-Tests für die Formulare (forms.py).

Getestet werden laut Thesis Kapitel 6:
- Validierung RecipeIngredientFormSet
- Validierung CategoryFormSet
- Fehlermeldungen
"""
import pytest

from core.forms import (
    CategoryFormSet,
    RecipeCategoryForm,
    RecipeForm,
    RecipeIngredientForm,
    RecipeIngredientFormSet,
)
from core.models import Category, Ingredient, Recipe


# ---------------------------------------------------------------------------
# RecipeForm (Hauptformular)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestRecipeForm:
    def test_valid_form(self):
        form = RecipeForm(data={
            "name": "Testrezept",
            "servings": 2,
            "preparation_length": 15,
            "instructions": "Anleitung",
            "rating": 3,
        })
        assert form.is_valid(), form.errors

    def test_missing_name_invalid(self):
        form = RecipeForm(data={
            "name": "",
            "servings": 2,
            "preparation_length": 15,
            "instructions": "Anleitung",
            "rating": 3,
        })
        assert not form.is_valid()
        assert "name" in form.errors

    def test_missing_preparation_length_invalid(self):
        form = RecipeForm(data={
            "name": "X",
            "servings": 2,
            "preparation_length": "",
            "instructions": "Y",
            "rating": 3,
        })
        assert not form.is_valid()
        assert "preparation_length" in form.errors

    def test_invalid_rating_choice(self):
        form = RecipeForm(data={
            "name": "X",
            "servings": 2,
            "preparation_length": 15,
            "instructions": "Y",
            "rating": 99,
        })
        assert not form.is_valid()
        assert "rating" in form.errors


# ---------------------------------------------------------------------------
# RecipeIngredientForm (Einzelnes Zutaten-Formular)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestRecipeIngredientForm:
    def test_completely_empty_row_is_valid(self):
        """Komplett leere Zeile → vom Formset später ignoriert."""
        form = RecipeIngredientForm(data={
            "ingredient": "", "new_ingredient": "", "amount": "", "unit": "",
        })
        assert form.is_valid(), form.errors

    def test_existing_ingredient_with_amount_and_unit_valid(self):
        ing = Ingredient.objects.create(name="Mehl")
        form = RecipeIngredientForm(data={
            "ingredient": ing.pk,
            "new_ingredient": "",
            "amount": "200",
            "unit": "g",
        })
        assert form.is_valid(), form.errors

    def test_new_ingredient_with_amount_and_unit_valid(self):
        form = RecipeIngredientForm(data={
            "ingredient": "",
            "new_ingredient": "Hefe",
            "amount": "1",
            "unit": "Stk",
        })
        assert form.is_valid(), form.errors

    def test_ingredient_without_amount_invalid(self):
        ing = Ingredient.objects.create(name="Salz")
        form = RecipeIngredientForm(data={
            "ingredient": ing.pk,
            "new_ingredient": "",
            "amount": "",
            "unit": "g",
        })
        assert not form.is_valid()
        # Fehlermeldung enthält das Wort "Menge"
        errors_text = " ".join(form.non_field_errors())
        assert "Menge" in errors_text

    def test_ingredient_without_unit_invalid(self):
        ing = Ingredient.objects.create(name="Pfeffer")
        form = RecipeIngredientForm(data={
            "ingredient": ing.pk,
            "new_ingredient": "",
            "amount": "5",
            "unit": "",
        })
        assert not form.is_valid()
        errors_text = " ".join(form.non_field_errors())
        assert "Einheit" in errors_text


# ---------------------------------------------------------------------------
# RecipeIngredientFormSet
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestRecipeIngredientFormSet:
    @pytest.fixture
    def parent_recipe(self):
        return Recipe.objects.create(
            name="Parent", servings=2, preparation_length=10,
            instructions="x", rating=2,
        )

    def test_empty_formset_valid(self, parent_recipe):
        formset = RecipeIngredientFormSet(
            data={
                "recipe_ingredients-TOTAL_FORMS": "0",
                "recipe_ingredients-INITIAL_FORMS": "0",
                "recipe_ingredients-MIN_NUM_FORMS": "0",
                "recipe_ingredients-MAX_NUM_FORMS": "1000",
            },
            instance=parent_recipe,
            prefix="recipe_ingredients",
        )
        assert formset.is_valid(), formset.errors

    def test_one_valid_row(self, parent_recipe):
        ing = Ingredient.objects.create(name="Butter")
        formset = RecipeIngredientFormSet(
            data={
                "recipe_ingredients-TOTAL_FORMS": "1",
                "recipe_ingredients-INITIAL_FORMS": "0",
                "recipe_ingredients-MIN_NUM_FORMS": "0",
                "recipe_ingredients-MAX_NUM_FORMS": "1000",
                "recipe_ingredients-0-ingredient": ing.pk,
                "recipe_ingredients-0-new_ingredient": "",
                "recipe_ingredients-0-amount": "100",
                "recipe_ingredients-0-unit": "g",
            },
            instance=parent_recipe,
            prefix="recipe_ingredients",
        )
        assert formset.is_valid(), formset.errors

    def test_row_with_ingredient_but_no_amount_invalid(self, parent_recipe):
        ing = Ingredient.objects.create(name="Eier")
        formset = RecipeIngredientFormSet(
            data={
                "recipe_ingredients-TOTAL_FORMS": "1",
                "recipe_ingredients-INITIAL_FORMS": "0",
                "recipe_ingredients-MIN_NUM_FORMS": "0",
                "recipe_ingredients-MAX_NUM_FORMS": "1000",
                "recipe_ingredients-0-ingredient": ing.pk,
                "recipe_ingredients-0-new_ingredient": "",
                "recipe_ingredients-0-amount": "",
                "recipe_ingredients-0-unit": "Stk",
            },
            instance=parent_recipe,
            prefix="recipe_ingredients",
        )
        assert not formset.is_valid()


# ---------------------------------------------------------------------------
# RecipeCategoryForm und CategoryFormSet
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestRecipeCategoryForm:
    def test_existing_category_valid(self):
        cat = Category.objects.create(name="Snack")
        form = RecipeCategoryForm(data={"category": cat.pk, "new_category": ""})
        assert form.is_valid(), form.errors

    def test_new_category_valid(self):
        form = RecipeCategoryForm(data={"category": "", "new_category": "Frühstück"})
        assert form.is_valid(), form.errors

    def test_both_fields_invalid(self):
        """Sowohl bestehende als auch neue Kategorie → Fehlermeldung."""
        cat = Category.objects.create(name="Existing")
        form = RecipeCategoryForm(data={
            "category": cat.pk,
            "new_category": "Andere",
        })
        assert not form.is_valid()
        errors_text = " ".join(form.non_field_errors())
        assert "entweder" in errors_text.lower() or "nicht beides" in errors_text.lower()

    def test_both_empty_valid(self):
        """Leere Zeile ist erlaubt (vom Formset später ignoriert)."""
        form = RecipeCategoryForm(data={"category": "", "new_category": ""})
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestCategoryFormSet:
    def test_single_empty_form_valid(self):
        formset = CategoryFormSet(
            data={
                "categories-TOTAL_FORMS": "1",
                "categories-INITIAL_FORMS": "0",
                "categories-MIN_NUM_FORMS": "0",
                "categories-MAX_NUM_FORMS": "1000",
                "categories-0-category": "",
                "categories-0-new_category": "",
            },
            prefix="categories",
        )
        assert formset.is_valid(), formset.errors

    def test_multiple_new_categories(self):
        formset = CategoryFormSet(
            data={
                "categories-TOTAL_FORMS": "2",
                "categories-INITIAL_FORMS": "0",
                "categories-MIN_NUM_FORMS": "0",
                "categories-MAX_NUM_FORMS": "1000",
                "categories-0-category": "",
                "categories-0-new_category": "Vegan",
                "categories-1-category": "",
                "categories-1-new_category": "Glutenfrei",
            },
            prefix="categories",
        )
        assert formset.is_valid(), formset.errors

    def test_one_invalid_row_breaks_set(self):
        cat = Category.objects.create(name="Existierend")
        formset = CategoryFormSet(
            data={
                "categories-TOTAL_FORMS": "1",
                "categories-INITIAL_FORMS": "0",
                "categories-MIN_NUM_FORMS": "0",
                "categories-MAX_NUM_FORMS": "1000",
                "categories-0-category": cat.pk,
                "categories-0-new_category": "Doppelt",
            },
            prefix="categories",
        )
        assert not formset.is_valid()
