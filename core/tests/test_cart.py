"""Unit-Tests für den Einkaufskorb (Cart-Views in views.py).

Getestet werden:
- Hinzufügen
- Aggregation gleicher Zutaten
- Portionsfaktor
- Löschen
"""
import pytest
from decimal import Decimal
from django.urls import reverse

from core.models import Ingredient, Recipe, RecipeIngredient


@pytest.fixture
def two_recipes_same_ingredient(db, category):
    """Zwei Rezepte, die beide 'Tomate' (g) enthalten für Aggregations-Tests."""
    tomate = Ingredient.objects.create(name="Tomate")
    zwiebel = Ingredient.objects.create(name="Zwiebel")

    r1 = Recipe.objects.create(
        name="Suppe", servings=2, preparation_length=20,
        instructions="x", rating=2,
    )
    RecipeIngredient.objects.create(recipe=r1, ingredient=tomate, amount=200, unit="g")
    RecipeIngredient.objects.create(recipe=r1, ingredient=zwiebel, amount=1, unit="Stk")

    r2 = Recipe.objects.create(
        name="Salat", servings=2, preparation_length=10,
        instructions="x", rating=2,
    )
    RecipeIngredient.objects.create(recipe=r2, ingredient=tomate, amount=300, unit="g")

    return r1, r2


# ---------------------------------------------------------------------------
# Hinzufügen
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestCartAdd:
    def test_add_recipe_creates_items(self, client, recipe):
        client.post(
            reverse("core:cart_add", kwargs={"pk": recipe.pk}),
            {"servings": recipe.servings},
        )
        cart = client.session["shopping_cart"]
        assert len(cart["items"]) == 1
        assert cart["items"][0]["ingredient_name"] == "Tomate"
        assert cart["items"][0]["unit"] == "g"

    def test_add_redirects_to_detail(self, client, recipe):
        response = client.post(
            reverse("core:cart_add", kwargs={"pk": recipe.pk}),
            {"servings": recipe.servings},
        )
        assert response.status_code == 302
        assert response.url == reverse("core:recipe", kwargs={"pk": recipe.pk})

    def test_invalid_servings_does_not_add(self, client, recipe):
        client.post(
            reverse("core:cart_add", kwargs={"pk": recipe.pk}),
            {"servings": "0"},
        )
        cart = client.session.get("shopping_cart", {"items": []})
        assert cart["items"] == []

    def test_non_numeric_servings_does_not_add(self, client, recipe):
        client.post(
            reverse("core:cart_add", kwargs={"pk": recipe.pk}),
            {"servings": "abc"},
        )
        cart = client.session.get("shopping_cart", {"items": []})
        assert cart["items"] == []


# ---------------------------------------------------------------------------
# Portionsfaktor (Skalierung der Mengen)
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestCartPortionScaling:
    def test_doubling_servings_doubles_amount(self, client, recipe):
        """Doppelte Portionen → doppelte Menge."""
        client.post(
            reverse("core:cart_add", kwargs={"pk": recipe.pk}),
            {"servings": recipe.servings * 2},
        )
        cart = client.session["shopping_cart"]
        amount = Decimal(cart["items"][0]["amount"])
        # Ausgangsmenge 500g für 4 Portionen → 1000g für 8 Portionen
        assert amount == Decimal("1000.00") or amount == Decimal("1000")

    def test_halving_servings_halves_amount(self, client, recipe):
        client.post(
            reverse("core:cart_add", kwargs={"pk": recipe.pk}),
            {"servings": Decimal(recipe.servings) / 2},
        )
        cart = client.session["shopping_cart"]
        amount = Decimal(cart["items"][0]["amount"])
        assert amount == Decimal("250.00") or amount == Decimal("250")


# ---------------------------------------------------------------------------
# Aggregation gleicher Zutaten in der Anzeige
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestCartAggregation:
    def test_aggregates_same_name_and_unit(self, client, two_recipes_same_ingredient):
        r1, r2 = two_recipes_same_ingredient
        client.post(reverse("core:cart_add", kwargs={"pk": r1.pk}),
                    {"servings": r1.servings})
        client.post(reverse("core:cart_add", kwargs={"pk": r2.pk}),
                    {"servings": r2.servings})

        response = client.get(reverse("core:shopping_cart"))
        shopping_list = response.context["shopping_list"]

        tomate = next(i for i in shopping_list if i["name"].lower() == "tomate")
        # 200 + 300 = 500
        assert tomate["amount"] == Decimal("500")
        # Beide Rezepte werden referenziert
        assert "Suppe" in tomate["recipes"]
        assert "Salat" in tomate["recipes"]

    def test_different_units_not_aggregated(self, client, recipe):
        """Gleicher Name aber unterschiedliche Einheit → keine Aggregation."""
        # 1x mit Original-Einheit "g"
        client.post(reverse("core:cart_add", kwargs={"pk": recipe.pk}),
                    {"servings": recipe.servings})
        # Manuell zweite Tomaten-Einheit "kg" einschmuggeln
        session = client.session
        session["shopping_cart"]["items"].append({
            "ingredient_name": "Tomate", "unit": "kg",
            "amount": "1", "recipe_name": "X", "checked": False,
        })
        session.save()

        response = client.get(reverse("core:shopping_cart"))
        names_units = [(i["name"].lower(), i["unit"].lower())
                       for i in response.context["shopping_list"]]
        assert ("tomate", "g") in names_units
        assert ("tomate", "kg") in names_units


# ---------------------------------------------------------------------------
# Löschen
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestCartDelete:
    def test_delete_item_removes_all_matching(self, client, two_recipes_same_ingredient):
        r1, r2 = two_recipes_same_ingredient
        client.post(reverse("core:cart_add", kwargs={"pk": r1.pk}),
                    {"servings": r1.servings})
        client.post(reverse("core:cart_add", kwargs={"pk": r2.pk}),
                    {"servings": r2.servings})

        client.post(reverse("core:cart_item_delete"),
                    {"name": "Tomate", "unit": "g"})

        items = client.session["shopping_cart"]["items"]
        names = [i["ingredient_name"].lower() for i in items]
        assert "tomate" not in names
        # Zwiebel (aus r1) bleibt
        assert "zwiebel" in names

    def test_clear_empties_cart(self, client, recipe):
        client.post(reverse("core:cart_add", kwargs={"pk": recipe.pk}),
                    {"servings": recipe.servings})
        assert client.session["shopping_cart"]["items"]

        client.post(reverse("core:cart_clear"))
        assert client.session["shopping_cart"]["items"] == []


# ---------------------------------------------------------------------------
# Anzeige
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestCartView:
    def test_empty_cart_renders(self, client):
        response = client.get(reverse("core:shopping_cart"))
        assert response.status_code == 200
        assert response.context["total_items"] == 0
        assert response.context["shopping_list"] == []
