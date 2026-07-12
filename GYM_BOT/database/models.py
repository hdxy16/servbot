import datetime
from typing import List, Optional
from sqlalchemy import String, Integer, Float, Boolean, DateTime, Date, ForeignKey, Text, JSON, Time
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

# ==========================================
# 1. КОРИСТУВАЧІ ТА РОЛІ
# ==========================================
class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    full_name: Mapped[str] = mapped_column(String)
    
    # Ролі зберігаються як масив строк у JSON (напр. ["ADMIN", "TRAINER", "CLIENT"])
    roles: Mapped[list] = mapped_column(JSON, default=list)
    active_role: Mapped[Optional[str]] = mapped_column(String, nullable=True) # Поточна вибрана роль
    
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

class ClientProfile(Base):
    __tablename__ = "client_profiles"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    height: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    start_weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    goal: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    level: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    start_date: Mapped[datetime.date] = mapped_column(Date, default=datetime.date.today)
    next_checkin: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class TrainerClient(Base):
    __tablename__ = "trainer_clients"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trainer_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    assigned_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class TrainerSettings(Base):
    __tablename__ = "trainer_settings"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trainer_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    
    checkin_frequency: Mapped[int] = mapped_column(Integer, default=7) # в днях
    weight_reminder_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    photo_reminder_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_client_edit_food: Mapped[bool] = mapped_column(Boolean, default=True)
    timezone: Mapped[str] = mapped_column(String, default="Europe/Kyiv")
    default_daily_vegetables: Mapped[int] = mapped_column(Integer, default=400) # грами

# ==========================================
# 2. ХАРЧУВАННЯ ТА ПРОДУКТИ
# ==========================================
class NutritionPlan(Base):
    __tablename__ = "nutrition_plans"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    
    protein_portions: Mapped[float] = mapped_column(Float, default=0.0)
    carbs_portions: Mapped[float] = mapped_column(Float, default=0.0)
    fats_portions: Mapped[float] = mapped_column(Float, default=0.0)
    fruits_portions: Mapped[float] = mapped_column(Float, default=0.0)
    anything_portions: Mapped[float] = mapped_column(Float, default=0.0)
    vegetables_g: Mapped[int] = mapped_column(Integer, default=400)
    
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String, nullable=True) # Чому змінили план

class FoodProduct(Base):
    __tablename__ = "food_products"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String, index=True) # protein, carbs, fat, fruit, vegetable, anything
    name: Mapped[str] = mapped_column(String, unique=True)
    portion_size: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String, default="г")

class Recipe(Base):
    __tablename__ = "recipes"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_file_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    calories: Mapped[int] = mapped_column(Integer, default=0)
    protein: Mapped[float] = mapped_column(Float, default=0.0)
    carbs: Mapped[float] = mapped_column(Float, default=0.0)
    fats: Mapped[float] = mapped_column(Float, default=0.0)

class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(Integer, ForeignKey("recipes.id", ondelete="CASCADE"))
    food_product_id: Mapped[int] = mapped_column(Integer, ForeignKey("food_products.id", ondelete="CASCADE"))
    amount: Mapped[float] = mapped_column(Float)

class FavoriteFood(Base):
    __tablename__ = "favorite_foods"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    food_product_id: Mapped[int] = mapped_column(Integer, ForeignKey("food_products.id", ondelete="CASCADE"))
    added_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

class RecentFoodHistory(Base):
    __tablename__ = "recent_food_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    food_product_id: Mapped[int] = mapped_column(Integer, ForeignKey("food_products.id", ondelete="CASCADE"))
    last_used_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

