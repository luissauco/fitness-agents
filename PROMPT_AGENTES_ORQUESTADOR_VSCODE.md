# PROMPT PARA CREAR AGENTES Y ORQUESTADOR EN VSCODE

> Pega este prompt en Claude Code dentro de tu proyecto fitness-agents.
> Modelo recomendado: **Claude Opus 4.7 con extended thinking activado (high effort)**.
> Claude Code ya tiene el CLAUDE.md con las reglas del proyecto + Karpathy.

---

## PROMPT:

````
Vamos a construir el corazón del sistema multi-agente: los 5 agentes especializados y el orquestador LangGraph que los coordina.

## CONTEXTO

Ya tenemos construido:
- Estructura del proyecto (src/, cli/, tests/, output/)
- Módulo RAG en src/knowledge/ con indexer, retriever, chunker, embeddings
  - El retriever expone `retrieve_for_agent(query, agent_type, k)` que devuelve contexto formateado
- Módulo de modelos en src/models/ con todos los modelos Pydantic:
  - UserProfile, Questionnaire, BodyAssessment, MacroDistribution
  - Mesocycle (con Microcycle, TrainingDay, ProgrammedExercise, SetScheme)
  - NutritionPlan (con DailyDiet, Meal, FoodItem, InterchangeRules)
  - ProgressLog (con WeightLog, TrainingProgress, SubjectiveFeedback, ProgressDecision)
  - ExerciseDatabase con catálogo de ejercicios
- Configuración en src/config/settings.py con la API key de Anthropic
- Validators cruzados en src/models/validators.py

Ahora construimos los agentes que toman estos modelos como input/output y usan Claude para razonar.

## ARQUITECTURA GENERAL

Cada agente es una clase que:
1. Recibe inputs (modelos Pydantic + contexto)
2. Consulta el RAG con queries relevantes a su dominio
3. Construye un prompt estructurado para Claude
4. Llama a la API de Claude con structured outputs (JSON schema del modelo de salida)
5. Valida la respuesta con los validators cruzados
6. Retorna un modelo Pydantic validado

El orquestador es un grafo LangGraph donde cada nodo es un agente y los edges son las transiciones de fase.

## MODELOS DE CLAUDE A USAR EN PRODUCCIÓN

Usa estos identificadores de modelo (verifica en src/config/settings.py si están definidos como constantes):
- claude-opus-4-7 → para agentes que generan estructuras complejas: training, nutrition
- claude-sonnet-4-6 → para agentes conversacionales o de análisis: intake, assessment, progress
- claude-haiku-4-5-20251001 → reservado para tareas simples (futuro)

Cada agente debe tener su modelo configurable desde settings.

## QUÉ NECESITO

Sigue este orden EXACTO. Espera mi confirmación entre pasos. Si tienes dudas técnicas, pregunta antes.

---

### PASO 1: Infraestructura compartida (`src/agents/base.py` + `src/agents/claude_client.py`)

**1.1 Cliente Claude wrapper (`claude_client.py`):**

Crea una clase `ClaudeClient` que encapsule el SDK de Anthropic:

```python
class ClaudeClient:
    """Wrapper async sobre el SDK de Anthropic con reintentos y logging."""
    
    def __init__(self, settings: Settings):
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.settings = settings
    
    async def generate_structured(
        self,
        model: str,
        system_prompt: str,
        user_message: str | list[dict],  # str o lista multimodal con imágenes
        response_model: type[BaseModel],
        max_tokens: int = 8192,
        temperature: float = 0.7,
        thinking: bool = False,  # extended thinking
    ) -> BaseModel:
        """
        Genera output estructurado validado contra un modelo Pydantic.
        Usa el patrón de tool use con un único tool que tiene el schema del modelo.
        Reintenta hasta 3 veces si la validación falla.
        """
        ...
    
    async def generate_text(
        self,
        model: str,
        system_prompt: str,
        user_message: str | list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """Genera texto libre (para agentes conversacionales)."""
        ...
    
    async def generate_stream(
        self,
        model: str,
        system_prompt: str,
        user_message: str | list[dict],
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Genera respuesta en streaming (yields chunks de texto)."""
        ...
```

Detalles de implementación:
- Para `generate_structured`: usa `tools=[{"name": "submit", "input_schema": response_model.model_json_schema()}]` con `tool_choice={"type": "tool", "name": "submit"}`
- Para imágenes: el `user_message` puede ser una lista con bloques `{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": ...}}` y `{"type": "text", "text": "..."}`
- Función helper para convertir paths de imágenes a base64
- Logging con loguru: cada llamada con modelo, tokens consumidos, latencia
- Reintentos exponenciales con tenacity en errores de API (no en errores de validación)
- Si falla validación Pydantic, reintenta diciéndole a Claude el error exacto

**1.2 Clase base de agente (`base.py`):**

