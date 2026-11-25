# Architecture

The frontend communicates only through the REST API. FastAPI validates business objects before the repository stores their complete JSON snapshots in SQLite. Optimization runs are persisted before a local worker thread builds a Pyomo model. The solver result is interpreted into business-facing allocations, capacities, costs, service metrics, and recommendations, then persisted on the run.

Each decision domain owns its API, validated schemas, optimization formulations, application services, and persistence records under `app/modules/<module>`. Solvers have no frontend or database dependency. New capacity-planning engines implement the validated-project-to-result boundary under `app/modules/capacity_planning/optimization`; energy engines follow the equivalent boundary under `app/modules/energy_storage/optimization`.

Platform code is intentionally small: `app/core` owns cross-module utilities and health routes, `app/database` owns the shared SQLAlchemy session and metadata, and `app/main.py` composes routers and demo initialization. Modules may depend on this shared infrastructure but should not import implementation details from another decision module.

The frontend mirrors those boundaries. `src/app` contains the shell and Decision Hub, `src/modules` contains independent decision workspaces, and `src/shared` contains only reusable components, API access, and transport types.

