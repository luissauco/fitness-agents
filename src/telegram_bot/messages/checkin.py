"""Mensajes de texto para el flujo de check-in bisemanal del bot de Telegram."""


def checkin_intro(mesocycle_name: str) -> str:
    """Introducción al check-in bisemanal."""
    return (
        "<b>Check-in bisemanal</b> 📅\n\n"
        f"Mesociclo activo: <b>{mesocycle_name}</b>\n\n"
        "Voy a pedirte unos datos para evaluar tu progreso y ajustar el plan "
        "si es necesario. Tarda unos 5 minutos.\n\n"
        "¡Empecemos!"
    )


def no_active_mesocycle() -> str:
    """Error: no hay mesociclo activo."""
    return (
        "No tienes ningún mesociclo activo en este momento.\n\n"
        "Usa /start para crear tu perfil y generar tu primer plan."
    )


def ask_weights() -> str:
    """Solicitud de pesajes en ayunas."""
    return (
        "<b>Peso corporal</b>\n\n"
        "Escribe entre 3 y 5 pesajes en ayunas de esta semana, separados por coma.\n\n"
        "<i>Ejemplo: 78.5, 78.2, 78.8, 78.4</i>"
    )


def ask_measurement(field_name: str, unit: str = "cm") -> str:
    """Solicitud de una medida corporal específica."""
    return (
        f"<b>Medida: {field_name}</b>\n\n"
        f"Introduce tu medida de <b>{field_name}</b> en {unit}.\n\n"
        f"<i>Ejemplo: 82.5</i>"
    )


def ask_photos() -> str:
    """Solicitud de fotos corporales del check-in."""
    return (
        "<b>Fotos del check-in</b>\n\n"
        "Envía 4 fotos en una sola vez:\n"
        "1. Frente (brazos a los lados)\n"
        "2. Espalda (brazos a los lados)\n"
        "3. Lateral izquierdo\n"
        "4. Lateral derecho\n\n"
        "<i>Mismas condiciones que las fotos iniciales. "
        "Si prefieres saltarlas, escribe <code>saltar</code>.</i>"
    )


def ask_adherence() -> str:
    """Solicitud de adherencia a la dieta."""
    return (
        "<b>Adherencia a la dieta</b>\n\n"
        "Del 1 al 10, ¿cómo valorarías tu adherencia al plan nutricional "
        "esta quincena?\n\n"
        "<i>1 = muy baja, 10 = perfecta</i>"
    )


def ask_cheat_meals() -> str:
    """Solicitud del número de comidas trampa."""
    return (
        "<b>Comidas trampa</b>\n\n"
        "¿Cuántas comidas fuera del plan tuviste esta quincena?\n\n"
        "Responde con un número: <code>0</code>, <code>1</code>, "
        "<code>2</code>, <code>3</code> o más."
    )


def ask_steps() -> str:
    """Solicitud de pasos diarios promedio."""
    return (
        "<b>Actividad no estructurada</b>\n\n"
        "¿Cuál fue tu promedio de pasos diarios esta quincena?\n\n"
        "<i>Ejemplo: 8500</i>"
    )


def ask_subjective(field: str) -> str:
    """Solicitud de valoración subjetiva de un campo específico."""
    return (
        f"<b>{field.capitalize()}</b>\n\n"
        f"Del 1 al 10, ¿cómo valorarías tu <b>{field}</b> esta quincena?\n\n"
        "<i>1 = muy malo, 10 = excelente</i>"
    )


def ask_pain() -> str:
    """Pregunta sobre dolor o molestias durante el entrenamiento."""
    return (
        "<b>Dolor o molestias</b>\n\n"
        "¿Has tenido algún dolor o molestia muscular/articular "
        "durante los entrenamientos?\n\n"
        "Responde <code>sí</code> o <code>no</code>."
    )


def ask_pain_description() -> str:
    """Solicitud de descripción del dolor o molestia."""
    return (
        "Describe brevemente la molestia: zona afectada, cuándo aparece "
        "y nivel de intensidad del 1 al 10.\n\n"
        "<i>Ejemplo: rodilla derecha al bajar escaleras, nivel 4</i>"
    )


def ask_training_logs() -> str:
    """Solicitud de logs de entrenamiento (opcional)."""
    return (
        "<b>Registros de entrenamiento</b> <i>(opcional)</i>\n\n"
        "Puedes enviar tus anotaciones o capturas de los entrenamientos "
        "de las últimas dos semanas.\n\n"
        "Si no tienes o prefieres saltarlo, escribe <code>saltar</code>."
    )


def ask_notes() -> str:
    """Solicitud de notas adicionales (opcional)."""
    return (
        "<b>Notas adicionales</b> <i>(opcional)</i>\n\n"
        "¿Hay algo más que quieras comentar sobre estas dos semanas? "
        "Cualquier detalle que consideres relevante.\n\n"
        "Si no tienes nada que añadir, escribe <code>saltar</code>."
    )


def checkin_processing() -> str:
    """Mensaje de procesamiento del check-in."""
    return (
        "Procesando tu check-in... Esto puede tardar 30-60 segundos.\n\n"
        "<i>Estoy analizando tu progreso y ajustando el plan.</i>"
    )


def checkin_complete() -> str:
    """Mensaje de check-in completado."""
    return (
        "¡Check-in completado! En unos segundos recibirás:\n\n"
        "• <b>Informe de progreso</b> con análisis de las últimas dos semanas\n"
        "• <b>Plan actualizado</b> si hay ajustes en entrenamiento o nutrición\n\n"
        "Buen trabajo por mantener el seguimiento."
    )


def checkin_reminder() -> str:
    """Recordatorio de check-in bisemanal."""
    return (
        "Es hora de tu check-in bisemanal 📅\n\n"
        "Han pasado dos semanas desde el último registro. "
        "Usa /checkin para revisar tu progreso y ajustar el plan."
    )


def invalid_weight() -> str:
    """Error: peso inválido."""
    return (
        "No he podido leer ese peso. Asegúrate de usar punto como separador decimal "
        "y comas para separar varios valores.\n\n"
        "<i>Ejemplo: 78.5, 78.2, 78.8</i>"
    )


def invalid_number() -> str:
    """Error: número inválido."""
    return (
        "Ese valor no parece un número válido. "
        "Introduce solo dígitos, usando punto como separador decimal si es necesario.\n\n"
        "<i>Ejemplo: 82.5</i>"
    )


def skip_optional() -> str:
    """Confirmación de campo opcional saltado."""
    return "<i>Campo omitido. Continuamos.</i>"