# ==========================================
# 3. ЩОДЕННИК ХАРЧУВАННЯ
# ==========================================
class FoodDay(Base):
    __tablename__ = "food_days"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[datetime.date] = mapped_column(Date, default=datetime.date.today)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    water_ml: Mapped[int] = mapped_column(Integer, default=0)
    steps: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class Meal(Base):
    __tablename__ = "meals"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    food_day_id: Mapped[int] = mapped_column(Integer, ForeignKey("food_days.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String) # Сніданок, Обід, Вечеря, Перекус
    time: Mapped[Optional[datetime.time]] = mapped_column(Time, nullable=True)

class MealEntry(Base):
    """Конкретний продукт, з'їдений у певний прийом їжі"""
    __tablename__ = "meal_entries"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meal_id: Mapped[int] = mapped_column(Integer, ForeignKey("meals.id", ondelete="CASCADE"))
    food_product_id: Mapped[int] = mapped_column(Integer, ForeignKey("food_products.id", ondelete="RESTRICT"))
    amount: Mapped[float] = mapped_column(Float)
    portions: Mapped[float] = mapped_column(Float)

class FoodPhoto(Base):
    __tablename__ = "food_photos"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    food_day_id: Mapped[int] = mapped_column(Integer, ForeignKey("food_days.id", ondelete="CASCADE"))
    file_id: Mapped[str] = mapped_column(String)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trainer_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

# ==========================================
# 4. ТРЕНУВАННЯ
# ==========================================
class Exercise(Base):
    __tablename__ = "exercises"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    muscle_group: Mapped[str] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class ExerciseMedia(Base):
    __tablename__ = "exercise_media"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exercise_id: Mapped[int] = mapped_column(Integer, ForeignKey("exercises.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String) # video, gif, photo
    file_id: Mapped[str] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)

class WorkoutProgram(Base):
    __tablename__ = "workout_programs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trainer_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class WorkoutDay(Base):
    __tablename__ = "workout_days"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    program_id: Mapped[int] = mapped_column(Integer, ForeignKey("workout_programs.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String) # "День 1: Верх"
    order: Mapped[int] = mapped_column(Integer, default=1)

class WorkoutExercise(Base):
    """Зв'язок вправи з днем тренування (з кастомними нотатками тренера)"""
    __tablename__ = "workout_exercises"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workout_day_id: Mapped[int] = mapped_column(Integer, ForeignKey("workout_days.id", ondelete="CASCADE"))
    exercise_id: Mapped[int] = mapped_column(Integer, ForeignKey("exercises.id", ondelete="RESTRICT"))
    
    trainer_video_file_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    trainer_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_sets: Mapped[int] = mapped_column(Integer, default=3)
    target_reps: Mapped[str] = mapped_column(String, default="8-12") # Строка, бо може бути "Max" або "8-12"

class WorkoutSession(Base):
    """Фактичне виконання тренування клієнтом"""
    __tablename__ = "workout_sessions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    workout_day_id: Mapped[int] = mapped_column(Integer, ForeignKey("workout_days.id", ondelete="RESTRICT"))
    date: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)

class WorkoutSet(Base):
    """Запис конкретного підходу клієнтом"""
    __tablename__ = "workout_sets"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("workout_sessions.id", ondelete="CASCADE"))
    workout_exercise_id: Mapped[int] = mapped_column(Integer, ForeignKey("workout_exercises.id", ondelete="RESTRICT"))
    
    weight: Mapped[float] = mapped_column(Float)
    reps: Mapped[int] = mapped_column(Integer)
    set_number: Mapped[int] = mapped_column(Integer)
    rpe: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

# ==========================================
# 5. ПРОГРЕС, ЧЕКІНИ ТА CRM
# ==========================================
class Measurement(Base):
    __tablename__ = "measurements"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[datetime.date] = mapped_column(Date, default=datetime.date.today)
    
    weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    waist: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    chest: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hips: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    arms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

class ProgressPhoto(Base):
    __tablename__ = "progress_photos"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[datetime.date] = mapped_column(Date, default=datetime.date.today)
    
    file_id: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String) # front, side, back
    weight_at_photo: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    trainer_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class CheckIn(Base):
    __tablename__ = "checkins"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[datetime.date] = mapped_column(Date, default=datetime.date.today)
    
    sleep: Mapped[int] = mapped_column(Integer) # 1-10
    energy: Mapped[int] = mapped_column(Integer) # 1-10
    stress: Mapped[int] = mapped_column(Integer) # 1-10
    hunger: Mapped[int] = mapped_column(Integer) # 1-10
    feeling: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trainer_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class FAQ(Base):
    __tablename__ = "faqs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String)
    question: Mapped[str] = mapped_column(String)
    answer: Mapped[str] = mapped_column(Text)

class Broadcast(Base):
    __tablename__ = "broadcasts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    target: Mapped[str] = mapped_column(String) # all, active, inactive
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

class Notification(Base):
    __tablename__ = "notifications"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String) # weight, photo, training, checkin
    text: Mapped[str] = mapped_column(Text)
    scheduled_at: Mapped[datetime.datetime] = mapped_column(DateTime)
    is_sent: Mapped[bool] = mapped_column(Boolean, default=False)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    target_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    action: Mapped[str] = mapped_column(String) # "Trainer changed nutrition plan"
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    date: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)