```python
class BaseAgent(ABC):
    """Clase base para todos los agentes del sistema."""
    
    name: str  # identificador del agente
    model: str  # modelo de Claude a usar
    agent_type: str  # tipo para retrieve_for_agent ("training", "nutrition", etc.)
    
    def __init__(
        self,
        claude_client: ClaudeClient,
        retriever: KnowledgeRetriever,
        settings: Settings,
    ):
        self.claude = claude_client
        self.retriever = retriever
        self.settings = settings
        self.system_prompt = self._load_system_prompt()
    
    def _load_system_prompt(self) -> str:
        """Carga el system prompt desde src/config/prompts/{name}.md"""
        ...
    
    async def get_rag_context(self, query: str, k: int = 5) -> str:
        """Helper para consultar el RAG con el agent_type del agente."""
        return self.retriever.retrieve_for_agent(query, self.agent_type, k=k)
    
    @abstractmethod
    async def run(self, *args, **kwargs):
        """Ejecuta la lógica del agente. Cada subclase implementa su firma."""
        ...
```

**1.3 Estructura de prompts:**

Crea `src/config/prompts/` con un .md por agente. Los prompts deben:
- Definir el rol del agente con claridad
- Especificar el output esperado
- Incluir las reglas no negociables del agente
- Dejar placeholders donde se inyectará el contexto (RAG, modelos del usuario)

Crea solo los archivos vacíos por ahora (orchestrator.md, intake.md, assessment.md, training.md, nutrition.md, progress.md). Los rellenamos en cada paso.

**1.4 Tests:**

`tests/test_agents/test_claude_client.py`:
- Mock del SDK de Anthropic
- Test de generate_structured con modelo Pydantic simple
- Test de reintento ante error de validación
- Test de manejo de imágenes en user_message

---

### PASO 2: Agente Intake (`src/agents/intake.py`)

Agente conversacional que recoge el cuestionario inicial. NO es one-shot — mantiene una conversación stateful con el usuario.

**Modelo a usar:** `claude-sonnet-4-6` (es conversacional, no necesita Opus).

**Comportamiento:**

```python
class IntakeAgent(BaseAgent):
    name = "intake"
    agent_type = "general"  # consulta poco RAG
    
    async def start_session(self) -> IntakeSession:
        """Inicia una nueva sesión de cuestionario."""
        ...
    
    async def process_response(
        self,
        session: IntakeSession,
        user_message: str,
        attached_images: list[str] | None = None,
    ) -> IntakeTurn:
        """
        Procesa una respuesta del usuario y devuelve el siguiente turno.
        
        Returns:
            IntakeTurn con:
            - assistant_message: pregunta o comentario del agente
            - is_complete: True si ya recogió todo
            - validated_responses: respuestas validadas hasta ahora
            - pending_questions: preguntas pendientes
        """
        ...
    
    async def build_profile(self, session: IntakeSession) -> UserProfile:
        """Construye el UserProfile final a partir de las respuestas."""
        ...
```

**Lógica:**

1. El agente conoce el `Questionnaire.get_default()` con todos los bloques.
2. En cada turno, decide:
   - Si la respuesta del usuario completa una pregunta válidamente → guarda y avanza
   - Si es ambigua → pide clarificación
   - Si el usuario se desvía → reconduce con empatía
   - Si el usuario menciona algo importante en otra pregunta → lo recoge anticipadamente
3. Conversación natural, no formulario. No pregunta varios bloques a la vez.
4. Detecta cuándo solicitar fotos corporales y fotos del gimnasio.
5. Al final, llama a `UserProfile.from_questionnaire(responses)` y valida.

**System prompt** (`src/config/prompts/intake.md`):

Define un agente entrevistador empático, en español, que:
- Hace una pregunta a la vez
- Valida sin interrogar
- No juzga hábitos del usuario
- Pregunta el bloque "objetivos" en último lugar para que el resto contextualice
- Antes de pedir fotos, explica para qué se usan
- Resume al final lo que ha entendido

**Modelo IntakeSession (en `src/models/intake_session.py`):**

```python
class IntakeTurn(BaseModel):
    """Un turno de la conversación de intake."""
    assistant_message: str
    is_complete: bool
    next_question_id: str | None
    validated_responses: list[QuestionnaireResponse]
    pending_questions: list[str]  # ids de preguntas pendientes
    awaiting_image: bool = False  # si está esperando una foto
    
class IntakeSession(BaseModel):
    """Estado de una sesión de cuestionario."""
    id: str
    user_id: str
    started_at: datetime
    completed_at: datetime | None = None
    questionnaire: Questionnaire
    responses: list[QuestionnaireResponse]
    conversation_history: list[dict]  # [{"role": "user"|"assistant", "content": "..."}]
    current_block: str
```

**Tests:**

`tests/test_agents/test_intake.py`:
- Mock de ClaudeClient
- Test de inicio de sesión: primera pregunta es del bloque correcto
- Test de avance: respuesta válida → siguiente pregunta
- Test de clarificación: respuesta ambigua → re-pregunta
- Test de finalización: todas respondidas → build_profile retorna UserProfile válido

