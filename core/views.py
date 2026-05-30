"""Views for the core application."""

import re
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from core.models import Recipe, Category, Ingredient, RecipeImage
from .forms import (
    CategoryFormSet,
    RecipeForm,
    RecipeImageFormSet,
    RecipeIngredientFormSet,
)
from .services import extract_recipe_from_image


def _get_cart(request):
    if "shopping_cart" not in request.session:
        request.session["shopping_cart"] = {"items": []}
    return request.session.get("shopping_cart", {"items": []})

def _save_cart(request, cart):
    """Speichert den Warenkorb in der Session."""
    request.session["shopping_cart"] = cart
    request.session.modified = True

def _ensure_single_title(recipe):
    titled = list(recipe.images.filter(is_title=True))
    if len(titled) > 1:
        for img in titled[1:]:
            img.is_title = False
            img.save()
    elif len(titled) == 0 and recipe.images.exists():
        first = recipe.images.first()
        first.is_title = True
        first.save()


class CategoryListView(ListView):
    model = Category
    template_name = "core/category_list.html"
    context_object_name = "categories"


class CategoryView(ListView):
    model = Recipe
    template_name = "core/recipe_category_list.html"
    context_object_name = "recipes"

    def get_queryset(self):
        category_id = self.kwargs.get("category_id")
        return Recipe.objects.filter(categories__id=category_id).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category_id = self.kwargs.get("category_id")
        context["category"] = get_object_or_404(Category, id=category_id)
        return context


class RecipeView(View):
    def get(self, request, pk):
        recipe = get_object_or_404(
            Recipe.objects.prefetch_related(
                'recipe_ingredients__ingredient',
                'categories',
                'images',
            ),
            pk=pk,
        )
        context = {
            'recipe': recipe,
            'images': recipe.images.all(),
        }
        return render(request, 'core/recipe_detail.html', context)


