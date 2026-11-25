import type {Comparison,EnergyProject,EnergyRun,EnergySimulationRun,PlanningMode,Project,Run,Scenario} from '../types'
const json=async<T>(url:string,init?:RequestInit):Promise<T>=>{const r=await fetch(url,init);if(!r.ok)throw new Error(await r.text());return r.json()}
const send=(method:string,body:unknown):RequestInit=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
export const api={
 projects:()=>json<Project[]>('/api/projects'),
 updateProject:(project:Project)=>json<Project>(`/api/projects/${project.id}`,send('PUT',project)),
 run:(id:string,scenario_id:string|null,mode:PlanningMode='deterministic')=>json<Run>(`/api/projects/${id}/runs`,send('POST',{mode,scenario_id:mode==='deterministic'?scenario_id:null})),
 getRun:(id:string)=>json<Run>(`/api/runs/${id}`),
 runs:(id:string)=>json<Run[]>(`/api/projects/${id}/runs`),
 duplicateScenario:(projectId:string,scenarioId:string,name:string)=>json<Scenario>(`/api/projects/${projectId}/scenarios/${scenarioId}/duplicate`,send('POST',{name})),
 updateScenario:(projectId:string,scenario:Scenario)=>json<Scenario>(`/api/projects/${projectId}/scenarios/${scenario.id}`,send('PUT',scenario)),
 compare:(baseline:string,candidate:string)=>json<Comparison>(`/api/runs/compare/${baseline}/${candidate}`)
 ,energyProjects:()=>json<EnergyProject[]>('/api/energy/projects')
 ,runEnergy:(id:string,request:{mode:'deterministic'|'stochastic';current_period:number;current_energy_mwh_by_storage:Record<string,number>;lookahead_periods:number;commitment_periods:number})=>json<EnergyRun>(`/api/energy/projects/${id}/runs`,send('POST',{time_limit_seconds:60,...request}))
 ,getEnergyRun:(id:string)=>json<EnergyRun>(`/api/energy/runs/${id}`)
 ,simulateEnergy:(id:string,request:{policies:('deterministic'|'stochastic')[];realized_scenario_id:string|null;start_period:number;horizon_periods:number;current_energy_mwh_by_storage:Record<string,number>;lookahead_periods:number;commitment_periods:number})=>json<EnergySimulationRun>(`/api/energy/projects/${id}/simulations`,send('POST',{time_limit_seconds:30,...request}))
 ,getEnergySimulation:(id:string)=>json<EnergySimulationRun>(`/api/energy/simulations/${id}`)
}