---

### PASO 3: Agente Assessment (`src/agents/assessment.py`)

Análisis corporal usando Claude Vision sobre las fotos.

**Modelo a usar:** `claude-sonnet-4-6` (vision capable, suficiente).

**Comportamiento:**

```python
class AssessmentAgent(BaseAgent):
    name = "assessment"
    agent_type = "assessment"
    
    async def run(
        self,
        profile: UserProfile,
        measurements: BodyMeasurements,
    ) -> BodyAssessment:
        """
        Analiza fotos y medidas para generar evaluación corporal.
        
        Returns: BodyAssessment con visual, metabolic y phase_recommendation
        """
        ...
    
    def _calculate_metabolic_estimates(
        self,
        profile: UserProfile,
        measurements: BodyMeasurements,
    ) -> MetabolicEstimates:
        """Cálculo determinístico (no LLM): Mifflin-St Jeor, IMC, ratios."""
        ...
    
    async def _analyze_photos(
        self,
        photo_paths: list[str],
        profile: UserProfile,
    ) -> VisualAssessment:
        """Llama a Claude Vision con las 4 fotos para análisis cualitativo."""
        ...
    
    async def _recommend_phase(
        self,
        profile: UserProfile,
        visual: VisualAssessment,
        metabolic: MetabolicEstimates,
    ) -> PhaseRecommendation:
        """Recomienda fase (cut/bulk/recomp) consultando RAG y razonando."""
        ...
```

**Lógica:**

1. `_calculate_metabolic_estimates`: cálculo puro Python, sin LLM:
   - BMR Mifflin-St Jeor según sexo
   - TDEE = BMR × factor (sedentario 1.2, ligero 1.375, moderado 1.55, alto 1.725, muy alto 1.9). El factor lo deriva de profile.activity
   - IMC = peso / (altura/100)²
   - Ratio cintura/cadera si ambos existen
   - % graso por fórmula Navy si hay las medidas necesarias

2. `_analyze_photos`: una sola llamada a Claude Vision con las 4 fotos en el mismo mensaje multimodal:
   - System prompt instruye al agente a ser conservador en estimaciones
   - User message: "[imagen frente] [imagen espalda] [imagen perfil izq] [imagen perfil der] Analiza la composición corporal de esta persona. Es {sexo}, {edad} años, {altura} cm, {peso} kg."
   - Output estructurado: VisualAssessment

3. `_recommend_phase`:
   - Consulta RAG con query como "recomendación de fase según composición corporal y objetivo"
   - Pasa a Claude: profile + visual + metabolic + RAG context
   - Output: PhaseRecommendation con kcal target y macros sugeridos
   - Validar con `validate_macros_consistency`

**System prompt** (`src/config/prompts/assessment.md`):

- Evaluador clínico pero realista
- Estimaciones de % graso siempre como rango (ej: 15-18%), nunca puntual
- Identifica puntos débiles sin dramatismo
- Justifica recomendación de fase con datos del usuario y conocimiento del RAG
- Si el usuario está en un % graso muy alto/bajo, lo refleja con honestidad

**Tests:**

- Mock de ClaudeClient para vision
- Test de cálculo de BMR/TDEE con valores conocidos
- Test de Navy formula con medidas de ejemplo
- Test de coherencia: phase recommendation tiene kcal coherentes con TDEE y fase

---

### PASO 4: Agente Training (`src/agents/training.py`)

Generación del mesociclo completo. ESTE ES EL AGENTE MÁS COMPLEJO.

**Modelo a usar:** `claude-opus-4-7` con extended thinking. Necesita razonamiento profundo.

**Comportamiento:**

```python
class TrainingAgent(BaseAgent):
    name = "training"
    agent_type = "training"
    
    async def run(
        self,
        profile: UserProfile,
        assessment: BodyAssessment,
        previous_mesocycle: Mesocycle | None = None,
    ) -> Mesocycle:
        """
        Genera un mesociclo completo de entrenamiento.
        
        Si hay previous_mesocycle, considera la progresión desde ese.
        """
        ...
    
    def _select_split(self, training_days: int, level: str) -> str:
        """Selección determinística del split según días y nivel."""
        ...
    
    async def _design_mesocycle_structure(
        self,
        profile: UserProfile,
        assessment: BodyAssessment,
        split: str,
        rag_context: str,
    ) -> MesocycleStructure:
        """
        Decide estructura de alto nivel: número de microciclos, progresión,
        ejercicios principales por día. Output intermedio antes del detalle.
        """
        ...
    
    async def _populate_microcycles(
        self,
        structure: MesocycleStructure,
        exercise_db: ExerciseDatabase,
        available_equipment: list[Equipment],
        rag_context: str,
    ) -> list[Microcycle]:
        """
        Genera el detalle completo de cada microciclo:
        - Ejercicios concretos del catálogo (con id válido)
        - SetScheme con técnicas (top set, rest-pause, supersets)
        - Progresión entre microciclos
        - Microciclo de descarga al final
        """
        ...
    
    def _validate_mesocycle(self, mesocycle: Mesocycle, profile: UserProfile) -> None:
        """
        Valida con los validators cruzados:
        - validate_mesocycle_structure
        - validate_equipment_compatibility
        Si hay errores graves, lanza excepción. Warnings se logean.
        """
        ...
```

