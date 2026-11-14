"""SQLAlchemy ORM models: users, recipes, tags, meal plans."""

from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def _now() -> datetime:
    """Current UTC time (used as a column default)."""
    return datetime.now(UTC)


recipe_tags = Table(
    "recipe_tags",
    Base.metadata,
    Column("recipe_id", ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    """An account that can own recipes and meal plans."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    recipes: Mapped[list["Recipe"]] = relationship(back_populates="owner")
    meal_plans: Mapped[list["MealPlan"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Tag(Base):
    """A dietary tag such as 'vegan' or 'gluten-free'."""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True)

    recipes: Mapped[list["Recipe"]] = relationship(secondary=recipe_tags, back_populates="tags")


class Recipe(Base):
    """A recipe with structured ingredients; seeded from TheMealDB or created by a user."""

    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str | None] = mapped_column(String(50))
    cuisine: Mapped[str | None] = mapped_column(String(50))
    ingredients: Mapped[list[dict]] = mapped_column(JSON)
    instructions: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="user")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    owner: Mapped[User] = relationship(back_populates="recipes")
    tags: Mapped[list[Tag]] = relationship(secondary=recipe_tags, back_populates="recipes")

    @property
    def tag_names(self) -> list[str]:
        """Sorted list of this recipe's tag names."""
        return sorted(t.name for t in self.tags)

    @property
    def owner_username(self) -> str:
        """Username of the recipe's owner."""
        return self.owner.username


class MealPlan(Base):
    """A generated multi-day meal plan belonging to one user."""

    __tablename__ = "meal_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    request: Mapped[dict] = mapped_column(JSON)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped[User] = relationship(back_populates="meal_plans")
    items: Mapped[list["MealPlanItem"]] = relationship(
        back_populates="meal_plan",
        cascade="all, delete-orphan",
        order_by="(MealPlanItem.day, MealPlanItem.meal)",
    )


class MealPlanItem(Base):
    """One slot (day + meal) in a meal plan, pointing at a recipe."""

    __tablename__ = "meal_plan_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    meal_plan_id: Mapped[int] = mapped_column(ForeignKey("meal_plans.id", ondelete="CASCADE"))
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"))
    day: Mapped[int] = mapped_column(Integer)
    meal: Mapped[str] = mapped_column(String(10))

    meal_plan: Mapped[MealPlan] = relationship(back_populates="items")
    recipe: Mapped[Recipe] = relationship()
