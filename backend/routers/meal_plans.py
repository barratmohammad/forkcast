"""Meal plan generation, management and shopping lists."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import MealPlan, MealPlanItem, User
from ollama_client import get_llm
from rag_pipeline import RecipeIndex, get_index, plan_meals
from routers.recipes import to_out
from schemas import (
    MealPlanItemOut,
    MealPlanOut,
    MealPlanRequest,
    MealPlanSummary,
    ShoppingList,
)
from shopping import build_shopping_list

router = APIRouter(prefix="/meal-plans", tags=["meal plans"])

MEAL_ORDER = {"lunch": 0, "dinner": 1}


def to_plan_out(plan: MealPlan) -> MealPlanOut:
    """Convert an ORM meal plan to its response schema, ordered by day then meal."""
    items = sorted(plan.items, key=lambda i: (i.day, MEAL_ORDER.get(i.meal, 9)))
    return MealPlanOut(
        id=plan.id,
        title=plan.title,
        request=plan.request,
        notes=plan.notes,
        created_at=plan.created_at,
        items=[MealPlanItemOut(day=i.day, meal=i.meal, recipe=to_out(i.recipe)) for i in items],
    )


def get_own_plan(db: Session, plan_id: int, user: User) -> MealPlan:
    """Load one of the user's plans; 404 for missing or someone else's."""
    plan = db.get(MealPlan, plan_id)
    if plan is None or plan.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Meal plan not found")
    return plan


@router.post("", response_model=MealPlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(
    body: MealPlanRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    index: RecipeIndex = Depends(get_index),
    llm=Depends(get_llm),
) -> MealPlanOut:
    """Generate and save a meal plan chosen from recipes in the collection."""
    try:
        picks, notes = plan_meals(db, index, llm, body)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    title = f"{body.days}-day plan" + (f" ({', '.join(body.tags)})" if body.tags else "")
    plan = MealPlan(user=user, title=title, request=body.model_dump(), notes=notes)
    plan.items = [MealPlanItem(day=d, meal=m, recipe_id=rid) for d, m, rid in picks]
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return to_plan_out(plan)


@router.get("", response_model=list[MealPlanSummary])
def list_plans(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[MealPlanSummary]:
    """The current user's meal plans, newest first."""
    plans = db.scalars(
        select(MealPlan)
        .where(MealPlan.user_id == user.id)
        .order_by(MealPlan.created_at.desc(), MealPlan.id.desc())
    )
    return [
        MealPlanSummary(id=p.id, title=p.title, created_at=p.created_at, item_count=len(p.items))
        for p in plans
    ]


@router.get("/{plan_id}", response_model=MealPlanOut)
def get_plan(
    plan_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> MealPlanOut:
    """Fetch one of your meal plans."""
    return to_plan_out(get_own_plan(db, plan_id, user))


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(
    plan_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Response:
    """Delete one of your meal plans."""
    db.delete(get_own_plan(db, plan_id, user))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{plan_id}/shopping-list", response_model=ShoppingList)
def shopping_list(
    plan_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ShoppingList:
    """Combine the ingredients of every recipe in a plan into one shopping list."""
    plan = get_own_plan(db, plan_id, user)
    result = build_shopping_list(
        [(i.recipe.title, i.recipe.ingredients) for i in plan.items],
        plan.request.get("on_hand", []),
    )
    return ShoppingList(plan_id=plan.id, **result)
