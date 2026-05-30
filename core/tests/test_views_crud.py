"""Unit-Tests für die CRUD-Views (views.py).

Getestet werden:
- Anlegen (Create)
- Bearbeiten (Update)
- Löschen (Delete)
- Detailansicht (Read)
- Weiterleitung nach Aktion (Redirect)
"""
import pytest
from django.urls import reverse

from core.models import Category, Recipe
from core.tests.helpers import make_uploaded_image


# ---------------------------------------------------------------------------
# Detail / Listenansicht (READ)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestRecipeDetailView:
    def test_detail_view_shows_recipe(self, client, recipe):
        response = client.get(reverse("core:recipe", kwargs={"pk": recipe.pk}))
        assert response.status_code == 200
        assert "Tomatensuppe" in response.content.decode("utf-8")

    def test_detail_view_returns_404_for_unknown(self, client):
        response = client.get(reverse("core:recipe", kwargs={"pk": 9999}))
        assert response.status_code == 404

    def test_detail_view_uses_correct_template(self, client, recipe):
        response = client.get(reverse("core:recipe", kwargs={"pk": recipe.pk}))
        assert "core/recipe_detail.html" in [t.name for t in response.templates]


@pytest.mark.django_db
class TestRecipeListView:
    def test_list_view_returns_200(self, client, recipe):
        response = client.get(reverse("core:recipe_list"))
        assert response.status_code == 200

    def test_list_view_contains_recipes(self, client, recipe):
        response = client.get(reverse("core:recipe_list"))
        assert recipe in response.context["recipes"]


@pytest.mark.django_db
class TestCategoryListView:
    def test_category_list_returns_200(self, client, category):
        response = client.get(reverse("core:category_list"))
        assert response.status_code == 200
        assert category in response.context["categories"]

    def test_recipes_by_category(self, client, recipe, category):
        response = client.get(
            reverse("core:recipe_category", kwargs={"category_id": category.pk})
        )
        assert response.status_code == 200
        assert recipe in response.context["recipes"]


# ---------------------------------------------------------------------------
# Anlegen (CREATE)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestRecipeCreateView:
    def test_get_create_form(self, client):
        response = client.get(reverse("core:recipe_create"))
        assert response.status_code == 200
        assert "form" in response.context

    def _post_data(self, name="Neues Rezept"):
        return {
            "name": name,
            "servings": 2,
            "preparation_length": 20,
            "instructions": "Testanleitung",
            "rating": 3,
            # Leeres RecipeIngredient-Inline-Formset
            "recipe_ingredients-TOTAL_FORMS": "0",
            "recipe_ingredients-INITIAL_FORMS": "0",
            "recipe_ingredients-MIN_NUM_FORMS": "0",
            "recipe_ingredients-MAX_NUM_FORMS": "1000",
            # Leeres Kategorie-Formset (1 leere extra)
            "categories-TOTAL_FORMS": "1",
            "categories-INITIAL_FORMS": "0",
            "categories-MIN_NUM_FORMS": "0",
            "categories-MAX_NUM_FORMS": "1000",
            "categories-0-category": "",
            "categories-0-new_category": "",
            # Leeres Bild-Inline-Formset
            "images-TOTAL_FORMS": "0",
            "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0",
            "images-MAX_NUM_FORMS": "1000",
        }

    def test_create_recipe_persists(self, client):
        response = client.post(reverse("core:recipe_create"), self._post_data())
        assert Recipe.objects.filter(name="Neues Rezept").exists()
        # Weiterleitung zur Detailseite
        new_recipe = Recipe.objects.get(name="Neues Rezept")
        assert response.status_code == 302
        assert response.url == reverse(
            "core:recipe", kwargs={"pk": new_recipe.pk}
        )

    def test_create_with_new_category(self, client):
        data = self._post_data(name="Mit Kategorie")
        data["categories-0-new_category"] = "Suppe"
        client.post(reverse("core:recipe_create"), data)
        r = Recipe.objects.get(name="Mit Kategorie")
        assert r.categories.filter(name="Suppe").exists()

    def test_create_invalid_returns_form(self, client):
        """Ungültige Eingabe (fehlender Name) führt nicht zur Speicherung."""
        data = self._post_data()
        data["name"] = ""  # Pflichtfeld leer
        response = client.post(reverse("core:recipe_create"), data)
        assert response.status_code == 200  # gerendert, kein Redirect
        assert not Recipe.objects.filter(name="").exists()


