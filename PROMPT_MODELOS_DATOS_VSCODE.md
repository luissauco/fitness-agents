# PROMPT PARA CREAR LOS MODELOS DE DATOS EN VSCODE

> Copia y pega este prompt en Claude Code dentro de tu proyecto fitness-agents.
> Claude Code ya tiene el CLAUDE.md con las reglas del proyecto + Karpathy.

---

## PROMPT:

```
Vamos a construir el módulo de modelos de datos (`src/models/`) para el sistema multi-agente de fitness. Estos modelos Pydantic son la columna vertebral del proyecto: los usan todos los agentes, los generadores de archivos y la persistencia.

## CONTEXTO

Ya tenemos construido:
- Estructura del proyecto completa
- Módulo RAG en src/knowledge/ (indexer, retriever, chunker, embeddings, sources)
- Configuración en src/config/settings.py

Ahora necesitamos los modelos de datos que representan toda la información que fluye por el sistema.

## REFERENCIAS DE FORMATO

Tengo tres archivos de referencia que definen los formatos reales que el sistema debe manejar. No los tienes disponibles directamente, así que te describo su estructura:

### Cuestionario inicial (PDF de referencia)
Un formulario con estos campos:
- Nombre, Apellidos, Edad, Sexo (M/F)
- Altura (cm), Peso en ayunas (kg)
- Actividad física durante el día (texto libre)
- Días de descanso total/parcial por semana
- NEAT estimado (¿actividad elevada fuera del entreno?)
- Días de entrenamiento semanales dispuestos
- Alimentos que no gustan
- Hora de levantarse y acostarse
- Hora de actividad física habitual
- Comidas en un día normal (número, alimentos, bebidas)
- Disposición a comer en ventana horaria reducida
- Disposición a saltarse el desayuno
- Cantidad de sal habitual
- Bebidas habituales y litros de agua diarios
- Grupos de alimentos cómodos/incómodos (cocinar, llevar fuera)
- Disposición a suplementos
- Alergias o intolerancias

Campos adicionales que añado yo:
- Objetivos detallados (texto libre)
- Fotos actuales: frente, espalda, perfil izquierdo, perfil derecho (paths a imágenes)
- Material disponible en el gimnasio (texto o paths a fotos)
- Kcals actuales y distribución de macros
- Tipo de entrenamiento que ha venido siguiendo
- Lesiones o molestias recientes

### Mesociclo Excel (formato de referencia)
Estructura del Excel con mesociclo de entrenamiento:
- Título con nombre del cliente y fecha
- Agrupado por días de entrenamiento (Día 1, Día 2, etc.)
- Para cada día, lista de ejercicios con:
  - Nombre del ejercicio (con indicaciones técnicas detalladas, ej: "Press inclinado mancuernas (45º, agarre neutro, ROM completo)")
  - Esquema de series: "2x?(fallo)", "top set: 1x?(RIR 1) / back-off: 2x?(RIR 1)", etc.
  - Columnas por cada microciclo (Micro 1, Micro 2, ..., Descarga) con espacio para KGs × Reps
  - Descanso entre series
- Días de descanso marcados (ej: "Día 3: Rest")
- Esquema semanal de referencia al final: qué días son pesas, cuáles descanso, pasos mínimos por tipo de día
- Los microciclos pueden ser de 7 o 10 días

### Plan nutricional (PDF de referencia)
Estructura del plan:
- Cabecera: nombre, objetivos (ej: "Minicut"), duración, fecha inicio
- Dos plantillas de dieta diferenciadas:
  - DÍAS DE ENTRENO: kcal totales, HC/P/G en gramos
  - DÍAS DE DESCANSO: kcal totales, HC/P/G en gramos (menos kcal y HC)
- Cada plantilla tiene comidas con:
  - Nombre de la comida (Desayuno, Comida, Merienda/Almuerzo, Intraentreno, Cena)
  - Alimentos con gramos exactos
  - Opciones intercambiables separadas por "/" (ej: "arroz/pasta/quinoa")
  - Notas de preparación (al horno, plancha, vapor, etc.)
- Esquema semanal: qué días son entreno/descanso, pasos mínimos
- Protocolo de cheat meal
- Tips generales (intercambiabilidad de fuentes HC, proteína, verdura, fruta)
- Información sobre NEAT y cardio LISS

## QUÉ NECESITO

Crea todos los modelos Pydantic en src/models/. Sigue este orden:

### PASO 1: Modelo de ejercicios (`src/models/exercise_db.py`)

Catálogo de ejercicios con toda la metadata necesaria para seleccionarlos:

```python
class MuscleGroup(str, Enum):
    """Grupos musculares principales."""
    CHEST = "chest"
    BACK = "back"
    SHOULDERS = "shoulders"
    BICEPS = "biceps"
    TRICEPS = "triceps"
    QUADS = "quads"
    HAMSTRINGS = "hamstrings"
    GLUTES = "glutes"
    CALVES = "calves"
    ABS = "abs"
    FOREARMS = "forearms"
    ADDUCTORS = "adductors"
    TRAPS = "traps"
    REAR_DELTS = "rear_delts"
    LATERAL_DELTS = "lateral_delts"

