"""SQLAlchemy 2.0 ORM 模型 —— 資料庫結構的唯一來源(取代原本的 sql/schema.sql)。

型別用 `Mapped[...]` 標註,欄位細節(server_default / FK / index / unique)
用 `mapped_column(...)` / `__table_args__` 補齊。`Base.metadata.create_all()`
只會建立不存在的資料表,不會更動已存在資料表的欄位,對既有部署安全。
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, UniqueConstraint, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    invite_code: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Profile(Base):
    """每位會員的每日目標設定(user_id 即主鍵,一人一筆)。"""
    __tablename__ = "profiles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    mode: Mapped[str] = mapped_column(server_default=text("'auto'"))
    sex: Mapped[str | None]
    age: Mapped[int | None]
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    body_fat_pct: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    measured_bmr: Mapped[int | None]
    activity_level: Mapped[str | None]
    goal: Mapped[str | None]
    calorie_adjust: Mapped[int | None]
    tdee: Mapped[int | None]
    calories_min: Mapped[int]
    calories_max: Mapped[int]
    protein_min: Mapped[int]
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class Entry(Base):
    """一筆飲食記錄。"""
    __tablename__ = "entries"
    __table_args__ = (Index("idx_entries_user_eaten", "user_id", "eaten_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    eaten_at: Mapped[datetime] = mapped_column(server_default=func.now())
    name: Mapped[str]
    calories: Mapped[int]
    protein_g: Mapped[Decimal] = mapped_column(Numeric(5, 1))
    source: Mapped[str]
    note: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Food(Base):
    """常用食物,每位會員各自一份。"""
    __tablename__ = "foods"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str]
    calories: Mapped[int]
    protein_g: Mapped[Decimal] = mapped_column(Numeric(5, 1))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Recipe(Base):
    """自己記的食譜,每位會員各自一份。"""
    __tablename__ = "recipes"
    __table_args__ = (Index("idx_recipes_user", "user_id", "updated_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str]
    servings: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    calories: Mapped[int | None]
    protein_g: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    ingredients: Mapped[str | None]
    steps: Mapped[str | None]
    video_url: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class Friendship(Base):
    """好友關係(雙向;以 requester/addressee 一筆表示)。"""
    __tablename__ = "friendships"
    __table_args__ = (
        UniqueConstraint("requester_id", "addressee_id"),
        Index("idx_friend_addr", "addressee_id", "status"),
        Index("idx_friend_req", "requester_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    addressee_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(server_default=text("'pending'"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class SharePrefs(Base):
    """分享權限(每位使用者一組,套用到所有好友)。"""
    __tablename__ = "share_prefs"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    share_mascot: Mapped[bool] = mapped_column(server_default=text("true"))
    share_diet: Mapped[bool] = mapped_column(server_default=text("false"))
    share_recipes: Mapped[bool] = mapped_column(server_default=text("false"))


class Exercise(Base):
    """運動記錄(月曆打卡)。"""
    __tablename__ = "exercises"
    __table_args__ = (Index("idx_exercises_user_logged", "user_id", "logged_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    logged_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ex_type: Mapped[str]
    duration_min: Mapped[int | None]
    distance_km: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    calories: Mapped[int | None]
    note: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    movements: Mapped[list["ExerciseMovement"]] = relationship(
        back_populates="exercise",
        cascade="all, delete-orphan",
        order_by="ExerciseMovement.sort_order",
    )


class ExerciseMovement(Base):
    """重訓細節:一筆運動記錄底下的動作。"""
    __tablename__ = "exercise_movements"
    __table_args__ = (Index("idx_ex_movements_exercise", "exercise_id", "sort_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"))
    name: Mapped[str]
    sort_order: Mapped[int] = mapped_column(server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    exercise: Mapped["Exercise"] = relationship(back_populates="movements")
    sets: Mapped[list["ExerciseSet"]] = relationship(
        back_populates="movement",
        cascade="all, delete-orphan",
        order_by="ExerciseSet.set_order",
    )


class ExerciseSet(Base):
    """重訓動作底下的組數。"""
    __tablename__ = "exercise_sets"
    __table_args__ = (Index("idx_ex_sets_movement", "movement_id", "set_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    movement_id: Mapped[int] = mapped_column(
        ForeignKey("exercise_movements.id", ondelete="CASCADE")
    )
    set_order: Mapped[int] = mapped_column(server_default=text("0"))
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    reps: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    movement: Mapped["ExerciseMovement"] = relationship(back_populates="sets")


class WorkoutPlan(Base):
    """訓練菜單:可重複套用的重訓範本。"""
    __tablename__ = "workout_plans"
    __table_args__ = (Index("idx_workout_plans_user", "user_id", "updated_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str]
    source_url: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    movements: Mapped[list["WorkoutPlanMovement"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="WorkoutPlanMovement.sort_order",
    )


class WorkoutPlanMovement(Base):
    """訓練菜單底下的動作 + 目標組數/次數。"""
    __tablename__ = "workout_plan_movements"
    __table_args__ = (Index("idx_plan_movements_plan", "plan_id", "sort_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("workout_plans.id", ondelete="CASCADE"))
    name: Mapped[str]
    target_sets: Mapped[int] = mapped_column(server_default=text("3"))
    target_reps: Mapped[int] = mapped_column(server_default=text("10"))
    sort_order: Mapped[int] = mapped_column(server_default=text("0"))

    plan: Mapped["WorkoutPlan"] = relationship(back_populates="movements")