# ---------------------------------------------------------------------------
# Bearbeiten (UPDATE)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestRecipeUpdateView:
    def test_get_edit_form(self, client, recipe):
        response = client.get(
            reverse("core:recipe_edit", kwargs={"pk": recipe.pk})
        )
        assert response.status_code == 200
        assert response.context["form"].instance == recipe

    def test_update_changes_field(self, client, recipe, category):
        data = {
            "name": "Tomatensuppe Deluxe",
            "servings": 6,
            "preparation_length": 45,
            "instructions": "Geänderte Anleitung",
            "rating": 3,
            "recipe_ingredients-TOTAL_FORMS": "1",
            "recipe_ingredients-INITIAL_FORMS": "1",
            "recipe_ingredients-MIN_NUM_FORMS": "0",
            "recipe_ingredients-MAX_NUM_FORMS": "1000",
            "recipe_ingredients-0-id": recipe.recipe_ingredients.first().pk,
            "recipe_ingredients-0-recipe": recipe.pk,
            "recipe_ingredients-0-ingredient": recipe.recipe_ingredients.first().ingredient.pk,
            "recipe_ingredients-0-new_ingredient": "",
            "recipe_ingredients-0-amount": "500",
            "recipe_ingredients-0-unit": "g",
            "categories-TOTAL_FORMS": "1",
            "categories-INITIAL_FORMS": "1",
            "categories-MIN_NUM_FORMS": "0",
            "categories-MAX_NUM_FORMS": "1000",
            "categories-0-category": category.pk,
            "categories-0-new_category": "",
            "images-TOTAL_FORMS": "0",
            "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0",
            "images-MAX_NUM_FORMS": "1000",
        }
        response = client.post(
            reverse("core:recipe_edit", kwargs={"pk": recipe.pk}), data
        )
        recipe.refresh_from_db()
        assert recipe.name == "Tomatensuppe Deluxe"
        assert recipe.servings == 6
        assert recipe.rating == 3
        assert response.status_code == 302  # Redirect nach erfolgreichem Save


# ---------------------------------------------------------------------------
# Löschen (DELETE)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestRecipeDeleteView:
    def test_delete_recipe_redirects_to_list(self, client, recipe):
        response = client.post(
            reverse("core:recipe_delete", kwargs={"pk": recipe.pk})
        )
        assert response.status_code == 302
        assert response.url == reverse("core:recipe_list")
        assert not Recipe.objects.filter(pk=recipe.pk).exists()

    def test_get_confirm_page(self, client, recipe):
        response = client.get(
            reverse("core:recipe_delete", kwargs={"pk": recipe.pk})
        )
        assert response.status_code == 200


@pytest.mark.django_db
class TestCategoryDeleteView:
    def test_delete_category_redirects(self, client, category):
        response = client.post(
            reverse("core:category_delete", kwargs={"pk": category.pk})
        )
        assert response.status_code == 302
        assert response.url == reverse("core:category_list")
        assert not Category.objects.filter(pk=category.pk).exists()


@pytest.mark.django_db
class TestCategoryRenameView:
    def test_rename_changes_name(self, client, category):
        response = client.post(
            reverse("core:category_rename", kwargs={"pk": category.pk}),
            {"name": "Vorspeise"},
        )
        category.refresh_from_db()
        assert category.name == "Vorspeise"
        assert response.status_code == 302

    def test_rename_empty_keeps_name(self, client, category):
        original = category.name
        client.post(
            reverse("core:category_rename", kwargs={"pk": category.pk}),
            {"name": "   "},
        )
        category.refresh_from_db()
        assert category.name == original


@pytest.mark.django_db
class TestRecipeImageUpload:
    def test_upload_creates_recipe_image(self, client, recipe):
        """Ein erfolgreicher Upload legt ein RecipeImage in der DB an."""
        before = recipe.images.count()
        client.post(
            reverse("core:recipe_image_upload", kwargs={"pk": recipe.pk}),
            {"image": make_uploaded_image()},
        )
        assert recipe.images.count() == before + 1

    def test_first_uploaded_image_is_title(self, client, recipe):
        """Wenn noch kein Bild existiert, wird das erste hochgeladene zum Titelbild."""
        recipe.images.all().delete()  # Sauberer Startzustand
        client.post(
            reverse("core:recipe_image_upload", kwargs={"pk": recipe.pk}),
            {"image": make_uploaded_image()},
        )
        assert recipe.images.filter(is_title=True).count() == 1

    def test_second_upload_is_not_title(self, client, recipe):
        """Ein zweiter Upload bekommt is_title=False. Das erste Bild bleibt Titel."""
        recipe.images.all().delete()
        url = reverse("core:recipe_image_upload", kwargs={"pk": recipe.pk})
        client.post(url, {"image": make_uploaded_image("first.png")})
        client.post(url, {"image": make_uploaded_image("second.png")})
        assert recipe.images.count() == 2
        assert recipe.images.filter(is_title=True).count() == 1

    def test_upload_redirects_to_recipe_detail(self, client, recipe):
        """Nach dem Upload wird auf die Rezept-Detailseite weitergeleitet."""
        response = client.post(
            reverse("core:recipe_image_upload", kwargs={"pk": recipe.pk}),
            {"image": make_uploaded_image()},
        )
        assert response.status_code == 302
        assert response.url == reverse("core:recipe", kwargs={"pk": recipe.pk})

    def test_post_without_image_does_not_crash(self, client, recipe):
        """POST ohne Bild-Datei → kein Crash, weiterhin Redirect."""
        before = recipe.images.count()
        response = client.post(
            reverse("core:recipe_image_upload", kwargs={"pk": recipe.pk}),
        )
        assert response.status_code == 302
        assert recipe.images.count() == before  # nichts hinzugefügt