"""Django admin configuration for the core application."""

from django.contrib import admin
from .models import Recipe, RecipeIngredient, Category, Ingredient


class RecipeIngredientInline(admin.TabularInline):
    """Inline admin interface for recipe ingredients."""
    model = RecipeIngredient
    extra = 1


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    """Admin interface for recipes."""
    inlines = [RecipeIngredientInline]


admin.site.register(Category)
admin.site.register(Ingredient)