class MovementPattern(str, Enum):
    """Patrones de movimiento biomecánicos."""
    HORIZONTAL_PUSH = "horizontal_push"
    VERTICAL_PUSH = "vertical_push"
    HORIZONTAL_PULL = "horizontal_pull"
    VERTICAL_PULL = "vertical_pull"
    KNEE_DOMINANT = "knee_dominant"      # sentadilla, prensa, extensiones
    HIP_DOMINANT = "hip_dominant"        # peso muerto, hip thrust
    ISOLATION_ARMS = "isolation_arms"
    ISOLATION_SHOULDERS = "isolation_shoulders"
    CORE = "core"
    CALVES = "calves"

class Equipment(str, Enum):
    """Equipamiento necesario."""
    BARBELL = "barbell"
    DUMBBELL = "dumbbell"
    CABLE = "cable"
    MACHINE = "machine"
    SMITH_MACHINE = "smith_machine"
    BODYWEIGHT = "bodyweight"
    BANDS = "bands"
    KETTLEBELL = "kettlebell"
    EZ_BAR = "ez_bar"
    PULLUP_BAR = "pullup_bar"
    BENCH = "bench"             # plano, inclinado, declinado

class ForceProfile(str, Enum):
    """Perfil de resistencia / curva de fuerza del ejercicio."""
    # Conceptos de biomecánica de Fran PJ
    STRETCHED = "stretched"       # máxima tensión en posición estirada
    SHORTENED = "shortened"       # máxima tensión en posición contraída
    MID_RANGE = "mid_range"       # máxima tensión en rango medio
    CONSTANT = "constant"         # tensión constante (cables, máquinas)

class Exercise(BaseModel):
    """Un ejercicio del catálogo."""
    id: str                                  # slug único
    name: str                                # nombre en español
    name_en: str | None = None               # nombre en inglés (para búsquedas)
    primary_muscles: list[MuscleGroup]       # músculos principales
    secondary_muscles: list[MuscleGroup]     # músculos secundarios
    movement_pattern: MovementPattern
    equipment: list[Equipment]               # equipamiento necesario
    force_profile: ForceProfile
    is_compound: bool                        # compuesto o aislamiento
    is_unilateral: bool = False              # unilateral o bilateral
    default_rep_range: tuple[int, int]       # rango de reps recomendado (ej: (8, 12))
    default_rest_seconds: int                # descanso recomendado entre series
    technique_notes: str | None = None       # indicaciones técnicas (ángulo, agarre, ROM)
    difficulty: Literal["beginner", "intermediate", "advanced"] = "intermediate"
    video_reference: str | None = None       # URL a vídeo de técnica
