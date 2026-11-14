"""Reusable recipe payloads for API tests."""

CURRY = {
    "title": "Chickpea Curry",
    "cuisine": "Indian",
    "category": "Vegan",
    "ingredients": [
        {"name": "chickpeas", "measure": "1 can"},
        {"name": "curry powder", "measure": "2 tbsp"},
        {"name": "coconut milk", "measure": "400ml"},
        {"name": "garlic", "measure": "2 cloves"},
    ],
    "instructions": "Fry the garlic and curry powder, add chickpeas and coconut milk, simmer.",
}

STEW = {
    "title": "Beef Stew",
    "cuisine": "British",
    "category": "Beef",
    "ingredients": [
        {"name": "beef", "measure": "1kg"},
        {"name": "carrots", "measure": "3"},
        {"name": "garlic", "measure": "1 clove"},
    ],
    "instructions": "Brown the beef, add carrots and stock, simmer for two hours.",
}

PANCAKES = {
    "title": "Fluffy Pancakes",
    "category": "Breakfast",
    "ingredients": [
        {"name": "flour", "measure": "200g"},
        {"name": "eggs", "measure": "2"},
        {"name": "milk", "measure": "300ml"},
    ],
    "instructions": "Whisk flour, eggs and milk into a batter and fry in a hot pan.",
}