class RecipeCreateView(CreateView):
    model = Recipe
    form_class = RecipeForm
    object = None
    template_name = "core/recipe_create.html"

    def get_success_url(self):
        return reverse_lazy('core:recipe', kwargs={'pk': self.object.pk})

    def get(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        formset = RecipeIngredientFormSet(prefix="recipe_ingredients")
        category_formset = CategoryFormSet(prefix="categories")
        image_formset = RecipeImageFormSet(prefix="images")
        return render(request, self.template_name, {
            'form': form,
            'formset': formset,
            'category_formset': category_formset,
            'image_formset': image_formset,
        })

    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        formset = RecipeIngredientFormSet(request.POST, prefix="recipe_ingredients")
        category_formset = CategoryFormSet(request.POST, prefix="categories")
        image_formset = RecipeImageFormSet(request.POST, request.FILES, prefix="images")

        all_valid = (
            form.is_valid()
            and formset.is_valid()
            and category_formset.is_valid()
            and image_formset.is_valid()
        )

        if all_valid:
            recipe = form.save()
            self.object = recipe
            formset.instance = recipe

            # Zutaten speichern
            for subform in formset:
                if not subform.cleaned_data:
                    continue
                new_ing_name = subform.cleaned_data.get('new_ingredient')
                existing_ing = subform.cleaned_data.get('ingredient')
                if new_ing_name:
                    ing, _ = Ingredient.objects.get_or_create(name=new_ing_name)
                    subform.instance.ingredient = ing
                elif existing_ing:
                    subform.instance.ingredient = existing_ing
            formset.save()

            # Kategorien speichern
            for catform in category_formset:
                if catform.cleaned_data.get('DELETE'):
                    continue
                new_cat_name = catform.cleaned_data.get('new_category', '').strip()
                existing_cat = catform.cleaned_data.get('category')
                if new_cat_name:
                    existing_cat, _ = Category.objects.get_or_create(name=new_cat_name)
                if existing_cat:
                    recipe.categories.add(existing_cat)

            # Bilder speichern
            image_formset.instance = recipe
            image_formset.save()

            # Gescanntes Bild als RecipeImage übernehmen, falls vorhanden
            scanned_path = request.POST.get('scanned_image_path', '').strip()
            if scanned_path and not recipe.images.exists():
                RecipeImage.objects.create(recipe=recipe, image=scanned_path, is_title=True)

            _ensure_single_title(recipe)
            return redirect('core:recipe', pk=recipe.pk)

        return render(request, self.template_name, {
            'form': form,
            'formset': formset,
            'category_formset': category_formset,
            'image_formset': image_formset,
        })


class RecipeUpdateView(UpdateView):
    model = Recipe
    form_class = RecipeForm
    template_name = "core/recipe_edit.html"

    def get_success_url(self):
        return reverse_lazy('core:recipe', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        recipe = self.object
        if self.request.POST:
            context['formset'] = RecipeIngredientFormSet(
                self.request.POST,
                instance=recipe,
                prefix="recipe_ingredients"
            )
            context['category_formset'] = CategoryFormSet(
                self.request.POST,
                prefix="categories"
            )
            context['image_formset'] = RecipeImageFormSet(
                self.request.POST, self.request.FILES,
                instance=recipe,
                prefix="images"
            )
        else:
            context['formset'] = RecipeIngredientFormSet(
                instance=recipe,
                prefix="recipe_ingredients"
            )
            existing_categories = [{'category': cat} for cat in recipe.categories.all()]
            context['category_formset'] = CategoryFormSet(
                prefix="categories",
                initial=existing_categories
            )
            context['image_formset'] = RecipeImageFormSet(
                instance=recipe,
                prefix="images"
            )
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        category_formset = context['category_formset']
        image_formset = context['image_formset']

        if not (formset.is_valid() and category_formset.is_valid() and image_formset.is_valid()):
            return self.render_to_response(context)

        recipe = form.save()
        formset.instance = recipe

        # Zutaten speichern
        for subform in formset:
            if not subform.cleaned_data:
                continue
            new_ing_name = subform.cleaned_data.get('new_ingredient')
            existing_ing = subform.cleaned_data.get('ingredient')
            if new_ing_name:
                ing, _ = Ingredient.objects.get_or_create(name=new_ing_name)
                subform.instance.ingredient = ing
            elif existing_ing:
                subform.instance.ingredient = existing_ing
        formset.save()

        # Kategorien speichern (erst alte entfernen, dann neue setzen)
        recipe.categories.clear()
        for catform in category_formset:
            if catform.cleaned_data.get('DELETE'):
                continue
            new_cat_name = catform.cleaned_data.get('new_category', '').strip()
            existing_cat = catform.cleaned_data.get('category')
            if new_cat_name:
                existing_cat, _ = Category.objects.get_or_create(name=new_cat_name)
            if existing_cat:
                recipe.categories.add(existing_cat)

        # Bilder speichern
        image_formset.save()
        _ensure_single_title(recipe)

        return redirect(self.get_success_url())


class RecipeImageUploadView(View):
    def post(self, request, pk):
        recipe = get_object_or_404(Recipe, pk=pk)
        image = request.FILES.get('image')
        if image:
            is_first = not recipe.images.exists()
            RecipeImage.objects.create(recipe=recipe, image=image, is_title=is_first)
            _ensure_single_title(recipe)
        return redirect('core:recipe', pk=pk)


class CategoryRenameView(View):
    def post(self, request, pk):
        category = get_object_or_404(Category, pk=pk)
        new_name = request.POST.get('name', '').strip()
        if new_name:
            category.name = new_name
        new_image = request.FILES.get('image')
        if new_image:
            category.image = new_image
        if new_name or new_image:
            category.save()
            messages.success(request, f'Kategorie „{category.name}" wurde aktualisiert.')
        return redirect('core:category_list')


class CategoryDeleteView(DeleteView):
    model = Category
    template_name = "core/category_confirm_delete.html"
    success_url = reverse_lazy('core:category_list')

    def form_valid(self, form):
        messages.success(self.request, f'Kategorie „{self.object.name}" wurde gelöscht.')
        return super().form_valid(form)


class RecipeDeleteView(DeleteView):
    model = Recipe
    template_name = "core/recipe_confirm_delete.html"
    success_url = reverse_lazy('core:recipe_list')

    def form_valid(self, form):
        messages.success(self.request, f'Rezept „{self.object.name}" wurde gelöscht.')
        return super().form_valid(form)


class RecipeListView(ListView):
    model = Recipe
    template_name = "core/recipe_list.html"
    context_object_name = "recipes"

    def get_queryset(self):
        return Recipe.objects.prefetch_related('images')

class RecipeSearchView(ListView):
    model = Recipe
    template_name = "core/recipe_search.html"
    context_object_name = "recipes"

    def get_queryset(self):
        query = self.request.GET.get("q", "").strip()
        category_ids = self.request.GET.getlist("category")
        max_time = self.request.GET.get("max_time", "").strip()

        has_filters = bool(query or category_ids or max_time)
        if not has_filters:
            return Recipe.objects.none()

        qs = Recipe.objects.all()

        for term in [t for t in re.split(r'[,\s]+', query) if t]:
            qs = qs.filter(
                Q(name__icontains=term)
                | Q(instructions__icontains=term)
                | Q(categories__name__icontains=term)
                | Q(
                    recipe_ingredients__ingredient__name__icontains=term
                )
            )

        if category_ids:
            for cid in category_ids:
                qs = qs.filter(categories__id=cid)

        if max_time:
            try:
                qs = qs.filter(preparation_length__lte=int(max_time))
            except ValueError:
                pass

        return qs.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "").strip()
        context["selected_categories"] = [
            int(c)
            for c in self.request.GET.getlist("category")
            if c.isdigit()
        ]
        context["max_time"] = self.request.GET.get("max_time", "").strip()
        context["all_categories"] = Category.objects.order_by("name")
        context["has_filters"] = bool(
            context["query"]
            or context["selected_categories"]
            or context["max_time"]
        )
        return context

class RecipeScanView(View):
    def post(self, request):
        image_files = request.FILES.getlist('image')
        if not image_files:
            return JsonResponse({'error': 'Kein Bild hochgeladen.'}, status=400)
        try:
            api_key = settings.GEMINI_API_KEY
            data = extract_recipe_from_image(image_files, api_key)
            return JsonResponse({'success': True, 'data': data})
        except Exception as error: # pylint: disable=broad-exception-caught
            return JsonResponse({'error': str(error)}, status=500)

class CartAddView(View):
    """Wird von der Rezeptdetailseite aufgerufen."""
    def post(self, request, pk):
        recipe = Recipe.objects.prefetch_related(
            "recipe_ingredients__ingredient"
        ).get(pk=pk)

        try:
            desired = Decimal(request.POST.get("servings", recipe.servings))
            if desired <= 0:
                raise ValueError
        except (ValueError, InvalidOperation):
            messages.error(request, "Ungültige Portionszahl.")
            return 	redirect('core:recipe', pk=pk)

        factor = desired / recipe.servings
        cart = _get_cart(request)

        for ri in recipe.recipe_ingredients.all():
            cart["items"].append({
                "ingredient_name": ri.ingredient.name,
                "unit": ri.unit,
                "amount": str(ri.amount * factor),
                "recipe_name": recipe.name,
                "checked": False,
            })

        _save_cart(request, cart)
        messages.success(request, f'„{recipe.name}" wurde zur Einkaufsliste hinzugefügt.')
        return redirect("core:recipe", pk=pk)


class CartView(View):
    template_name = "core/shopping_cart.html"

    def get(self, request):
        cart = _get_cart(request)
        items = cart.get("items", [])

        # Aggregieren: gleicher Name + gleiche Einheit werden summiert
        aggregated = {}
        for i, item in enumerate(items):
            key = (item["ingredient_name"].lower(), item["unit"].lower())
            if key not in aggregated:
                aggregated[key] = {
                    "name": item["ingredient_name"],
                    "unit": item["unit"],
                    "amount": Decimal(item["amount"]),
                    "checked": item["checked"],
                    # Indices aller Einzel-Items die zu diesem Eintrag gehören
                    "indices": [i],
                    "recipes": [item["recipe_name"]],
                }
            else:
                aggregated[key]["amount"] += Decimal(item["amount"])
                aggregated[key]["indices"].append(i)
                aggregated[key]["recipes"].append(item["recipe_name"])
                # Nur abgehakt wenn ALLE zugehörigen Items abgehakt
                aggregated[key]["checked"] = (
                    aggregated[key]["checked"] and item["checked"]
                )

        shopping_list = sorted(aggregated.values(), key=lambda x: x["name"].lower())

        return render(request, self.template_name, {
            'shopping_list': shopping_list,
            'total_items': len(items),
        })


class CartItemDeleteView(View):
    """Löscht eine aggregierte Zutat (alle zugehörigen Einzel-Items)."""
    def post(self, request):
        name = request.POST.get("name", "").lower()
        unit = request.POST.get("unit", "").lower()
        cart = _get_cart(request)

        cart["items"] = [
            item for item in cart["items"]
            if not (
                item["ingredient_name"].lower() == name and
                item["unit"].lower() == unit
            )
        ]
        _save_cart(request, cart)
        return redirect("core:shopping_cart")

class CartClearView(View):
    """Leert den gesamten Warenkorb."""
    def post(self, request):
        _save_cart(request, {"items": []})
        return redirect("core:shopping_cart")