**Lógica del agente:**

1. `_select_split` (determinístico):
   - 3 días → full_body
   - 4 días → upper_lower
   - 5 días → push_pull_legs (+ uno extra) o torso_legs
   - 6 días → push_pull_legs ×2

2. Consulta RAG con queries específicas:
   - "metodología hipertrofia split {split} volumen efectivo"
   - "selección ejercicios biomecánica para {muscle_group_priority}"
   - "progresión microciclos RIR cargas {phase}"
   - "técnicas intensificación rest-pause superseries"
   
   Combina los chunks recuperados en un único `rag_context`.

3. `_design_mesocycle_structure` (LLM):
   - Decide nº de microciclos (4-5 + descarga estándar)
   - Define el patrón de progresión: micro 1 RIR 2-3, micro 2 RIR 1-2, micro 3 RIR 0-1, micro 4 pico, micro 5 descarga
   - Define ejercicios principales (compuestos) por día sin entrar en detalle de series

4. `_populate_microcycles` (LLM, structured output Microcycle):
   - Por cada microciclo, genera todos los TrainingDay con todos los ProgrammedExercise
   - Cada exercise_id debe existir en ExerciseDatabase (validar)
   - Cada equipamiento debe estar disponible (validar)
   - SetScheme realista: top sets con back-off, rest-pause solo en aislamientos finales, superseries en ejercicios complementarios
   - Pasos diarios: 10500 días entreno, 12500 días descanso (para fase de cut, ajustar para bulk)

5. Validación final: si hay errores, reintenta UNA vez con el error en el prompt.

**System prompt** (`src/config/prompts/training.md`):

Este prompt debe ser EXTENSO y meticuloso. Define:
- Rol: programador de entrenamiento basado en evidencia, metodología Fran Pérez Jurado
- Principios de selección de ejercicios:
  * Patrones de movimiento equilibrados (push horizontal/vertical, pull horizontal/vertical, knee/hip dominant)
  * Variedad de force profile (stretched, shortened, mid-range) por grupo muscular
  * Compuestos antes que aislamientos
  * Aislamientos al final, ahí van las técnicas de intensificación
- Volumen efectivo por grupo muscular (rango 10-20 series semanales según experiencia)
- Frecuencia: cada grupo muscular 2 veces por semana mínimo
- Reglas de progresión por microciclo
- Cuándo usar cada técnica (rest-pause, superseries, drop sets, myo-reps)
- Reglas duras:
  * Si el usuario tiene lesión X, evitar ejercicios que carguen X
  * Si el usuario está en cut, priorizar mantenimiento de fuerza (más intensidad, menos volumen)
  * En descarga: -40% volumen, RIR 3+
- Indicaciones técnicas en exercise_name (ángulo, agarre, ROM): tomar de Exercise.technique_notes del catálogo

**Tests:**

- Mock de ClaudeClient con respuesta estructurada válida
- Test de _select_split para distintos días
- Test de validación: ejercicio con equipamiento no disponible → falla
- Test de progresión: RIR del último micro de carga < RIR del primero
- Test de descarga: último microciclo tiene is_deload=True y volume_modifier <= 0.7
- Integration test (con mock): genera mesociclo completo, todos los exercise_ids existen

---

### PASO 5: Agente Nutrition (`src/agents/nutrition.py`)

Generación del plan nutricional.

**Modelo a usar:** `claude-opus-4-7`. La generación de comidas con intercambiabilidad es compleja.

**Comportamiento:**

```python
class NutritionAgent(BaseAgent):
    name = "nutrition"
    agent_type = "nutrition"
    
    async def run(
        self,
        profile: UserProfile,
        assessment: BodyAssessment,
        mesocycle: Mesocycle,  # para coordinar entreno con nutrición
        previous_plan: NutritionPlan | None = None,
    ) -> NutritionPlan:
        """Genera plan nutricional completo."""
        ...
    
    def _calculate_target_macros(
        self,
        profile: UserProfile,
        assessment: BodyAssessment,
        day_type: Literal["training", "rest"],
    ) -> MacroDistribution:
        """Cálculo determinístico de macros target según fase y tipo de día."""
        ...
    
    async def _design_meals(
        self,
        target_macros: MacroDistribution,
        profile: UserProfile,
        day_type: Literal["training", "rest"],
        rag_context: str,
    ) -> DailyDiet:
        """LLM genera las comidas que cuadran con los macros target."""
        ...
    
    def _build_interchange_rules(self) -> InterchangeRules:
        """Reglas de intercambiabilidad estándar (constantes del sistema)."""
        ...
```

