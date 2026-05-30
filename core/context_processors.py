"""Template context processors for the core application."""

def cart_count(request):
    """Return the current shopping cart item count for templates."""
    cart = request.session.get("shopping_cart", {"items": []})
    return {"cart_count": len(cart["items"])}
