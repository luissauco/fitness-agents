"""Cuestionario inicial del usuario y modelo de respuestas.

Define los tipos de pregunta (`QuestionType`), el modelo `Question`, las
respuestas (`QuestionnaireResponse`) y la clase `Questionnaire` que organiza
las preguntas por bloques temáticos. `Questionnaire.get_default()` devuelve
el cuestionario completo predeterminado del sistema.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class QuestionType(str, Enum):
    """Tipo de respuesta esperada para cada pregunta."""

    TEXT = "text"
    NUMBER = "number"
    SELECT = "select"
    MULTI_SELECT = "multi_select"
    SCALE = "scale"
    IMAGE = "image"
    TIME = "time"
    YES_NO = "yes_no"


class Question(BaseModel):
    """Una pregunta del cuestionario."""

    id: str = Field(..., description="Identificador único de la pregunta (kebab-case).")
    block: str = Field(..., description="Bloque temático al que pertenece.")
    text: str = Field(..., description="Texto de la pregunta tal y como se muestra al usuario.")
    question_type: QuestionType
    options: list[str] | None = Field(
        default=None,
        description="Opciones disponibles. Obligatorio en SELECT y MULTI_SELECT.",
    )
    required: bool = True
    validation_hint: str | None = Field(
        default=None,
        description="Pista de validación / formato esperado (ej: 'kg con un decimal').",
    )
    follow_up: str | None = Field(
        default=None, description="Pregunta de seguimiento si la respuesta lo requiere."
    )

    @model_validator(mode="after")
    def _check_options(self) -> Question:
        """SELECT y MULTI_SELECT deben aportar opciones; el resto no debería."""
        needs_options: bool = self.question_type in (
            QuestionType.SELECT,
            QuestionType.MULTI_SELECT,
        )
        if needs_options and not self.options:
            raise ValueError(f"La pregunta '{self.id}' ({self.question_type}) requiere `options`.")
        if not needs_options and self.options:
            raise ValueError(
                f"La pregunta '{self.id}' ({self.question_type}) no debe tener `options`."
            )
        return self


class QuestionnaireResponse(BaseModel):
    """Respuesta a una pregunta concreta del cuestionario."""

    question_id: str
    value: str | int | float | list[str] | None = Field(
        default=None,
        description="Valor primario de la respuesta. None solo si la pregunta es opcional.",
    )
    image_paths: list[str] | None = Field(
        default=None, description="Rutas a imágenes; solo aplica a preguntas IMAGE."
    )
    timestamp: datetime = Field(default_factory=datetime.now)


# --------------------------------------------------------------- Bloques default


def _block_datos_personales() -> list[Question]:
    """Bloque 1: datos personales."""
    return [
        Question(
            id="nombre",
            block="datos_personales",
            text="¿Cuál es tu nombre completo?",
            question_type=QuestionType.TEXT,
        ),
        Question(
            id="edad",
            block="datos_personales",
            text="¿Cuántos años tienes?",
            question_type=QuestionType.NUMBER,
            validation_hint="Edad en años (entero).",
        ),
        Question(
            id="sexo",
            block="datos_personales",
            text="¿Cuál es tu sexo biológico?",
            question_type=QuestionType.SELECT,
            options=["M", "F"],
        ),
        Question(
            id="altura_cm",
            block="datos_personales",
            text="¿Cuál es tu altura en centímetros?",
            question_type=QuestionType.NUMBER,
            validation_hint="cm con un decimal (ej: 178.5).",
        ),
        Question(
            id="peso_ayunas_kg",
            block="datos_personales",
            text="¿Cuál es tu peso en ayunas (kg)?",
            question_type=QuestionType.NUMBER,
            validation_hint="kg con un decimal, medido por la mañana en ayunas.",
        ),
        Question(
            id="hora_levantarse",
            block="datos_personales",
            text="¿A qué hora te levantas habitualmente?",
            question_type=QuestionType.TIME,
        ),
        Question(
            id="hora_acostarse",
            block="datos_personales",
            text="¿A qué hora te acuestas habitualmente?",
            question_type=QuestionType.TIME,
        ),
    ]


def _block_actividad_entrenamiento() -> list[Question]:
    """Bloque 2: actividad y entrenamiento."""
    return [
        Question(
            id="actividad_diaria",
            block="actividad_entrenamiento",
            text="Describe tu actividad física durante el día (trabajo, desplazamientos, etc.).",
            question_type=QuestionType.TEXT,
        ),
        Question(
            id="neat_nivel",
            block="actividad_entrenamiento",
            text="¿Cómo dirías que es tu actividad fuera del entrenamiento (NEAT)?",
            question_type=QuestionType.SELECT,
            options=["bajo", "moderado", "alto"],
            validation_hint=(
                "bajo: oficina sin movimiento; moderado: caminas a diario; "
                "alto: trabajo activo."
            ),
        ),
        Question(
            id="dias_entreno_disponibles",
            block="actividad_entrenamiento",
            text="¿Cuántos días por semana puedes entrenar?",
            question_type=QuestionType.NUMBER,
            validation_hint="Entero entre 1 y 7.",
        ),
        Question(
            id="dias_descanso_total",
            block="actividad_entrenamiento",
            text="¿Cuántos días de descanso TOTAL tienes a la semana?",
            question_type=QuestionType.NUMBER,
            validation_hint="Días sin actividad estructurada.",
        ),
        Question(
            id="hora_entreno",
            block="actividad_entrenamiento",
            text="¿A qué hora sueles entrenar?",
            question_type=QuestionType.TIME,
            required=False,
        ),
        Question(
            id="tipo_entreno_previo",
            block="actividad_entrenamiento",
            text="¿Qué tipo de entrenamiento has venido siguiendo hasta ahora?",
            question_type=QuestionType.TEXT,
            validation_hint="Estructura, frecuencia, ejercicios principales, tiempo siguiéndolo.",
        ),
        Question(
            id="lesiones_molestias",
            block="actividad_entrenamiento",
            text="¿Tienes lesiones o molestias recientes a tener en cuenta?",
            question_type=QuestionType.TEXT,
            required=False,
            validation_hint="Indica zona, intensidad y si limita algún movimiento.",
        ),
    ]


def _block_nutricion_actual() -> list[Question]:
    """Bloque 3: nutrición actual."""
    return [
        Question(
            id="numero_comidas_dia",
            block="nutricion_actual",
            text="¿Cuántas comidas haces en un día normal?",
            question_type=QuestionType.NUMBER,
        ),
        Question(
            id="alimentos_habituales",
            block="nutricion_actual",
            text="Describe qué sueles comer en un día típico (alimentos por comida).",
            question_type=QuestionType.TEXT,
        ),
        Question(
            id="bebidas_habituales",
            block="nutricion_actual",
            text="¿Qué bebidas consumes habitualmente?",
            question_type=QuestionType.MULTI_SELECT,
            options=[
                "agua",
                "café",
                "té / infusiones",
                "refrescos light / zero",
                "refrescos azucarados",
                "zumos",
                "alcohol",
                "bebidas deportivas",
            ],
        ),
        Question(
            id="agua_litros_dia",
            block="nutricion_actual",
            text="¿Cuántos litros de agua bebes al día aproximadamente?",
            question_type=QuestionType.NUMBER,
            validation_hint="Litros con decimales (ej: 2.5).",
        ),
        Question(
            id="cantidad_sal",
            block="nutricion_actual",
            text="¿Cómo describirías tu consumo de sal habitual?",
            question_type=QuestionType.SELECT,
            options=["baja", "moderada", "alta"],
        ),
        Question(
            id="kcals_actuales",
            block="nutricion_actual",
            text="¿Sabes cuántas kcal estás comiendo actualmente?",
            question_type=QuestionType.NUMBER,
            required=False,
            validation_hint="Si lo sabes, kcal totales del día.",
        ),
        Question(
            id="alergias_intolerancias",
            block="nutricion_actual",
            text="¿Tienes alergias o intolerancias alimentarias?",
            question_type=QuestionType.TEXT,
            required=False,
            validation_hint="Lista separada por comas (ej: 'lactosa, gluten').",
        ),
        Question(
            id="suplementacion_actual",
            block="nutricion_actual",
            text="¿Qué suplementos tomas actualmente?",
            question_type=QuestionType.TEXT,
            required=False,
            validation_hint="Lista separada por comas con dosis (ej: 'creatina 5g, whey 30g').",
        ),
    ]


def _block_preferencias() -> list[Question]:
    """Bloque 4: preferencias y disposición."""
    return [
        Question(
            id="alimentos_no_gusta",
            block="preferencias",
            text="¿Qué alimentos no te gustan o evitas siempre?",
            question_type=QuestionType.TEXT,
            required=False,
        ),
        Question(
            id="comodidad_cocinar",
            block="preferencias",
            text="¿Qué grupos de alimentos te resultan cómodos de cocinar en casa?",
            question_type=QuestionType.MULTI_SELECT,
            options=[
                "carnes",
                "pescados",
                "huevos",
                "arroz / pasta",
                "legumbres",
                "tubérculos",
                "verduras",
                "frutas",
                "lácteos",
                "frutos secos",
            ],
        ),
        Question(
            id="comodidad_fuera",
            block="preferencias",
            text="¿Qué grupos de alimentos te resultan cómodos para llevar fuera de casa?",
            question_type=QuestionType.MULTI_SELECT,
            options=[
                "carnes",
                "pescados",
                "huevos",
                "arroz / pasta",
                "legumbres",
                "tubérculos",
                "verduras",
                "frutas",
                "lácteos",
                "frutos secos",
            ],
        ),
        Question(
            id="ventana_horaria_reducida",
            block="preferencias",
            text="¿Estarías dispuesto a comer en una ventana horaria reducida (ej: 8h)?",
            question_type=QuestionType.YES_NO,
        ),
        Question(
            id="saltarse_desayuno",
            block="preferencias",
            text="¿Estarías dispuesto a saltarte el desayuno si fuera lo más práctico?",
            question_type=QuestionType.YES_NO,
        ),
        Question(
            id="abierto_suplementos",
            block="preferencias",
            text="¿Estás abierto a tomar suplementos si están justificados?",
            question_type=QuestionType.YES_NO,
        ),
    ]


def _block_objetivos() -> list[Question]:
    """Bloque 5: objetivos."""
    return [
        Question(
            id="objetivo_principal",
            block="objetivos",
            text="¿Cuál es tu objetivo principal?",
            question_type=QuestionType.SELECT,
            options=[
                "fat_loss",
                "muscle_gain",
                "recomposition",
                "minicut",
                "lean_bulk",
                "maintenance",
            ],
        ),
        Question(
            id="objetivo_detallado",
            block="objetivos",
            text="Describe con tus palabras qué quieres conseguir y por qué.",
            question_type=QuestionType.TEXT,
            validation_hint="Detalla el resultado esperado, no solo el tipo de fase.",
        ),
        Question(
            id="objetivos_secundarios",
            block="objetivos",
            text="¿Tienes algún objetivo secundario (rendimiento, salud, estético)?",
            question_type=QuestionType.TEXT,
            required=False,
        ),
        Question(
            id="plazo",
            block="objetivos",
            text="¿En qué plazo te gustaría ver los resultados principales?",
            question_type=QuestionType.TEXT,
            required=False,
            validation_hint="Ej: '3 meses', 'antes de verano', 'sin prisa'.",
        ),
        Question(
            id="zonas_prioritarias",
            block="objetivos",
            text="¿Qué zonas corporales te gustaría enfatizar?",
            question_type=QuestionType.MULTI_SELECT,
            required=False,
            options=[
                "pecho",
                "espalda",
                "hombros",
                "brazos",
                "abdomen",
                "glúteos",
                "cuádriceps",
                "isquios",
                "gemelos",
            ],
        ),
    ]


def _block_equipamiento_fotos() -> list[Question]:
    """Bloque 6: equipamiento del gimnasio y fotos corporales."""
    return [
        Question(
            id="material_gimnasio",
            block="equipamiento_fotos",
            text="Describe el material disponible en el gimnasio donde entrenas.",
            question_type=QuestionType.TEXT,
            validation_hint="Mencionar máquinas clave, poleas, mancuernas máx, etc.",
        ),
        Question(
            id="equipamiento_fotos_paths",
            block="equipamiento_fotos",
            text="Sube fotos del gimnasio (opcional, ayuda a identificar maquinaria).",
            question_type=QuestionType.IMAGE,
            required=False,
        ),
        Question(
            id="foto_frente",
            block="equipamiento_fotos",
            text="Foto de cuerpo entero de FRENTE (en ropa interior o ajustada).",
            question_type=QuestionType.IMAGE,
        ),
        Question(
            id="foto_espalda",
            block="equipamiento_fotos",
            text="Foto de cuerpo entero de ESPALDA.",
            question_type=QuestionType.IMAGE,
        ),
        Question(
            id="foto_perfil_izquierdo",
            block="equipamiento_fotos",
            text="Foto de cuerpo entero de PERFIL IZQUIERDO.",
            question_type=QuestionType.IMAGE,
        ),
        Question(
            id="foto_perfil_derecho",
            block="equipamiento_fotos",
            text="Foto de cuerpo entero de PERFIL DERECHO.",
            question_type=QuestionType.IMAGE,
        ),
    ]


# Orden canónico de los bloques (afecta a iteración del cuestionario).
_DEFAULT_BLOCK_ORDER: tuple[str, ...] = (
    "datos_personales",
    "actividad_entrenamiento",
    "nutricion_actual",
    "preferencias",
    "objetivos",
    "equipamiento_fotos",
)

_DEFAULT_BLOCK_FACTORIES = {
    "datos_personales": _block_datos_personales,
    "actividad_entrenamiento": _block_actividad_entrenamiento,
    "nutricion_actual": _block_nutricion_actual,
    "preferencias": _block_preferencias,
    "objetivos": _block_objetivos,
    "equipamiento_fotos": _block_equipamiento_fotos,
}


class Questionnaire(BaseModel):
    """Cuestionario completo organizado por bloques."""

    blocks: dict[str, list[Question]] = Field(
        ..., description="Mapa de nombre_bloque → lista de preguntas (orden preservado)."
    )

    @classmethod
    def get_default(cls) -> Questionnaire:
        """Cuestionario predeterminado con los 6 bloques completos."""
        blocks: dict[str, list[Question]] = {
            name: _DEFAULT_BLOCK_FACTORIES[name]() for name in _DEFAULT_BLOCK_ORDER
        }
        return cls(blocks=blocks)

    # --------------------------------------------------------------- Consultas

    def all_questions(self) -> list[Question]:
        """Devuelve todas las preguntas en orden canónico de bloques."""
        return [q for block_name in _DEFAULT_BLOCK_ORDER for q in self.blocks.get(block_name, [])]

    def find_question(self, question_id: str) -> Question | None:
        """Busca una pregunta por id en cualquier bloque."""
        for questions in self.blocks.values():
            for q in questions:
                if q.id == question_id:
                    return q
        return None

    def required_question_ids(self) -> list[str]:
        """Ids de las preguntas obligatorias (útil para validar completitud)."""
        return [q.id for q in self.all_questions() if q.required]

    def missing_required(self, responses: list[QuestionnaireResponse]) -> list[str]:
        """Devuelve los ids de preguntas obligatorias sin responder."""
        answered: set[str] = {
            r.question_id for r in responses if r.value is not None or r.image_paths
        }
        return [qid for qid in self.required_question_ids() if qid not in answered]