```

Incluye también `ExerciseDatabase` como clase con métodos para:
- Filtrar por muscle_group, movement_pattern, equipment disponible
- Buscar por nombre
- Obtener ejercicios complementarios (antagonistas)
- Cargar catálogo desde JSON

Crea un archivo `data/exercises.json` con un catálogo inicial de al menos 60-80 ejercicios comunes cubriendo todos los patrones de movimiento y grupos musculares. Incluye variantes con distintos perfiles de fuerza (por ejemplo para pecho: press plano barra/mancuernas, press inclinado, aperturas en polea, pec deck, etc.).

### PASO 2: Modelo de cuestionario (`src/models/questionnaire.py`)

```python
class QuestionType(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    SELECT = "select"           # selección única
    MULTI_SELECT = "multi_select"  # selección múltiple
    SCALE = "scale"             # escala 1-10
    IMAGE = "image"             # foto/imagen
    TIME = "time"               # hora del día
    YES_NO = "yes_no"

class Question(BaseModel):
    id: str
    block: str                  # bloque temático
    text: str                   # texto de la pregunta
    question_type: QuestionType
    options: list[str] | None = None   # para select/multi_select
    required: bool = True
    validation_hint: str | None = None  # guía de validación
    follow_up: str | None = None        # pregunta de seguimiento si aplica

class QuestionnaireResponse(BaseModel):
    question_id: str
    value: str | int | float | list[str] | None
    image_paths: list[str] | None = None  # para preguntas tipo IMAGE
    timestamp: datetime

class Questionnaire(BaseModel):
    """Cuestionario completo con todas las preguntas organizadas por bloques."""
    blocks: dict[str, list[Question]]  # bloque → preguntas
    
    @classmethod
    def get_default(cls) -> "Questionnaire":
        """Retorna el cuestionario predeterminado con todos los bloques."""
        ...
```

Los bloques deben ser:
1. "datos_personales" — nombre, edad, sexo, altura, peso
2. "actividad_entrenamiento" — actividad actual, días disponibles, NEAT, lesiones, entreno previo
3. "nutricion_actual" — comidas, bebidas, kcals actuales, macros, sal, agua, alergias, suplementos
4. "preferencias" — alimentos que no gustan, comodidad con horarios, ventana horaria, ayuno
5. "objetivos" — objetivo principal detallado, secundarios, plazo, prioridades corporales
6. "equipamiento_fotos" — material del gimnasio, fotos corporales

Rellena TODAS las preguntas basándote en el cuestionario de referencia que te describí arriba. Cada bloque debe tener entre 3 y 8 preguntas.

### PASO 3: Perfil de usuario (`src/models/user_profile.py`)

Modelo que agrega toda la información del usuario tras completar el cuestionario:

```python
class PersonalData(BaseModel):
    name: str
    age: int
    sex: Literal["M", "F"]
    height_cm: float
    weight_kg: float
    wake_time: time
    sleep_time: time

class ActivityProfile(BaseModel):
    training_days_per_week: int
    rest_days_per_week: int
    current_training_type: str | None          # descripción de su entreno actual
    training_time: time | None                 # hora habitual de entreno
    neat_level: Literal["low", "moderate", "high"]
    injuries: list[str]                        # lesiones/molestias activas

class NutritionProfile(BaseModel):
    current_calories: int | None               # kcals que viene haciendo
    current_macros: MacroDistribution | None   # distribución actual
    meals_per_day: int
    typical_foods: str                         # descripción de comidas habituales
    disliked_foods: list[str]
    allergies: list[str]
    intolerances: list[str]
    salt_usage: Literal["low", "moderate", "high"]
    daily_water_liters: float
    habitual_drinks: list[str]
    comfortable_food_groups: list[str]         # fáciles de cocinar/llevar
    uncomfortable_food_groups: list[str]       # incómodos
    open_to_supplements: bool
    open_to_fasting: bool
    open_to_skip_breakfast: bool
    open_to_reduced_window: bool               # ventana horaria reducida

class Goals(BaseModel):
    primary_goal: Literal["fat_loss", "muscle_gain", "recomposition", "minicut", "lean_bulk", "maintenance"]
    primary_goal_detail: str                   # descripción detallada
    secondary_goals: list[str]
    target_timeframe: str | None               # plazo deseado
    priority_body_areas: list[str]             # zonas a enfatizar

class GymEquipment(BaseModel):
    available_equipment: list[Equipment]       # del enum de exercise_db
    equipment_notes: str | None                # notas adicionales
    equipment_photo_paths: list[str]           # fotos del gimnasio

class UserProfile(BaseModel):
    """Perfil completo del usuario. Se construye a partir del cuestionario."""
    id: str
    created_at: datetime
    updated_at: datetime
    personal: PersonalData
    activity: ActivityProfile
    nutrition: NutritionProfile
    goals: Goals
    gym: GymEquipment
    body_photo_paths: list[str]               # frente, espalda, perfil izq, perfil der
    
    @classmethod
    def from_questionnaire(cls, responses: list[QuestionnaireResponse]) -> "UserProfile":
        """Construye el perfil a partir de las respuestas del cuestionario."""
        ...
```

### PASO 4: Evaluación corporal (`src/models/body_assessment.py`)

```python
class BodyMeasurements(BaseModel):
    """Medidas corporales en cm."""
    weight_kg: float
    waist_cm: float | None = None
    hip_cm: float | None = None
    chest_cm: float | None = None
    arm_left_cm: float | None = None
    arm_right_cm: float | None = None
    thigh_left_cm: float | None = None
    thigh_right_cm: float | None = None
    calf_left_cm: float | None = None
    calf_right_cm: float | None = None
    neck_cm: float | None = None
    shoulder_cm: float | None = None

class VisualAssessment(BaseModel):
    """Evaluación visual a partir de fotos (generada por Claude Vision)."""
    estimated_body_fat_range: tuple[float, float]   # rango % graso estimado (ej: (15.0, 18.0))
    fat_distribution: str                           # descripción de distribución de grasa
    muscle_development: dict[str, Literal["underdeveloped", "average", "developed", "strong"]]
    # grupos musculares → nivel de desarrollo
    weak_points: list[str]                          # puntos débiles observados
    strong_points: list[str]                        # puntos fuertes observados
    posture_notes: str | None = None                # observaciones posturales
    overall_impression: str                         # impresión general

class MetabolicEstimates(BaseModel):
    """Estimaciones metabólicas calculadas."""
    bmr: float                                      # tasa metabólica basal (Mifflin-St Jeor)
    tdee: float                                     # gasto diario total estimado
    activity_factor: float                          # factor de actividad usado
    bmi: float                                      # IMC (referencial)
    waist_hip_ratio: float | None = None            # ratio cintura/cadera
    estimated_bf_formula: float | None = None       # % graso por fórmula (Navy/JP)

class PhaseRecommendation(BaseModel):
    """Recomendación de fase basada en la evaluación."""
    recommended_phase: Literal["cut", "minicut", "maintenance", "lean_bulk", "bulk", "recomposition"]
    reasoning: str                                  # justificación
    suggested_duration_weeks: int                   # duración sugerida
    suggested_calorie_target: int                   # kcal objetivo
    suggested_macros: "MacroDistribution"            # macros sugeridos

class BodyAssessment(BaseModel):
    """Evaluación corporal completa."""
    id: str
    user_id: str
    date: date
    measurements: BodyMeasurements
    visual: VisualAssessment
    metabolic: MetabolicEstimates
    phase_recommendation: PhaseRecommendation
    photos_analyzed: list[str]                       # paths de las fotos analizadas
    notes: str | None = None
```

### PASO 5: Mesociclo y entrenamiento (`src/models/mesocycle.py`)

Este es el modelo más complejo. Debe representar la estructura jerárquica completa:

Mesociclo → Microciclos → Días de entrenamiento → Ejercicios programados

```python
class SetScheme(BaseModel):
    """Esquema de series para un ejercicio en un día."""
    total_sets: int
    rep_range: tuple[int, int]                     # ej: (8, 12)
    rir: int                                        # Reps In Reserve objetivo
    is_to_failure: bool = False                     # si alguna serie es a fallo
    technique: Literal["straight", "top_back_off", "rest_pause", "drop_set", 
                       "superset", "myo_reps"] | None = None
    top_set_count: int | None = None               # series top (si es top/back-off)
    backoff_set_count: int | None = None           # series back-off
    backoff_rir: int | None = None                 # RIR de las back-off
    superset_with: str | None = None               # id del ejercicio en superserie
    rest_seconds: int = 120                         # descanso entre series
    description: str                                # texto legible: "top set: 1x?(1) / back-off: 2x?(1)"

class ExerciseLog(BaseModel):
    """Registro real de rendimiento en un ejercicio."""
    sets: list[dict]  # [{"weight_kg": 80, "reps": 10}, ...]
    notes: str | None = None
    perceived_difficulty: Literal["easy", "moderate", "hard", "maximal"] | None = None

class ProgrammedExercise(BaseModel):
    """Un ejercicio programado dentro de un día de entrenamiento."""
    order: int                                      # posición en el día (1, 2, 3...)
    exercise_id: str                                # referencia al catálogo de ejercicios
    exercise_name: str                              # nombre completo con indicaciones técnicas
    set_scheme: SetScheme
    logs: dict[int, ExerciseLog] = {}               # microciclo_number → log real
    progression_notes: str | None = None            # notas de progresión entre micros

class TrainingDay(BaseModel):
    """Un día de entrenamiento dentro del microciclo."""
    day_number: int                                 # día dentro del microciclo (1, 2, 3...)
    day_label: str                                  # ej: "Día 1 - Upper A", "Día 3 - Rest"
    is_rest_day: bool = False
    exercises: list[ProgrammedExercise] = []
    target_steps: int = 10000                       # pasos mínimos del día
    cardio_notes: str | None = None                 # notas de cardio/NEAT

class Microcycle(BaseModel):
    """Un microciclo (generalmente 1 semana) dentro del mesociclo."""
    number: int                                     # 1, 2, 3, ...
    duration_days: int = 7                          # normalmente 7 o 10
    is_deload: bool = False                         # semana de descarga
    volume_modifier: float = 1.0                    # multiplicador de volumen vs base (deload: 0.6)
    intensity_modifier: float = 1.0                 # multiplicador de intensidad
    training_days: list[TrainingDay]
    notes: str | None = None

class WeeklySchedule(BaseModel):
    """Esquema semanal de referencia."""
    days: list[dict]  # [{"day": 1, "type": "pesas", "steps": 10500}, {"day": 3, "type": "descanso", "steps": 12500}, ...]
    notes: str | None = None                        # ej: "Descansaremos cada 3 días de entrenamiento"

class Mesocycle(BaseModel):
    """Mesociclo completo de entrenamiento."""
    id: str
    user_id: str
    name: str                                       # ej: "Mesociclo Hipertrofia Upper/Lower"
    start_date: date
    end_date: date | None = None                    # calculada
    phase: Literal["hypertrophy", "strength", "cut", "minicut", "lean_bulk", "maintenance", "deload"]
    split_type: Literal["full_body", "upper_lower", "push_pull_legs", "push_pull", "bro_split", "torso_legs"]
    training_days_per_week: int
    microcycles: list[Microcycle]
    weekly_schedule: WeeklySchedule
    progression_strategy: str                       # descripción de la estrategia de progresión
    notes: str | None = None
    created_at: datetime
    
    @property
    def total_weeks(self) -> int: ...
    
    @property
    def current_microcycle(self) -> Microcycle | None:
        """Retorna el microciclo actual basándose en la fecha."""
        ...
```

### PASO 6: Plan nutricional (`src/models/nutrition_plan.py`)

```python
class MacroDistribution(BaseModel):
    """Distribución de macronutrientes."""
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    fiber_g: int | None = None
    
    @property
    def protein_pct(self) -> float: ...
    @property
    def carbs_pct(self) -> float: ...
    @property
    def fat_pct(self) -> float: ...

class FoodItem(BaseModel):
    """Un alimento dentro de una comida."""
    name: str                                       # nombre del alimento
    amount_g: float                                 # cantidad en gramos
    alternatives: list[str] = []                    # alternativas intercambiables
    alternative_amounts: list[str] = []             # cantidades de las alternativas (ej: "180gr de patata")
    preparation_notes: str | None = None            # notas de preparación
    is_optional: bool = False

class Meal(BaseModel):
    """Una comida dentro del día."""
    name: str                                       # ej: "Desayuno", "Comida", "Intraentreno"
    time_suggestion: str | None = None              # hora sugerida
    foods: list[FoodItem]
    notes: str | None = None
    is_intra_workout: bool = False                  # si es intraentreno

class DailyDiet(BaseModel):
    """Dieta para un tipo de día (entreno o descanso)."""
    day_type: Literal["training", "rest"]
    macros: MacroDistribution
    meals: list[Meal]
    supplements: list[str] = []                     # ej: ["creatina 0.1g/kg", "proteína whey 30g"]

class CheatMealProtocol(BaseModel):
    """Protocolo de comida libre."""
    strategy: str                                   # descripción de la estrategia
    pre_cheat_tips: list[str]                       # tips para antes del cheat
    day_structure: list[str]                        # ejemplo de estructura del día
    frequency: str                                  # frecuencia sugerida

class InterchangeRules(BaseModel):
    """Reglas de intercambiabilidad de alimentos."""
    carb_sources: dict[str, str]                    # alimento → equivalencia (ej: "100g arroz" → "450g patata")
    protein_sources: list[str]                      # fuentes intercambiables a igualdad de gramos
    vegetable_rule: str                             # regla para verduras
    fruit_rule: str                                 # regla para frutas (excepciones)
    notes: list[str]                                # notas adicionales

class GeneralTips(BaseModel):
    """Tips generales del plan nutricional."""
    tips: list[str]
    allowed_drinks: list[str]                       # bebidas acalóricas permitidas
    sauce_rule: str                                 # regla de salsas
    seasoning_notes: str                            # condimentos

class NutritionPlan(BaseModel):
    """Plan nutricional completo."""
    id: str
    user_id: str
    name: str                                       # ej: "Plan Minicut - Mayo 2024"
    objective: str                                  # objetivo de la fase
    phase: Literal["cut", "minicut", "maintenance", "lean_bulk", "bulk", "recomposition"]
    duration: str                                   # ej: "1 mesociclo"
    start_date: date
    training_day_diet: DailyDiet
    rest_day_diet: DailyDiet
    interchange_rules: InterchangeRules
    cheat_meal_protocol: CheatMealProtocol | None = None
    general_tips: GeneralTips
    neat_cardio_notes: str                          # info sobre NEAT y LISS
    created_at: datetime
    
    @property
    def calorie_difference(self) -> int:
        """Diferencia de kcal entre día de entreno y descanso."""
        ...
```

### PASO 7: Registro de progreso (`src/models/progress_log.py`)

```python
class WeightLog(BaseModel):
    """Registro de peso (media de varios días)."""
    weights: list[float]                            # pesos individuales del período
    average: float                                  # media
    trend: Literal["losing", "stable", "gaining"]   # tendencia
    change_from_last: float | None = None           # cambio vs último check-in (kg)

class TrainingProgress(BaseModel):
    """Progreso de entrenamiento en el período."""
    exercises_tracked: int                          # ejercicios con registro
    exercises_progressed: int                       # ejercicios con progresión de carga
    exercises_stagnated: int                        # ejercicios estancados
    exercises_regressed: int                        # ejercicios con regresión
    volume_adherence_pct: float                     # % de volumen planificado completado
    notable_prs: list[str]                          # records personales destacados
    problem_exercises: list[str]                    # ejercicios problemáticos

class SubjectiveFeedback(BaseModel):
    """Sensaciones subjetivas del usuario."""
    energy_level: int                               # 1-10
    sleep_quality: int                              # 1-10
    hunger_level: int                               # 1-10 (10 = mucha hambre)
    motivation: int                                 # 1-10
    stress_level: int                               # 1-10
    soreness: int                                   # 1-10 (DOMS)
    mood: int                                       # 1-10
    pain_or_discomfort: str | None = None            # descripción si hay dolor
    additional_notes: str | None = None

class NutritionAdherence(BaseModel):
    """Adherencia al plan nutricional."""
    adherence_pct: float                            # % estimado de adherencia
    cheat_meals_count: int                          # comidas libres en el período
    missed_meals_avg: float                         # comidas saltadas por día (media)
    supplement_adherence: bool                      # si tomó suplementos consistentemente
    water_intake_liters: float                      # media diaria de agua
    notes: str | None = None

class PhotoComparison(BaseModel):
    """Comparación visual de fotos entre períodos."""
    current_photos: list[str]                       # paths fotos actuales
    previous_photos: list[str]                      # paths fotos anteriores
    visual_changes: str                             # descripción de cambios observados (Claude Vision)
    areas_improved: list[str]                       # zonas con mejora visible
    areas_unchanged: list[str]                      # zonas sin cambio

class ProgressDecision(BaseModel):
    """Decisión tomada tras el análisis de progreso."""
    action: Literal[
        "continue",           # seguir plan actual
        "adjust_calories",    # ajustar calorías
        "adjust_macros",      # ajustar macros
        "adjust_volume",      # ajustar volumen de entreno
        "early_deload",       # descarga anticipada
        "change_phase",       # cambiar de fase
        "new_mesocycle",      # generar nuevo mesociclo
    ]
    reasoning: str                                  # justificación de la decisión
    details: dict = {}                              # detalles del ajuste
    # ej: {"calorie_change": -200, "new_target": 2100}
    # ej: {"new_phase": "maintenance", "reason": "..."}

class ProgressLog(BaseModel):
    """Registro de progreso bisemanal."""
    id: str
    user_id: str
    mesocycle_id: str
    microcycle_number: int                          # microciclo que acaba de completar
    date: date
    period_start: date                              # inicio del período evaluado
    period_end: date                                # fin del período evaluado
    weight: WeightLog
    measurements: BodyMeasurements                  # del modelo body_assessment
    training: TrainingProgress
    nutrition: NutritionAdherence
    subjective: SubjectiveFeedback
    photos: PhotoComparison | None = None           # opcional si no hay fotos nuevas
    daily_steps_avg: int                            # media de pasos diarios
    decision: ProgressDecision                      # decisión del agente
    report_summary: str                             # resumen ejecutivo del período
    created_at: datetime
```

### PASO 8: Modelo __init__ y validación cruzada

En `src/models/__init__.py` exporta todos los modelos públicos de forma limpia.

Crea también `src/models/validators.py` con funciones de validación cruzada:

```python
def validate_macros_consistency(macros: MacroDistribution) -> bool:
    """Verifica que protein*4 + carbs*4 + fat*9 ≈ calories (±50 kcal tolerancia)."""
    ...

def validate_mesocycle_structure(mesocycle: Mesocycle) -> list[str]:
    """Verifica coherencia del mesociclo: días de entreno, deload al final, etc. Retorna lista de warnings."""
    ...

def validate_nutrition_vs_assessment(plan: NutritionPlan, assessment: BodyAssessment) -> list[str]:
    """Verifica que las kcal del plan son coherentes con la recomendación de fase."""
    ...

def validate_equipment_compatibility(mesocycle: Mesocycle, available: list[Equipment]) -> list[str]:
    """Verifica que todos los ejercicios del mesociclo usan equipamiento disponible."""
    ...
```

### PASO 9: Tests

Crea en `tests/test_models/`:

- `test_exercise_db.py`: filtrado por grupo muscular, por equipamiento, búsqueda por nombre
- `test_questionnaire.py`: cuestionario default tiene todos los bloques, validación de respuestas
- `test_mesocycle.py`: estructura jerárquica correcta, propiedades calculadas, deload
- `test_nutrition_plan.py`: consistencia de macros, diferencia entreno/descanso, intercambiabilidad
- `test_progress_log.py`: tendencia de peso, decisiones válidas
- `test_validators.py`: cada función de validación con casos válidos e inválidos

Usa fixtures con datos realistas (un usuario ejemplo, un mesociclo de 4 microciclos Upper/Lower, un plan nutricional de minicut).

## REQUISITOS

- Todos los modelos heredan de pydantic.BaseModel
- Usar Field() con description para campos que lo necesiten
- model_config con json_schema_extra donde ayude a documentar
- Métodos @property para valores calculados
- Validators con @field_validator o @model_validator donde haga falta
- Imports circulares: si MacroDistribution se usa en varios archivos, ponlo en un archivo compartido (`src/models/common.py`)
- Coherencia: los enums de Equipment, MuscleGroup etc. se reutilizan en exercise_db, mesocycle, user_profile

## ORDEN DE IMPLEMENTACIÓN

Empieza por el Paso 1 y ve secuencialmente. Espera mi confirmación entre pasos. Si hay dudas sobre algún modelo, pregunta antes de implementar.

Empecemos por el PASO 1: exercise_db.py con los enums, el modelo Exercise y el catálogo JSON de 60-80 ejercicios.
```
