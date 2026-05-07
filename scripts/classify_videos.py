"""Clasifica los vídeos de fran_videos.txt en topics del enum Topic según su título.

Uso:
    python scripts/classify_videos.py            # imprime tabla URL → topics
    python scripts/classify_videos.py --csv      # genera CSV con (url, topics)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

LIST_FILE = Path("fran_videos.txt")

# Reglas keyword → topic. Las claves se buscan como substrings en el título normalizado
# (lowercase, sin tildes). Cada regla puede activar 1+ topics. El topic por defecto si
# nada matchea es `hypertrophy` (la temática global del canal).
RULES: list[tuple[str, tuple[str, ...]]] = [
    # NUTRICIÓN / DIETA
    ("deficit", ("nutrition", "cutting")),
    ("definicion", ("nutrition", "cutting")),
    ("mini cut", ("nutrition", "cutting")),
    ("superavit", ("nutrition", "bulking")),
    ("recomp", ("nutrition", "recomposition")),
    ("macronutrient", ("nutrition", "macros")),
    ("proteic", ("nutrition", "macros")),
    ("proteina", ("nutrition", "macros")),
    ("sintesis proteica", ("nutrition", "macros", "hypertrophy")),
    ("antes de entrenar", ("nutrition", "meal_planning")),
    ("intra entrena", ("nutrition", "meal_planning")),
    ("intraentrena", ("nutrition", "meal_planning")),
    ("bebida intra", ("nutrition", "meal_planning")),
    ("comer", ("nutrition",)),
    ("dieta", ("nutrition",)),
    ("hambre", ("nutrition",)),
    ("calori", ("nutrition",)),
    ("glucosa", ("nutrition", "macros")),
    # SUPLEMENTACIÓN
    ("suplement", ("supplements",)),
    ("creatina", ("supplements",)),
    ("cafeina", ("supplements",)),
    ("cafeína", ("supplements",)),
    ("omega", ("supplements",)),
    ("vitamina", ("supplements",)),
    ("jengibre", ("supplements",)),
    # PERIODIZACIÓN / PROGRAMACIÓN
    ("mesociclo", ("periodization",)),
    ("microciclo", ("periodization",)),
    ("descarga", ("periodization", "deload")),
    ("deload", ("periodization", "deload")),
    ("planificar", ("periodization",)),
    ("planificacion", ("periodization",)),
    ("rutina", ("periodization", "exercise_selection")),
    ("split", ("periodization", "exercise_selection")),
    ("frecuencia", ("periodization", "volume")),
    ("torso/pierna", ("periodization", "exercise_selection")),
    ("torso pierna", ("periodization", "exercise_selection")),
    ("fullbody", ("periodization", "exercise_selection")),
    ("full body", ("periodization", "exercise_selection")),
    ("upper lower", ("periodization", "exercise_selection")),
    ("up/low", ("periodization", "exercise_selection")),
    ("push pull", ("periodization", "exercise_selection")),
    # SOBRECARGA
    ("sobrecarga progresiva", ("progressive_overload",)),
    ("sobrecarga", ("progressive_overload",)),
    ("estancamiento", ("progressive_overload", "periodization")),
    ("estancarte", ("progressive_overload", "periodization")),
    # VOLUMEN / INTENSIDAD
    ("volumen", ("volume",)),
    ("series efectivas", ("volume", "intensity")),
    ("repeticiones", ("intensity", "volume")),
    ("rangos de repeticiones", ("intensity", "volume")),
    ("cargas altas", ("intensity",)),
    ("cargas bajas", ("intensity",)),
    ("intensidad", ("intensity",)),
    # FALLO
    ("fallo muscular", ("intensity",)),
    ("fallo de tarea", ("intensity",)),
    ("al fallo", ("intensity",)),
    ("entrenar al fallo", ("intensity",)),
    ("rir", ("intensity",)),
    # RECUPERACIÓN / FATIGA
    ("recupera", ("recovery",)),
    ("fatiga", ("recovery", "intensity")),
    ("descansar", ("recovery", "rest_pause")),
    ("descanso", ("recovery", "rest_pause")),
    ("sobreentrena", ("recovery",)),
    ("agujetas", ("recovery",)),
    ("doms", ("recovery",)),
    ("daño muscular", ("recovery", "hypertrophy")),
    ("dano muscular", ("recovery", "hypertrophy")),
    ("atrofiar", ("recovery", "hypertrophy")),
    ("memoria muscular", ("recovery", "hypertrophy")),
    ("catabolismo", ("recovery", "hypertrophy")),
    # TÉCNICAS
    ("rest pause", ("rest_pause",)),
    ("rest-pause", ("rest_pause",)),
    ("superseries", ("supersets",)),
    ("super series", ("supersets",)),
    ("drop set", ("supersets", "intensity")),
    ("dropset", ("supersets", "intensity")),
    # BIOMECÁNICA
    ("biomecanica", ("biomechanics",)),
    ("biomecánica", ("biomechanics",)),
    ("brazo de momento", ("biomechanics",)),
    ("brazos de momento", ("biomechanics",)),
    ("perfil de resistencia", ("resistance_profile", "biomechanics")),
    ("excentrica", ("biomechanics", "intensity")),
    ("excéntrica", ("biomechanics", "intensity")),
    ("concentrica", ("biomechanics", "intensity")),
    ("concéntrica", ("biomechanics", "intensity")),
    ("isometric", ("biomechanics", "intensity")),
    ("velocidad", ("biomechanics", "intensity")),
    ("polea", ("biomechanics", "exercise_selection")),
    ("agarre", ("biomechanics", "exercise_selection")),
    # LONGITUD / ESTIRAMIENTO
    ("estiramiento", ("muscle_length", "hypertrophy")),
    ("parciales en estira", ("muscle_length", "hypertrophy")),
    ("parciales", ("muscle_length", "hypertrophy")),
    ("hipertrofia mediada", ("muscle_length", "hypertrophy")),
    ("longitud", ("muscle_length", "hypertrophy")),
    # SELECCIÓN DE EJERCICIOS / GRUPOS MUSCULARES
    ("pectoral", ("exercise_selection", "biomechanics")),
    ("pecho", ("exercise_selection", "biomechanics")),
    ("dorsal", ("exercise_selection", "biomechanics")),
    ("espalda", ("exercise_selection", "biomechanics")),
    ("biceps", ("exercise_selection", "biomechanics")),
    ("bíceps", ("exercise_selection", "biomechanics")),
    ("triceps", ("exercise_selection", "biomechanics")),
    ("tríceps", ("exercise_selection", "biomechanics")),
    ("braquial", ("exercise_selection", "biomechanics")),
    ("deltoides", ("exercise_selection", "biomechanics")),
    ("hombro", ("exercise_selection", "biomechanics")),
    ("trapecio", ("exercise_selection", "biomechanics")),
    ("gluteo", ("exercise_selection", "biomechanics")),
    ("glúteo", ("exercise_selection", "biomechanics")),
    ("cuadriceps", ("exercise_selection", "biomechanics")),
    ("cuádriceps", ("exercise_selection", "biomechanics")),
    ("isquio", ("exercise_selection", "biomechanics")),
    ("femoral", ("exercise_selection", "biomechanics")),
    ("gemelo", ("exercise_selection", "biomechanics")),
    ("gastrocnemio", ("exercise_selection", "biomechanics")),
    ("antebrazo", ("exercise_selection", "biomechanics")),
    ("aductor", ("exercise_selection", "biomechanics")),
    ("serrato", ("exercise_selection", "biomechanics")),
    ("piramidal", ("exercise_selection", "biomechanics")),
    ("calf", ("exercise_selection",)),
    # EJERCICIOS CONCRETOS
    ("sentadilla", ("exercise_selection",)),
    ("prensa", ("exercise_selection",)),
    ("hip thrust", ("exercise_selection",)),
    ("bulgara", ("exercise_selection",)),
    ("búlgara", ("exercise_selection",)),
    ("pullover", ("exercise_selection", "biomechanics")),
    ("curl", ("exercise_selection",)),
    ("press", ("exercise_selection",)),
    ("jalon", ("exercise_selection",)),
    ("jalón", ("exercise_selection",)),
    ("remo", ("exercise_selection",)),
    ("extension", ("exercise_selection",)),
    ("extensión", ("exercise_selection",)),
    ("elevacion", ("exercise_selection",)),
    ("elevación", ("exercise_selection",)),
    ("zancada", ("exercise_selection",)),
    ("hipopresivo", ("exercise_selection",)),
    # CARDIO / NEAT
    ("cardio", ("neat_cardio",)),
    ("neat", ("neat_cardio",)),
    # COMPOSICIÓN CORPORAL
    ("ganancia de masa", ("hypertrophy", "body_composition")),
    ("ganar musculo", ("hypertrophy", "body_composition")),
    ("ganar músculo", ("hypertrophy", "body_composition")),
    ("perder grasa", ("body_composition", "cutting")),
    ("retencion liquidos", ("body_composition",)),
    # HORMONAS / FISIOLOGÍA
    ("testosterona", ("hypertrophy", "supplements")),
    ("cortisol", ("hypertrophy", "recovery")),
    ("hormonal", ("hypertrophy", "recovery")),
    ("ribosoma", ("hypertrophy",)),
    ("sintesis", ("hypertrophy", "macros")),
    ("síntesis", ("hypertrophy", "macros")),
    ("contraccion", ("hypertrophy", "biomechanics")),
    ("contracción", ("hypertrophy", "biomechanics")),
    ("fibra muscular", ("hypertrophy", "biomechanics")),
    ("tension mecanica", ("hypertrophy", "intensity")),
    ("tensión mecánica", ("hypertrophy", "intensity")),
    ("tut", ("intensity",)),
    ("tiempo bajo tension", ("intensity",)),
    ("estimulo", ("hypertrophy", "intensity")),
    ("estímulo", ("hypertrophy", "intensity")),
    ("hipertrofia", ("hypertrophy",)),
    ("musculo", ("hypertrophy",)),
    ("músculo", ("hypertrophy",)),
    # AVANZADOS / NOVATOS
    ("atleta avanzado", ("periodization", "intensity")),
    ("avanzado", ("periodization",)),
    ("novato", ("periodization",)),
    ("principiante", ("periodization",)),
    # CALENTAMIENTO
    ("calentar", ("recovery", "periodization")),
    ("calentamiento", ("recovery", "periodization")),
    # MITOS
    ("mito", ("hypertrophy",)),
    ("desmint", ("hypertrophy",)),
    ("mentira", ("hypertrophy",)),
]

DEFAULT_TOPICS: tuple[str, ...] = ("hypertrophy",)


def normalize(text: str) -> str:
    """Lowercase + sin tildes para matching robusto."""
    table = str.maketrans("áéíóúüñ", "aeiouun")
    return text.lower().translate(table)


def classify(title: str) -> list[str]:
    """Devuelve lista de topics ordenada y deduplicada para un título."""
    norm = normalize(title)
    found: list[str] = []
    for keyword, topics in RULES:
        if keyword in norm:
            for t in topics:
                if t not in found:
                    found.append(t)
    if not found:
        found = list(DEFAULT_TOPICS)
    return found


def parse_line(line: str) -> tuple[str, str] | None:
    """Devuelve `(url, title)` para una línea de URL, o None si no aplica."""
    if not line.startswith("https://"):
        return None
    m = re.match(r"^(https://\S+)\s+#\s+\[YA\]?\s*\d+:\d+\s+(.*)$", line.strip())
    if m:
        return m.group(1), m.group(2)
    m = re.match(r"^(https://\S+)\s+#\s+\d+:\d+\s+(.*)$", line.strip())
    if m:
        return m.group(1), m.group(2)
    return None


def main() -> None:
    rows: list[tuple[str, str, list[str]]] = []
    with LIST_FILE.open(encoding="utf-8") as f:
        for line in f:
            parsed = parse_line(line)
            if parsed is None:
                continue
            url, title = parsed
            rows.append((url, title, classify(title)))

    if "--csv" in sys.argv:
        for url, _title, topics in rows:
            print(f"{url}\t{','.join(topics)}")
        return

    # Tabla resumen y muestra
    print(f"Total vídeos: {len(rows)}\n")
    from collections import Counter
    topic_counts: Counter[str] = Counter()
    for _u, _t, topics in rows:
        for t in topics:
            topic_counts[t] += 1
    print("Topics asignados (recuento):")
    for t, n in topic_counts.most_common():
        print(f"  {t:25s} {n:4d}")
    print("\nMuestra (primeros 20):")
    for url, title, topics in rows[:20]:
        vid = url.rsplit("/", 1)[-1]
        print(f"  {vid:22s} {','.join(topics):45s} {title[:60]}")


if __name__ == "__main__":
    main()
