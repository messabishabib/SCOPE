from sqlalchemy import select

from ....database.session import SessionLocal
from ..persistence.models import EnergyProjectRecord, EnergyRunRecord, EnergySimulationRecord
from ..schemas import EnergyOptimizationRun, EnergyProject, EnergySimulationRun


class EnergyRepository:
    def save_project(self, project: EnergyProject) -> EnergyProject:
        with SessionLocal() as db:
            record = db.get(EnergyProjectRecord, project.id)
            if record:
                record.name, record.payload = project.name, project.model_dump_json()
            else:
                db.add(EnergyProjectRecord(id=project.id, name=project.name, payload=project.model_dump_json(), created_at=project.created_at))
            db.commit()
        return project

    def list_projects(self) -> list[EnergyProject]:
        with SessionLocal() as db:
            rows = db.scalars(select(EnergyProjectRecord).order_by(EnergyProjectRecord.created_at)).all()
            return [EnergyProject.model_validate_json(x.payload) for x in rows]

    def get_project(self, project_id: str) -> EnergyProject | None:
        with SessionLocal() as db:
            row = db.get(EnergyProjectRecord, project_id)
            return EnergyProject.model_validate_json(row.payload) if row else None

    def save_run(self, run: EnergyOptimizationRun) -> EnergyOptimizationRun:
        with SessionLocal() as db:
            record = db.get(EnergyRunRecord, run.id)
            if record:
                record.status, record.payload = run.status, run.model_dump_json()
            else:
                db.add(EnergyRunRecord(id=run.id, project_id=run.project_id, status=run.status, payload=run.model_dump_json(), created_at=run.created_at))
            db.commit()
        return run

    def get_run(self, run_id: str) -> EnergyOptimizationRun | None:
        with SessionLocal() as db:
            row = db.get(EnergyRunRecord, run_id)
            return EnergyOptimizationRun.model_validate_json(row.payload) if row else None

    def save_simulation(self, run: EnergySimulationRun) -> EnergySimulationRun:
        with SessionLocal() as db:
            record = db.get(EnergySimulationRecord, run.id)
            if record:
                record.status, record.payload = run.status, run.model_dump_json()
            else:
                db.add(EnergySimulationRecord(id=run.id, project_id=run.project_id, status=run.status, payload=run.model_dump_json(), created_at=run.created_at))
            db.commit()
        return run

    def get_simulation(self, run_id: str) -> EnergySimulationRun | None:
        with SessionLocal() as db:
            row = db.get(EnergySimulationRecord, run_id)
            return EnergySimulationRun.model_validate_json(row.payload) if row else None


energy_repository = EnergyRepository()

