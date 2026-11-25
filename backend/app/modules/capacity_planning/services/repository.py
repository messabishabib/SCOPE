from sqlalchemy import select

from ....database.session import SessionLocal
from ..persistence.models import ProjectRecord, RunRecord
from ..schemas import OptimizationRun, Project


class Repository:
    def save_project(self, project: Project) -> Project:
        with SessionLocal() as db:
            record = db.get(ProjectRecord, project.id)
            payload = project.model_dump_json()
            if record:
                record.name, record.payload = project.name, payload
            else:
                db.add(ProjectRecord(id=project.id, name=project.name, payload=payload, created_at=project.created_at))
            db.commit()
        return project

    def list_projects(self) -> list[Project]:
        with SessionLocal() as db:
            return [Project.model_validate_json(r.payload) for r in db.scalars(select(ProjectRecord).order_by(ProjectRecord.created_at)).all()]

    def get_project(self, project_id: str) -> Project | None:
        with SessionLocal() as db:
            r = db.get(ProjectRecord, project_id)
            return Project.model_validate_json(r.payload) if r else None

    def save_run(self, run: OptimizationRun) -> OptimizationRun:
        with SessionLocal() as db:
            record = db.get(RunRecord, run.id)
            payload = run.model_dump_json()
            if record:
                record.status, record.payload = run.status, payload
            else:
                db.add(RunRecord(id=run.id, project_id=run.project_id, status=run.status, payload=payload, created_at=run.created_at))
            db.commit()
        return run

    def get_run(self, run_id: str) -> OptimizationRun | None:
        with SessionLocal() as db:
            r = db.get(RunRecord, run_id)
            return OptimizationRun.model_validate_json(r.payload) if r else None

    def list_runs(self, project_id: str) -> list[OptimizationRun]:
        with SessionLocal() as db:
            rows = db.scalars(select(RunRecord).where(RunRecord.project_id == project_id).order_by(RunRecord.created_at.desc())).all()
            return [OptimizationRun.model_validate_json(x.payload) for x in rows]


repository = Repository()

