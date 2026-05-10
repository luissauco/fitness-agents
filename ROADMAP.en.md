# Roadmap

English | [Espanol](ROADMAP.md)

This roadmap keeps the direction of `fitness-agents` visible and highlights which parts are ready for contributions.

## v0.1 - Domain Foundation

Status: complete.

- [x] `fitness-kb` CLI.
- [x] Source registry.
- [x] Chunking, embeddings, ChromaDB, and semantic retrieval.
- [x] Video ingestion and transcripts.
- [x] Pydantic models for users, questionnaires, exercises, mesocycles, nutrition, and progress.
- [x] Knowledge and model tests.
- [ ] Reviewed scientific sources with normalized citations.

## v0.2 - Agents

Status: complete.

- [x] Intake agent.
- [x] Body assessment agent.
- [x] Training agent.
- [x] Nutrition agent.
- [x] Progress agent.
- [x] LangGraph orchestrator with SQLite checkpoints.
- [x] Prompts with per-agent RAG context.
- [x] `fitness` CLI with start, checkin, and status commands.
- [x] SQLite persistence with user and session repositories.

## v0.3 - Professional Outputs

- [ ] Export mesocycles to Excel.
- [ ] Export nutrition plans to PDF.
- [ ] Editable templates for coaches.
- [ ] Traceability of sources used in each recommendation.

## v0.4 - Public Demo

- [ ] Reproducible notebook.
- [ ] Web or local app demo.
- [ ] Small example dataset.
- [ ] Screenshots and short README video.

## v1.0 - Stable Technical Product

- [ ] Stable API.
- [ ] Schema versioning.
- [ ] End-to-end integration tests.
- [ ] Complete contributor documentation.
- [ ] Public release with changelog.
