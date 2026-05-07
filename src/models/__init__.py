"""Modelos Pydantic transversales del sistema fitness-agents.

Reexporta los modelos públicos para que se puedan importar de forma plana:

    from src.models import UserProfile, Mesocycle, NutritionPlan
"""

from src.models.body_assessment import (
    BodyAssessment,
    BodyMeasurements,
    MetabolicEstimates,
    MuscleDevelopmentLevel,
    PhaseRecommendation,
    VisualAssessment,
)
from src.models.common import MacroDistribution
from src.models.exercise_db import (
    Equipment,
    Exercise,
    ExerciseDatabase,
    ForceProfile,
    MovementPattern,
    MuscleGroup,
)
from src.models.mesocycle import (
    ExerciseLog,
    Mesocycle,
    MesocyclePhase,
    Microcycle,
    ProgrammedExercise,
    SetScheme,
    SetTechnique,
    SplitType,
    TrainingDay,
    WeeklySchedule,
)
from src.models.nutrition_plan import (
    CheatMealProtocol,
    DailyDiet,
    FoodItem,
    GeneralTips,
    InterchangeRules,
    Meal,
    NutritionPlan,
)
from src.models.progress_log import (
    NutritionAdherence,
    PhotoComparison,
    ProgressAction,
    ProgressDecision,
    ProgressLog,
    SubjectiveFeedback,
    TrainingProgress,
    WeightLog,
)
from src.models.questionnaire import (
    Question,
    Questionnaire,
    QuestionnaireResponse,
    QuestionType,
)
from src.models.user_profile import (
    ActivityProfile,
    Goals,
    GymEquipment,
    NutritionProfile,
    PersonalData,
    UserProfile,
)
from src.models.validators import (
    validate_equipment_compatibility,
    validate_macros_consistency,
    validate_mesocycle_structure,
    validate_nutrition_vs_assessment,
)

__all__ = [
    "ActivityProfile",
    "BodyAssessment",
    "BodyMeasurements",
    "CheatMealProtocol",
    "DailyDiet",
    "Equipment",
    "Exercise",
    "ExerciseDatabase",
    "ExerciseLog",
    "FoodItem",
    "ForceProfile",
    "GeneralTips",
    "Goals",
    "GymEquipment",
    "InterchangeRules",
    "MacroDistribution",
    "Meal",
    "Mesocycle",
    "MesocyclePhase",
    "MetabolicEstimates",
    "Microcycle",
    "MovementPattern",
    "MuscleDevelopmentLevel",
    "MuscleGroup",
    "NutritionAdherence",
    "NutritionPlan",
    "NutritionProfile",
    "PersonalData",
    "PhaseRecommendation",
    "PhotoComparison",
    "ProgrammedExercise",
    "ProgressAction",
    "ProgressDecision",
    "ProgressLog",
    "Question",
    "QuestionType",
    "Questionnaire",
    "QuestionnaireResponse",
    "SetScheme",
    "SetTechnique",
    "SplitType",
    "SubjectiveFeedback",
    "TrainingDay",
    "TrainingProgress",
    "UserProfile",
    "VisualAssessment",
    "WeeklySchedule",
    "WeightLog",
    "validate_equipment_compatibility",
    "validate_macros_consistency",
    "validate_mesocycle_structure",
    "validate_nutrition_vs_assessment",
]
