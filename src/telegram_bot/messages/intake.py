"""Mensajes de texto para el flujo de onboarding del bot de Telegram."""


def welcome_back(name: str) -> str:
    """Saludo para usuario que ya tiene perfil."""
    return f"¡Hola, <b>{name}</b>! 👋\n\nUsa /status para ver tu estado actual."


def onboarding_intro() -> str:
    """Introducción al proceso de onboarding."""
    return (
        "<b>Bienvenido a tu coach personal</b>\n\n"
        "Voy a hacerte unas preguntas para conocerte mejor y diseñar tu plan "
        "de entrenamiento y nutrición personalizado.\n\n"
        "Iremos <b>una pregunta a la vez</b>. El proceso completo tarda unos "
        "<b>10-15 minutos</b>.\n\n"
        "Puedes parar cuando quieras y retomar más tarde con /start. "
        "Tu progreso se guarda automáticamente.\n\n"
        "¿Empezamos?"
    )


def intake_complete(name: str) -> str:
    """Mensaje de completado del onboarding."""
    return (
        f"¡Perfecto, <b>{name}</b>! Ya tengo todo lo que necesito.\n\n"
        "Estoy generando tu plan personalizado. En unos segundos recibirás:\n"
        "• Tu <b>mesociclo de entrenamiento</b> en Excel\n"
        "• Tu <b>plan nutricional</b> en PDF\n\n"
        "Recuerda hacer tu check-in bisemanal con /checkin para que pueda "
        "ajustar el plan a tu progreso."
    )


def photo_request() -> str:
    """Solicitud de fotos corporales en el onboarding."""
    return (
        "Ahora necesito tus <b>fotos de referencia</b>.\n\n"
        "Envía 4 fotos en una sola vez:\n"
        "1. Frente (brazos a los lados)\n"
        "2. Espalda (brazos a los lados)\n"
        "3. Lateral izquierdo\n"
        "4. Lateral derecho\n\n"
        "<i>Con ropa ajustada o bañador, buena iluminación y fondo liso. "
        "Si prefieres saltarlas, escribe <code>saltar</code>.</i>"
    )


def multi_select_hint(options: list[str]) -> str:
    """Instrucción para preguntas de selección múltiple."""
    opciones_formateadas = "\n".join(f"  <code>{o}</code>" for o in options)
    return (
        "Puedes elegir varias opciones. Escríbelas separadas por coma.\n\n"
        f"Opciones disponibles:\n{opciones_formateadas}\n\n"
        "<i>Ejemplo: A, C</i>"
    )
