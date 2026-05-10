# Roadmap

[English](ROADMAP.en.md) | Espanol

Este roadmap mantiene visible hacia donde va `fitness-agents` y que partes estan listas para recibir contribuciones.

## v0.1 - Base Del Dominio

Estado: completo.

- [x] CLI `fitness-kb`.
- [x] Registry de fuentes.
- [x] Chunking, embeddings, ChromaDB y recuperacion semantica.
- [x] Ingesta de videos y transcripciones.
- [x] Modelos Pydantic para usuario, cuestionario, ejercicios, mesociclo, nutricion y progreso.
- [x] Tests de knowledge y models.
- [ ] Fuentes cientificas revisadas con citas normalizadas.

## v0.2 - Agentes

Estado: completo.

- [x] Agente de intake.
- [x] Agente de evaluacion corporal.
- [x] Agente de entrenamiento.
- [x] Agente de nutricion.
- [x] Agente de progreso.
- [x] Orquestador LangGraph con checkpoints SQLite.
- [x] Prompts con contexto RAG por agente.
- [x] CLI `fitness` con comandos start, checkin y status.
- [x] Persistencia SQLite con repositorios de usuarios y sesiones.

## v0.3 - Salidas Profesionales

- [ ] Exportacion de mesociclos a Excel.
- [ ] Exportacion de planes nutricionales a PDF.
- [ ] Plantillas editables para entrenadores.
- [ ] Trazabilidad de fuentes usadas en cada recomendacion.

## v0.4 - Demo Publica

- [ ] Notebook reproducible.
- [ ] Demo web o app local.
- [ ] Dataset pequeno de ejemplo.
- [ ] Screenshots y video corto para README.

## v1.0 - Producto Tecnico Estable

- [ ] API estable.
- [ ] Versionado de esquemas.
- [ ] Tests de integracion end-to-end.
- [ ] Documentacion completa para contribuyentes.
- [ ] Release publica con changelog.
