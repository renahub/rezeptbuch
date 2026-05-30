"""URL-Konfiguration für die core-Anwendung."""

from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.CategoryListView.as_view(), name='category_list'),
    path('list/', views.RecipeListView.as_view(), name='recipe_list'),
    path(
        'category/<int:category_id>/',
        views.CategoryView.as_view(),
        name='recipe_category',
    ),
    path(
        'category/<int:pk>/umbenennen/',
        views.CategoryRenameView.as_view(),
        name='category_rename',
    ),
    path(
        'category/<int:pk>/loeschen/',
        views.CategoryDeleteView.as_view(),
        name='category_delete',
    ),
    path('<int:pk>/', views.RecipeView.as_view(), name='recipe'),
    path('create/', views.RecipeCreateView.as_view(), name='recipe_create'),
    path('<int:pk>/bearbeiten/', views.RecipeUpdateView.as_view(), name='recipe_edit'),
    path(
        '<int:pk>/bild-hochladen/',
        views.RecipeImageUploadView.as_view(),
        name='recipe_image_upload',
    ),
    path('<int:pk>/loeschen/', views.RecipeDeleteView.as_view(), name='recipe_delete'),
    path('suche/', views.RecipeSearchView.as_view(), name='recipe_search'),
    path('scan/', views.RecipeScanView.as_view(), name='recipe_scan'),
    path('einkaufsliste/', views.CartView.as_view(), name='shopping_cart'),
    path(
        'einkaufsliste/hinzufuegen/<int:pk>/',
        views.CartAddView.as_view(),
        name='cart_add',
    ),
    path('einkaufsliste/loeschen/', views.CartItemDeleteView.as_view(), name='cart_item_delete'),
    path('einkaufsliste/leeren/', views.CartClearView.as_view(), name='cart_clear'),
]
