from ai_host import generate_product_reveal


demo_product = {
    "position": 1,
    "product_name": "Midnight Crunch",
    "brand": "TryFlight Demo",
    "flavor_tags": [
        "Chocolate",
        "Caramel",
    ],
    "texture_tags": [
        "Crunchy",
        "Crispy",
    ],
    "story": (
        "A familiar chocolate-caramel opener with "
        "contrasting crunch."
    ),
    "is_wildcard": False,
}


message = generate_product_reveal(
    product=demo_product,
    participant_names=["Nick"],
    total_products=6,
)

print(message)