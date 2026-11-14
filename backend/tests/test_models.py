"""Model relationship tests."""

from models import MealPlan, MealPlanItem, Recipe, Tag, User


def test_recipe_relationships(db_session):
    user = User(username="alice", hashed_password="x")
    vegan, dairy_free = Tag(name="vegan"), Tag(name="dairy-free")
    recipe = Recipe(
        title="Chickpea Curry",
        ingredients=[{"name": "chickpeas", "measure": "1 can"}],
        instructions="Simmer everything together for 20 minutes.",
        source="user",
        owner=user,
        tags=[vegan, dairy_free],
    )
    plan = MealPlan(user=user, title="1-day plan", request={"days": 1}, notes="")
    plan.items.append(MealPlanItem(recipe=recipe, day=1, meal="dinner"))
    db_session.add_all([user, plan])
    db_session.commit()

    assert user.recipes[0].tag_names == ["dairy-free", "vegan"]
    assert plan.items[0].recipe.title == recipe.title

    db_session.delete(plan)
    db_session.commit()
    assert db_session.query(MealPlanItem).count() == 0
    assert db_session.query(Recipe).count() == 1
