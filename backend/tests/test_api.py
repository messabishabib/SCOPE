import time

from fastapi.testclient import TestClient

from app.main import app


def test_platform_health_route_remains_available():
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_demo_project_optimization_workflow():
    with TestClient(app) as client:
        projects = client.get("/api/projects")
        assert projects.status_code == 200
        project = next(p for p in projects.json() if p["id"] == "demo-manufacturing")
        response = client.post(f"/api/projects/{project['id']}/runs", json={"mode": "deterministic", "scenario_id": "baseline", "time_limit_seconds": 20})
        assert response.status_code == 202
        run_id = response.json()["id"]
        run = None
        for _ in range(50):
            run = client.get(f"/api/runs/{run_id}").json()
            if run["status"] not in {"queued", "running"}:
                break
            time.sleep(.05)
        assert run["status"] == "optimal"
        assert run["result"]["diagnostics"]["solution_validated"] is True
        exported = client.get(f"/api/runs/{run_id}/export.csv")
        assert exported.status_code == 200
        assert exported.text.startswith("resource_id,demand_id,period")


def test_scenario_duplicate_update_and_run_comparison():
    with TestClient(app) as client:
        project = next(p for p in client.get("/api/projects").json() if p["id"] == "demo-distribution")
        duplicated = client.post(f"/api/projects/{project['id']}/scenarios/baseline/duplicate", json={"name": "Stress test"})
        assert duplicated.status_code == 201
        scenario = duplicated.json()
        scenario["demand_multiplier"] = 1.15
        updated = client.put(f"/api/projects/{project['id']}/scenarios/{scenario['id']}", json=scenario)
        assert updated.status_code == 200

        run_ids = []
        for scenario_id in ["baseline", scenario["id"]]:
            response = client.post(f"/api/projects/{project['id']}/runs", json={"mode": "deterministic", "scenario_id": scenario_id})
            run_id = response.json()["id"]
            for _ in range(60):
                run = client.get(f"/api/runs/{run_id}").json()
                if run["status"] not in {"queued", "running"}:
                    break
                time.sleep(.05)
            assert run["status"] == "optimal"
            run_ids.append(run_id)
        comparison = client.get(f"/api/runs/compare/{run_ids[0]}/{run_ids[1]}")
        assert comparison.status_code == 200
        assert comparison.json()["total_cost_change"] > 0


def test_expected_plan_api_uses_all_scenarios():
    with TestClient(app) as client:
        project = next(p for p in client.get("/api/projects").json() if p["id"] == "demo-manufacturing")
        response = client.post(f"/api/projects/{project['id']}/runs", json={"mode": "expected", "scenario_id": None})
        assert response.status_code == 202
        run_id = response.json()["id"]
        for _ in range(80):
            run = client.get(f"/api/runs/{run_id}").json()
            if run["status"] not in {"queued", "running"}:
                break
            time.sleep(.05)
        assert run["status"] == "optimal"
        assert len(run["result"]["scenario_performance"]) == len(project["scenarios"])
        assert run["result"]["diagnostics"]["objective_basis"] == "expected"
