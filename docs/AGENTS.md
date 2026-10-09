# Repository Instructions

Before implementing backend functionality, read:

1. `docs/PROJECT_BRIEF.md`
2. `docs/SYSTEM_ARCHITECTURE.md`
3. `docs/COMPONENT_RELATIONSHIPS.md`
4. `docs/BACKEND_COMPONENTS.md`
5. `docs/DATA_AND_API_CONTRACTS.md`
6. `docs/IMPLEMENTATION_ROADMAP.md`
7. `docs/COPILOT_INSTRUCTIONS.md`

Follow the architecture and implementation sequence. Inspect the existing repository and frontend contracts before coding. Use Supabase Auth for API identity, a Redis-backed Celery queue for asynchronous work, and S3-compatible object storage for durable model outputs, all behind provider adapters. Keep V1 user datasets at their external providers and download them only to temporary GPU-worker storage. Test a complete vertical slice before expanding.
