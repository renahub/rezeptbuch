"""Unit-Tests für die Suchfunktion (RecipeSearchView).

Getestet werden:
- Treffer für Name
- Treffer für Zutat
- Treffer für Kategorie
- leeres Query
- Sonderzeichen
"""
import pytest
from decimal import Decimal
from django.urls import reverse

from core.models import Category, Ingredient, Recipe, RecipeIngredient


@pytest.fixture
def search_corpus(db):
    """Vorbereitete Rezepte mit unterschiedlichen Treffern für die Suche."""
    veggie = Category.objects.create(name="Vegetarisch")
    italien = Category.objects.create(name="Italienisch")

    tomate = Ingredient.objects.create(name="Tomate")
    basilikum = Ingredient.objects.create(name="Basilikum")

    pasta = Recipe.objects.create(
        name="Pasta al Pomodoro", servings=2, preparation_length=20,
        instructions="Tomatensoße kochen.", rating=4,
    )
    pasta.categories.add(italien, veggie)
    RecipeIngredient.objects.create(recipe=pasta, ingredient=tomate,
                                    amount=Decimal("400"), unit="g")
    RecipeIngredient.objects.create(recipe=pasta, ingredient=basilikum,
                                    amount=Decimal("10"), unit="g")

    salat = Recipe.objects.create(
        name="Caprese-Salat", servings=2, preparation_length=10,
        instructions="Anrichten.", rating=4,
    )
    salat.categories.add(italien)
    RecipeIngredient.objects.create(recipe=salat, ingredient=basilikum,
                                    amount=Decimal("5"), unit="g")

    suppe = Recipe.objects.create(
        name="Hühnersuppe", servings=4, preparation_length=60,
        instructions="Kochen.", rating=3,
    )
    return {"pasta": pasta, "salat": salat, "suppe": suppe}


@pytest.mark.django_db
class TestRecipeSearch:
    def test_search_by_name(self, client, search_corpus):
        response = client.get(reverse("core:recipe_search"), {"q": "Pasta"})
        assert response.status_code == 200
        results = list(response.context["recipes"])
        assert search_corpus["pasta"] in results
        assert search_corpus["salat"] not in results

    def test_search_by_ingredient(self, client, search_corpus):
        response = client.get(reverse("core:recipe_search"), {"q": "Basilikum"})
        results = list(response.context["recipes"])
        assert search_corpus["pasta"] in results
        assert search_corpus["salat"] in results
        assert search_corpus["suppe"] not in results

    def test_search_by_category(self, client, search_corpus):
        response = client.get(reverse("core:recipe_search"), {"q": "Italienisch"})
        results = list(response.context["recipes"])
        assert search_corpus["pasta"] in results
        assert search_corpus["salat"] in results
        assert search_corpus["suppe"] not in results

    def test_search_case_insensitive(self, client, search_corpus):
        response = client.get(reverse("core:recipe_search"), {"q": "pasta"})
        assert search_corpus["pasta"] in response.context["recipes"]

    def test_empty_query_returns_no_results(self, client, search_corpus):
        response = client.get(reverse("core:recipe_search"), {"q": ""})
        assert response.status_code == 200
        assert list(response.context["recipes"]) == []

    def test_whitespace_query_returns_no_results(self, client, search_corpus):
        response = client.get(reverse("core:recipe_search"), {"q": "   "})
        assert response.status_code == 200
        assert list(response.context["recipes"]) == []

    def test_missing_query_param(self, client, search_corpus):
        response = client.get(reverse("core:recipe_search"))
        assert response.status_code == 200
        assert list(response.context["recipes"]) == []

    def test_no_match_returns_empty(self, client, search_corpus):
        response = client.get(reverse("core:recipe_search"),
                              {"q": "Schokoladenmousse"})
        assert list(response.context["recipes"]) == []

    def test_special_characters_no_match(self, client, search_corpus):
        """Sonderzeichen dürfen keinen Server-Fehler werfen."""
        for query in ["%", "_", "'", '"', "<>", "@#&"]:
            response = client.get(reverse("core:recipe_search"), {"q": query})
            assert response.status_code == 200

    def test_german_umlaut_match(self, client, search_corpus):
        """Treffer auf Wörter mit Umlauten (z.B. 'Hühnersuppe')."""
        response = client.get(reverse("core:recipe_search"), {"q": "Hühner"})
        assert search_corpus["suppe"] in response.context["recipes"]

    def test_query_in_context(self, client, search_corpus):
        response = client.get(reverse("core:recipe_search"), {"q": "Pasta"})
        assert response.context["query"] == "Pasta"

    def test_results_are_distinct(self, client, search_corpus):
        """Pasta enthält 2 passende Zutaten + 2 passende Kategorien. Darf
        trotzdem nur einmal im Ergebnis erscheinen (distinct)."""
        response = client.get(reverse("core:recipe_search"), {"q": "a"})
        results = list(response.context["recipes"])
        # Keine Duplikate
        assert len(results) == len(set(r.pk for r in results))
