"""Mensajes de texto para el comando /status del bot de Telegram."""

from datetime import date


def status_message(
    name: str,
    mesocycle_name: str | None,
    microcycle_current: int | None,
    microcycle_total: int | None,
    next_checkin: date | None,
    recent_files: list[str],
) -> str:
    """Mensaje de estado completo del usuario."""
    lines: list[str] = [f"<b>Estado de {name}</b>\n"]

    # Sección mesociclo
    if mesocycle_name:
        lines.append(f"<b>Mesociclo activo:</b> {mesocycle_name}")
        if microcycle_current is not None and microcycle_total is not None:
            lines.append(f"<b>Microciclo:</b> {microcycle_current} de {microcycle_total}")
    else:
        lines.append("<i>Sin mesociclo activo.</i> Usa /start para crear tu plan.")

    lines.append("")

    # Próximo check-in
    if next_checkin:
        dias_restantes = (next_checkin - date.today()).days
        if dias_restantes > 0:
            linea_checkin = (
                f"<b>Próximo check-in:</b> {next_checkin.strftime('%d/%m/%Y')} "
                f"(en {dias_restantes} días)"
            )
        elif dias_restantes == 0:
            linea_checkin = "<b>Próximo check-in:</b> ¡hoy! Usa /checkin."
        else:
            linea_checkin = (
                "<b>Check-in pendiente</b> desde "
                f"{next_checkin.strftime('%d/%m/%Y')}. Usa /checkin."
            )
        lines.append(linea_checkin)
        lines.append("")

    # Archivos recientes
    if recent_files:
        lines.append("<b>Últimos archivos generados:</b>")
        for f in recent_files:
            lines.append(f"  • <code>{f}</code>")
    else:
        lines.append("<i>Todavía no hay archivos generados.</i>")

    return "\n".join(lines)


def no_profile_yet() -> str:
    """Mensaje cuando el usuario aún no tiene perfil."""
    return (
        "Todavía no tienes un perfil creado.\n\n"
        "Usa /start para comenzar el cuestionario inicial y "
        "generar tu primer plan personalizado."
    )