**Lógica:**

1. `_calculate_target_macros` (determinístico):
   - Calorías base = TDEE del assessment
   - Ajuste según fase:
     * minicut: -25% (corta duración)
     * cut: -15-20%
     * maintenance: 0%
     * lean_bulk: +10%
     * bulk: +15-20%
   - Día entreno vs descanso: descanso tiene -200 a -400 kcal (los HC son los que bajan)
   - Proteína: 2.0 g/kg constante
   - Grasas: 0.9 g/kg constante (mínimo hormonal)
   - HC: rellena lo que queda → proteína×4 + grasas×9 + HC×4 = kcal_total
   - Validar con `validate_macros_consistency`

2. Para cada day_type, llama a `_design_meals` que:
   - Consulta RAG: "estructura de comidas {fase}, intercambiabilidad fuentes"
   - Pasa al LLM: target_macros + profile (gustos, alergias, comodidad) + rag_context
   - LLM genera DailyDiet con N comidas que cuadran los macros (margen ±5%)
   - Cada FoodItem tiene alternatives intercambiables a igualdad de macros
   - Si profile.activity.training_time existe, intraentreno entre comidas adyacentes

3. `_build_interchange_rules`: constantes del proyecto:
   - HC: arroz=pasta=quinoa=cous_cous=legumbres (g a g), patata/boniato 4.5×
   - Proteína: pollo=pavo=pescado_blanco=burger_meat=lomo (g a g)
   - Verduras: intercambiables a igualdad de gramos
   - Frutas: intercambiables EXCEPTO plátano

4. Si profile.nutrition.open_to_supplements: añadir creatina 0.1g/kg como suplemento extra

5. Construye NutritionPlan con todo + cheat_meal_protocol estándar + general_tips

**System prompt** (`src/config/prompts/nutrition.md`):

- Nutricionista deportivo pragmático, prioriza adherencia
- En español, registro neutro
- Reglas duras:
  * NUNCA recomienda kcal por debajo de BMR salvo casos médicos
  * NUNCA proteína < 1.6 g/kg
  * NUNCA grasas < 0.6 g/kg
  * Respeta TODAS las alergias e intolerancias del profile
  * NO incluye alimentos en `disliked_foods`
  * Cantidad de comidas adaptada a `meals_per_day` del profile
  * Si `open_to_skip_breakfast`, ofrece versión con/sin desayuno
- Estructura comidas pensando en cocinabilidad (los `comfortable_food_groups` se usan más)

**Tests:**

- Test de cálculo de macros: cut → kcal < TDEE
- Test de día entreno vs descanso: training tiene más HC
- Test de respeto a alergias: mock con "lácteos" en allergies → ningún FoodItem con lácteos
- Test de coherencia: sum de macros de meals ≈ target_macros (±5%)
- Test de intercambiabilidad: cada FoodItem con HC tiene al menos 1 alternativa

---

### PASO 6: Agente Progress (`src/agents/progress.py`)

Análisis de progreso bisemanal y decisión de ajustes.

**Modelo a usar:** `claude-sonnet-4-6` con vision (compara fotos antes/después).

**Comportamiento:**

```python
class ProgressAgent(BaseAgent):
    name = "progress"
    agent_type = "progress"
    
    async def run(
        self,
        profile: UserProfile,
        current_mesocycle: Mesocycle,
        current_plan: NutritionPlan,
        checkin_data: CheckinInput,
        previous_logs: list[ProgressLog],
    ) -> ProgressLog:
        """
        Analiza el período y genera ProgressLog con decisión.
        """
        ...
    
    def _analyze_weight_trend(
        self,
        current_weights: list[float],
        previous_logs: list[ProgressLog],
        target_phase: str,
    ) -> WeightLog:
        """Análisis determinístico de tendencia."""
        ...
    
    def _analyze_training_progress(
        self,
        current_mesocycle: Mesocycle,
        microcycle_completed: int,
    ) -> TrainingProgress:
        """Análisis de logs de entrenamiento del período."""
        ...
    
    async def _compare_photos(
        self,
        current_photos: list[str],
        previous_photos: list[str],
    ) -> PhotoComparison:
        """Claude Vision compara conjuntos de fotos."""
        ...
    
    async def _make_decision(
        self,
        weight: WeightLog,
        training: TrainingProgress,
        nutrition: NutritionAdherence,
        subjective: SubjectiveFeedback,
        photos: PhotoComparison | None,
        profile: UserProfile,
        current_phase: str,
        rag_context: str,
    ) -> ProgressDecision:
        """LLM toma la decisión de ajuste basándose en todo."""
        ...
```

**Modelo de input** (`src/models/checkin_input.py`):

