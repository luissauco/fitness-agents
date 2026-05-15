"""Mensajes de error para el bot de Telegram."""


def error_block(errors: list[str]) -> str:
    """Bloque de errores formateado en HTML."""
    detalle = "\n".join(errors)
    return f"<b>⚠️ Errores</b>\n\n<pre>{detalle}</pre>"


def generic_error() -> str:
    """Error genérico del sistema."""
    return (
        "Ha ocurrido un error inesperado. Por favor, inténtalo de nuevo.\n\n"
        "Si el problema persiste, usa /start para reiniciar."
    )


def not_understood() -> str:
    """El bot no ha entendido el mensaje."""
    return "No he entendido ese mensaje.\n\nUsa /help para ver los comandos disponibles."


def access_denied() -> str:
    """Acceso denegado al usuario."""
    return "No tienes acceso a este bot.\n\nContacta con el administrador para solicitar acceso."
