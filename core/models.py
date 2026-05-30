"""Datenmodelle für die core-Anwendung."""

from django.db import models

RATING_CHOICES = [
    (1, 'Schlecht'),
    (2, 'Mittel'),
    (3, 'Sehr gut'),
]


class Category(models.Model):
    """Kategorie eines Rezepts."""

    name = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
    )
    image = models.ImageField(
        upload_to='category_images/',
        blank=True,
        null=True,
        verbose_name='Kategoriebild',
    )

    def __str__(self):
        return self.name


class Ingredient(models.Model):
    """Zutat eines Rezepts."""

    name = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
        verbose_name='Zutat',
    )

    def __str__(self):
        return self.name


class Recipe(models.Model):
    """Rezept mit Metadaten und Beziehungen zu Zutaten und Kategorien."""

    name = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
        verbose_name='Rezeptname',
    )
    categories = models.ManyToManyField(
        Category,
        related_name='recipes',
        verbose_name='Kategorien',
        blank=True,
    )
    ingredients = models.ManyToManyField(
        Ingredient,
        through='RecipeIngredient',
        related_name='recipes',
        verbose_name='Zutaten',
    )
    servings = models.PositiveSmallIntegerField(
        default=2,
        help_text='Anzahl Portionen',
        verbose_name='Portionen',
    )
    preparation_length = models.PositiveSmallIntegerField(
        help_text='Zeit in Minuten',
        verbose_name='Zubereitungszeit (Minuten)',
    )
    instructions = models.TextField(
        verbose_name='Zubereitung',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    rating = models.IntegerField(
        choices=RATING_CHOICES,
        default=2,
        help_text='Bewertung von 1 (schlecht) bis 3 (sehr gut)',
    )

    def __str__(self):
        return self.name


class RecipeImage(models.Model):
    """Bild eines Rezepts."""

    recipe = models.ForeignKey(
        'Recipe',
        on_delete=models.CASCADE,
        related_name='images',
        verbose_name='Rezept',
    )
    image = models.ImageField(
        upload_to='recipe_images/',
        verbose_name='Bild',
    )
    is_title = models.BooleanField(
        default=False,
        verbose_name='Titelbild',
    )
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['-is_title', 'order', 'pk']

    def __str__(self):
        return f'Bild für {self.recipe.name}'


class RecipeIngredient(models.Model):
    """Zwischenmodell für Rezept und Zutat mit Menge und Einheit."""

    recipe = models.ForeignKey(
        'Recipe',
        on_delete=models.CASCADE,
        related_name='recipe_ingredients',
        verbose_name='Rezept',
    )
    ingredient = models.ForeignKey(
        Ingredient,
        on_delete=models.CASCADE,
        related_name='recipe_ingredients',
        verbose_name='Zutat',
    )
    amount = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text='Menge',
        verbose_name='Menge',
    )
    unit = models.CharField(
        max_length=16,
        help_text='Einheit, z.B. g, ml, TL',
        verbose_name='Einheit',
    )

    def __str__(self):
        return f'{self.amount} {self.unit} {self.ingredient.name} für {self.recipe.name}'
