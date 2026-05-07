"""Ingesta masiva de fran_videos.txt con topics asignados por título.

Reutiliza una sola instancia de VideoIngester (modelo Whisper compartido).
Persiste el progreso en `output/ingest.log` y un resumen final.
"""

from __future__ import annotations

import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# Permite ejecutar el script desde la raíz del proyecto
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.classify_videos import classify, parse_line  # noqa: E402

LIST_FILE = ROOT / "fran_videos.txt"
LOG_FILE = ROOT / "output" / "ingest.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    """Append `msg` con timestamp al log file y a stderr."""
    stamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {msg}"
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, file=sys.stderr, flush=True)


def main() -> None:
    from src.knowledge.indexer import KnowledgeIndexer
    from src.knowledge.sources import KnowledgeRegistry, Topic
    from src.config.settings import get_settings
    from src.knowledge.video_ingest import VideoIngester

    settings = get_settings()
    registry = KnowledgeRegistry(settings.registry_path)
    existing_urls = {s.url for s in registry.list_all() if s.url}

    items: list[tuple[str, str, list[str]]] = []
    with LIST_FILE.open(encoding="utf-8") as f:
        for line in f:
            parsed = parse_line(line)
            if parsed is None:
                continue
            url, title = parsed
            items.append((url, title, classify(title)))

    pending = [(u, t, k) for (u, t, k) in items if u not in existing_urls]
    log(f"Total en lista: {len(items)} | ya en registry: {len(items) - len(pending)} | pendientes: {len(pending)}")

    indexer = KnowledgeIndexer()
    ingester = VideoIngester(indexer=indexer)

    ok = 0
    err = 0
    start = time.time()

    for i, (url, title, topic_names) in enumerate(pending, start=1):
        topics = [Topic(t) for t in topic_names]
        elapsed = time.time() - start
        avg = elapsed / max(i - 1, 1)
        eta_s = avg * (len(pending) - i + 1)
        log(
            f"[{i}/{len(pending)}] OK={ok} ERR={err} "
            f"ETA={eta_s / 60:.0f}min — {','.join(topic_names)} — {title[:60]}"
        )
        try:
            ingester.ingest(url, topics=topics, do_index=True)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            err += 1
            log(f"  ERROR: {exc}")
            log(f"  URL: {url}")

    total = time.time() - start
    log(f"FIN. ok={ok} err={err} tiempo={total / 60:.1f}min")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("EXCEPCIÓN no controlada:")
        log(traceback.format_exc())
        raise