```python
class CheckinInput(BaseModel):
    """Datos que el usuario aporta en el check-in bisemanal."""
    weights: list[float]  # pesos individuales del período
    measurements: BodyMeasurements
    photos: list[str] | None  # paths a fotos nuevas (opcional)
    training_logs: list[dict]  # [{exercise_id, sets: [{weight, reps}], notes}]
    nutrition_adherence_self_estimate: float  # 0.0-1.0
    cheat_meals_count: int
    daily_steps_avg: int
    subjective: SubjectiveFeedback  # ya estructurado del modelo
    user_notes: str | None
```

**Lógica:**

1. `_analyze_weight_trend`:
   - Media del período actual
   - Comparación con media del período anterior
   - Tendencia: losing (>200g/semana en cut), stable, gaining
   - Coherencia con fase: en cut, expectativa = pérdida 0.5-1% peso/semana

2. `_analyze_training_progress`:
   - Recorre `current_mesocycle.microcycles[microcycle_completed].training_days`
   - Compara logs registrados con el SetScheme programado
   - Cuenta exercises_progressed (más kg o más reps que el micro anterior)
   - Identifica problem_exercises (regresión consistente)

3. `_compare_photos` (si hay fotos nuevas):
   - Llama a Claude Vision con TODAS las fotos: actuales + previas
   - Pide identificación de cambios visibles, zonas mejoradas, sin cambio
   - Output estructurado: PhotoComparison

4. `_make_decision`:
   - Consulta RAG con query relevante a la situación: "ajuste calorías estancamiento cut", "señales fatiga acumulada deload anticipada"
   - Pasa a Claude un resumen completo del período + previous_logs (últimos 3) para tendencia larga
   - Output estructurado: ProgressDecision con action y details

**Reglas duras de decisión:**

- Si subjective.energy_level < 4 y soreness > 7 por 2 períodos seguidos → consider early_deload
- Si pain_or_discomfort no es null → mencionar y considerar adjust_volume o cambio de ejercicio
- Si weight.trend es opuesto al esperado por la fase → adjust_calories
- Si microcycle_completed == último microciclo del mesocycle → action = new_mesocycle
- Si todo va bien → action = continue

**System prompt** (`src/config/prompts/progress.md`):

- Analista honesto pero motivador
- En español, no infantilizar
- Comunica problemas con datos, no con drama
- Si hay señal de overtraining o problema de salud → menciona consultar profesional
- Decisiones siempre justificadas con datos del período + tendencia + RAG

**Tests:**

- Test de weight trend: pérdida 0.7%/semana → trend = "losing"
- Test de decisión: cut + ganancia de peso → action = "adjust_calories" con calorie_change negativo
- Test de detección de fatiga: subjective bajo + soreness alto → early_deload
- Test de fin de mesociclo: microcycle_completed == len(microcycles) → action = "new_mesocycle"

---

### PASO 7: Estado global del grafo (`src/graph/state.py`)

Define el estado compartido del LangGraph workflow.

```python
from typing import TypedDict, Annotated, Literal
from langgraph.graph import add_messages

class FitnessState(TypedDict):
    """Estado global del flujo del sistema."""
    
    # Identificación
    user_id: str
    session_id: str
    current_phase: Literal[
        "onboarding",      # cuestionario en curso
        "assessment",      # evaluando con fotos/medidas
        "planning",        # generando mesociclo y dieta
        "active",          # usuario en período activo de entrenamiento
        "checkin",         # procesando check-in bisemanal
        "completed",       # mesociclo terminado, esperando nuevo
    ]
    
    # Perfil del usuario (se construye en intake)
    user_profile: UserProfile | None
    intake_session: IntakeSession | None  # solo durante onboarding
    
    # Evaluación (se construye en assessment)
    body_assessment: BodyAssessment | None
    
    # Plan activo
    current_mesocycle: Mesocycle | None
    current_nutrition_plan: NutritionPlan | None
    current_microcycle_index: int  # cuál microciclo está activo (0-indexed)
    
    # Progreso
    progress_logs: list[ProgressLog]
    last_checkin_date: date | None
    next_checkin_date: date | None
    pending_checkin_data: CheckinInput | None
    
    # Conversación
    messages: Annotated[list[dict], add_messages]
    pending_user_input: str | None  # para flujo conversacional
    pending_action: str | None
    
    # Outputs generados (paths a archivos)
    generated_files: list[str]
    
    # Errores y warnings
    errors: list[str]
    warnings: list[str]


def initial_state(user_id: str) -> FitnessState:
    """Estado inicial para un usuario nuevo."""
    return FitnessState(
        user_id=user_id,
        session_id=str(uuid4()),
        current_phase="onboarding",
        user_profile=None,
        intake_session=None,
        body_assessment=None,
        current_mesocycle=None,
        current_nutrition_plan=None,
        current_microcycle_index=0,
        progress_logs=[],
        last_checkin_date=None,
        next_checkin_date=None,
        pending_checkin_data=None,
        messages=[],
        pending_user_input=None,
        pending_action=None,
        generated_files=[],
        errors=[],
        warnings=[],
    )
```

