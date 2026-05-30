"""Form definitions for the core application."""

from django import forms
from django.forms import formset_factory, inlineformset_factory
from .models import RecipeIngredient, Ingredient, Recipe, Category, RecipeImage


class RecipeForm(forms.ModelForm):
    class Meta:
        model = Recipe
        fields = ['name', 'servings', 'preparation_length', 'instructions', 'rating']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'servings': forms.NumberInput(attrs={'class': 'form-control'}),
            'preparation_length': forms.NumberInput(attrs={'class': 'form-control'}),
            'instructions': forms.Textarea(attrs={'class': 'form-control'}),
            'rating': forms.Select(attrs={'class': 'form-select'}),
        }


class RecipeIngredientForm(forms.ModelForm):
    """Einzelnes Formular für eine Rezeptzutat."""

    ingredient = forms.ModelChoiceField(
        queryset=Ingredient.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=False,
    )

    new_ingredient = forms.CharField(
        max_length=128,
        widget=forms.TextInput(
            attrs={'placeholder': 'Neue Zutat', 'class': 'form-control'}
        ),
        required=False,
    )

    amount = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )
    unit = forms.CharField(
        max_length=16,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'z.B. g, ml, TL'}),
    )

    class Meta:
        model = RecipeIngredient
        fields = ['ingredient', 'new_ingredient', 'amount', 'unit']

    def clean(self):
        cleaned_data = super().clean()
        ingredient = cleaned_data.get('ingredient')
        new_ingredient = (cleaned_data.get('new_ingredient') or '').strip()
        amount = cleaned_data.get('amount')
        unit = (cleaned_data.get('unit') or '').strip()

        # Komplett leere Zeile → als leer markieren, wird vom Formset ignoriert
        if not ingredient and not new_ingredient and not amount and not unit:
            return cleaned_data

        # Teilweise befüllte Zeile → Pflichtfelder prüfen
        if (ingredient or new_ingredient) and amount is None:
            raise forms.ValidationError("Bitte eine Menge angeben.")
        if (ingredient or new_ingredient) and not unit:
            raise forms.ValidationError("Bitte eine Einheit angeben.")

        return cleaned_data


# Formset für mehrere Zutaten
RecipeIngredientFormSet = inlineformset_factory(
    Recipe,
    RecipeIngredient,
    form=RecipeIngredientForm,
    extra=0,
    can_delete=True
)


class RecipeImageForm(forms.ModelForm):
    """Formular zum Hochladen von Rezeptbildern."""

    class Meta:
        model = RecipeImage
        fields = ['image', 'is_title']
        widgets = {
            'image': forms.ClearableFileInput(
                attrs={'class': 'form-control form-control-sm'}
            ),
            'is_title': forms.CheckboxInput(
                attrs={'class': 'form-check-input'}
            ),
        }


RecipeImageFormSet = inlineformset_factory(
    Recipe,
    RecipeImage,
    form=RecipeImageForm,
    extra=0,
    can_delete=True,
)


class RecipeCategoryForm(forms.Form):
    """Einzelnes Formular zur Auswahl oder Erstellung einer Kategorie."""

    category = forms.ModelChoiceField(
        queryset=Category.objects.all().order_by('name'),
        required=False,
        empty_label="-- Bestehende Kategorie --",
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    new_category = forms.CharField(
        max_length=128,
        required=False,
        widget=forms.TextInput(
            attrs={'placeholder': 'Neue Kategorie', 'class': 'form-control'}
        ),
    )

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get("category")
        new_category = cleaned_data.get("new_category", "").strip()
        if category and new_category:
            raise forms.ValidationError(
                'Bitte entweder eine bestehende Kategorie wählen ODER eine neue '
                'eingeben, nicht beides.'
            )
        return cleaned_data


# Formset für mehrere Kategorien
CategoryFormSet = formset_factory(
    RecipeCategoryForm,
    extra=1,
    can_delete=True,
)
