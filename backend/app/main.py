from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.api import router as platform_router
from .database.session import init_db
from .modules.capacity_planning.api.routes import router as capacity_router
from .modules.capacity_planning.services.demo import demo_projects
from .modules.capacity_planning.services.repository import repository
from .modules.energy_storage.api.routes import router as energy_router
from .modules.energy_storage.services.demo import energy_demo_project
from .modules.energy_storage.services.repository import energy_repository


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if not repository.list_projects():
        for project in demo_projects():
            repository.save_project(project)
    energy_projects = energy_repository.list_projects()
    demo_energy = next((p for p in energy_projects if p.id == "demo-pumped-hydro"), None)
    if not energy_projects or (demo_energy and not demo_energy.scenarios):
        energy_repository.save_project(energy_demo_project())
    yield


app = FastAPI(title="SCOPE Decision Support API", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(platform_router)
app.include_router(capacity_router)
app.include_router(energy_router)