Crea también `src/graph/checkpoints.py` con setup del SqliteSaver de LangGraph para persistir el estado entre sesiones.

---

### PASO 8: Grafo LangGraph (`src/graph/workflow.py`)

El orquestador. Define los nodos y edges del grafo.

**Nodos** (uno por agente + algunos auxiliares):

```python
async def intake_node(state: FitnessState) -> dict:
    """Procesa un turno de cuestionario."""
    ...

async def assessment_node(state: FitnessState) -> dict:
    """Genera evaluación corporal cuando hay perfil completo."""
    ...

async def training_node(state: FitnessState) -> dict:
    """Genera mesociclo."""
    ...

async def nutrition_node(state: FitnessState) -> dict:
    """Genera plan nutricional."""
    ...

async def progress_node(state: FitnessState) -> dict:
    """Procesa check-in bisemanal."""
    ...

async def schedule_checkin_node(state: FitnessState) -> dict:
    """Programa próximo check-in (+ 14 días)."""
    ...

async def advance_microcycle_node(state: FitnessState) -> dict:
    """Avanza al siguiente microciclo activo."""
    ...
```

Cada nodo:
- Recibe FitnessState
- Llama al agente correspondiente
- Retorna un dict con las claves a actualizar (LangGraph hace merge automático)
- Maneja errores: si falla, añade a state.errors y NO avanza la fase

**Edges condicionales:**

```python
def route_after_intake(state: FitnessState) -> str:
    """Router después del nodo intake."""
    if state["user_profile"] is None:
        return "intake"  # seguir intake
    return "assessment"

def route_after_assessment(state: FitnessState) -> str:
    if state["body_assessment"] is None:
        return "END"  # error
    return "training"

def route_after_planning(state: FitnessState) -> str:
    """Tras generar plan, terminamos planning y entramos en activo."""
    if state["current_mesocycle"] and state["current_nutrition_plan"]:
        return "schedule_checkin"
    return "END"

def route_after_progress(state: FitnessState) -> str:
    """Tras check-in, según la decisión del agente."""
    if not state["progress_logs"]:
        return "END"
    
    last_log = state["progress_logs"][-1]
    decision = last_log.decision.action
    
    if decision == "new_mesocycle":
        return "training"  # genera nuevo mesociclo
    elif decision in ("adjust_calories", "adjust_macros"):
        return "nutrition"  # regenera plan nutricional
    elif decision == "adjust_volume":
        return "training"  # regenera mesociclo
    else:  # continue, early_deload (que ya está en el mesociclo)
        return "advance_microcycle"
```

**Construcción del grafo:**

```python
def build_workflow() -> CompiledStateGraph:
    workflow = StateGraph(FitnessState)
    
    # Nodos
    workflow.add_node("intake", intake_node)
    workflow.add_node("assessment", assessment_node)
    workflow.add_node("training", training_node)
    workflow.add_node("nutrition", nutrition_node)
    workflow.add_node("progress", progress_node)
    workflow.add_node("schedule_checkin", schedule_checkin_node)
    workflow.add_node("advance_microcycle", advance_microcycle_node)
    
    # Entry point
    workflow.set_entry_point("intake")
    
    # Edges condicionales
    workflow.add_conditional_edges("intake", route_after_intake, {
        "intake": "intake",
        "assessment": "assessment",
    })
    workflow.add_conditional_edges("assessment", route_after_assessment, {
        "training": "training",
        "END": END,
    })
    workflow.add_edge("training", "nutrition")  # secuencial
    workflow.add_conditional_edges("nutrition", route_after_planning, {
        "schedule_checkin": "schedule_checkin",
        "END": END,
    })
    workflow.add_edge("schedule_checkin", END)
    
    workflow.add_conditional_edges("progress", route_after_progress, {
        "training": "training",
        "nutrition": "nutrition",
        "advance_microcycle": "advance_microcycle",
        "END": END,
    })
    workflow.add_edge("advance_microcycle", END)
    
    # Checkpointer
    checkpointer = get_sqlite_checkpointer()
    
    return workflow.compile(checkpointer=checkpointer)
```

**Punto de entrada para ejecutar el flujo:**

```python
async def run_workflow(
    initial_state: FitnessState,
    config: RunnableConfig,
) -> FitnessState:
    """Ejecuta el grafo desde el estado inicial."""
    workflow = build_workflow()
    final_state = await workflow.ainvoke(initial_state, config=config)
    return final_state

async def resume_workflow(
    user_id: str,
    new_input: dict,
    config: RunnableConfig,
) -> FitnessState:
    """Reanuda el workflow desde el último checkpoint."""
    workflow = build_workflow()
    # Carga último estado, aplica new_input, continúa
    ...
```

**Tests de integración:**

`tests/test_graph/test_workflow.py`:
- Test de flujo completo con mocks: onboarding → assessment → planning → schedule
- Test de reanudación: estado guardado, se carga, continúa
- Test de check-in: estado activo, check-in con tendencia mala → adjust_calories → nutrition node

---

### PASO 9: Wiring final y CLI (`cli/commands/`)

Comandos CLI básicos para probar el flujo end-to-end:

```python
# cli/commands/start.py
@app.command()
def start(user_id: str = typer.Option(..., prompt=True)):
    """Inicia onboarding para un nuevo usuario."""
    ...

# cli/commands/checkin.py
@app.command()
def checkin(user_id: str):
    """Inicia check-in bisemanal."""
    ...

# cli/commands/status.py
@app.command()
def status(user_id: str):
    """Muestra estado actual del usuario."""
    ...
```

Estos comandos:
1. Cargan settings + ClaudeClient + Retriever
2. Cargan o inicializan FitnessState
3. Ejecutan el workflow
4. Muestran output con Rich

NO incluyas generación de archivos (Excel/PDF) en este paso. Eso es la siguiente fase. Por ahora los comandos solo guardan los modelos Pydantic en SQLite y muestran resúmenes en terminal.

---

### PASO 10: Persistencia (`src/db/`)

Implementa el CRUD básico para los modelos:

```python
# src/db/repositories.py
class UserProfileRepository:
    def get(self, user_id: str) -> UserProfile | None: ...
    def save(self, profile: UserProfile) -> None: ...

class MesocycleRepository:
    def get_current(self, user_id: str) -> Mesocycle | None: ...
    def save(self, mesocycle: Mesocycle) -> None: ...
    def list_history(self, user_id: str) -> list[Mesocycle]: ...

class NutritionPlanRepository: ...
class BodyAssessmentRepository: ...
class ProgressLogRepository: ...
```

SQLite con sqlmodel o sqlalchemy. Cada modelo Pydantic se serializa a JSON en una columna, más metadata indexable (user_id, created_at, etc.).

Migraciones simples al iniciar (CREATE TABLE IF NOT EXISTS).

---

## REQUISITOS GENERALES

- Todo async donde tenga sentido (I/O, API calls)
- Logging estructurado con loguru en cada agente
- Manejo de errores: capturar, logear con contexto, retry una vez si tiene sentido
- Tests con pytest-asyncio para código async
- Type hints completos
- Docstrings en español en métodos públicos
- Costs tracking: cada llamada a Claude logea tokens consumidos para tracking de costes
- NO mockees el RAG en los tests de los agentes (mockea solo ClaudeClient). Si el RAG está vacío, el retriever retornará lista vacía y el agente debe seguir funcionando con esa información.

## CHECKPOINT FINAL

Al terminar el paso 10, debe ser posible:

```bash
fitness start --user-id luis
# (responde al cuestionario interactivo)
# (sube fotos)
# → genera UserProfile, BodyAssessment, Mesocycle, NutritionPlan
# → todo guardado en SQLite

fitness status --user-id luis
# Muestra: fase actual, microciclo activo, próximo check-in

fitness checkin --user-id luis
# (mete pesos, fotos, logs de entreno, sensaciones)
# → genera ProgressLog con decisión
# → si la decisión es regenerar, lanza el nodo correspondiente
```

Aún sin Excel/PDF, pero con TODA la lógica de agentes funcionando y persistente.

---

## ORDEN DE EJECUCIÓN

Empieza por el PASO 1 y espera mi confirmación entre cada paso. Si tienes dudas técnicas serias (especialmente en el paso 4 que es el más complejo), pregunta antes de implementar.

Antes de empezar el PASO 1: revisa src/knowledge/retriever.py y src/models/*.py para confirmar las firmas exactas de las clases que vas a usar. Si algo no encaja con lo que asumo en este prompt, dímelo y nos adaptamos.
````

---

## NOTAS POSTERIORES

### Modelos en producción vs desarrollo

| Tarea | Modelo | Razón |
|---|---|---|
| Escribir este código (Claude Code) | **Opus 4.7 + extended thinking** | Arquitectura crítica, decisiones difíciles de revertir |
| Iteraciones y bugfixes posteriores | Sonnet 4.6 | 5× más barato, suficiente para tweaks |
| Agente Intake en producción | Sonnet 4.6 | Conversacional, no necesita razonamiento profundo |
| Agente Assessment en producción | Sonnet 4.6 | Vision + análisis estándar |
| Agente Training en producción | **Opus 4.7** | Generación estructurada compleja con muchas reglas |
| Agente Nutrition en producción | **Opus 4.7** | Cuadrar macros + intercambiabilidad + restricciones |
| Agente Progress en producción | Sonnet 4.6 | Análisis de tendencias, no necesita Opus |

### Después de este prompt

Cuando termines, faltan dos piezas grandes:
1. **Generadores** — convertir Mesocycle → .xlsx y NutritionPlan → .pdf
2. **UI** — la decisión que comentamos (Telegram bot primero, web app después)

Ambas son aditivas: el core de agentes ya funcionará y guardará los modelos en SQLite.
