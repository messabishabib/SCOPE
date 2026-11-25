import {useState} from 'react'
import {BatteryCharging,Boxes,LayoutDashboard,Menu,Settings} from 'lucide-react'
import {CapacityWorkspace} from '../modules/capacity_planning/CapacityWorkspace'
import {EnergyWorkspace} from '../modules/energy_storage/EnergyWorkspace'
import {DecisionHub} from './DecisionHub'

type Module='home'|'capacity'|'energy'

const initialModule=():Module=>{
 const requested=new URLSearchParams(window.location.search).get('module')
 return requested==='capacity'||requested==='energy'?requested:'home'
}

export function App(){
 const [module,setModule]=useState<Module>(initialModule),[collapsed,setCollapsed]=useState(false)
 const selectModule=(next:Module)=>{
  setModule(next)
  const url=new URL(window.location.href)
  next==='home'?url.searchParams.delete('module'):url.searchParams.set('module',next)
  window.history.replaceState({},'',url)
 }
 const title=module==='capacity'?'Capacity Planning':module==='energy'?'Energy Storage':'Decision Hub'
 return <div className={`shell ${collapsed?'collapsed':''}`}><aside><div className="brand"><div className="mark">S</div><div><b>SCOPE</b><span>DECISION TOOLS</span></div></div><nav>
  <a className={module==='home'?'active':''} onClick={()=>selectModule('home')}><LayoutDashboard/><span>Decision Hub</span></a><div className="nav-divider"><span>OPTIMIZATION MODULES</span></div><a className={module==='capacity'?'active':''} onClick={()=>selectModule('capacity')}><Boxes/><span>Capacity Planning</span></a><a className={module==='energy'?'active':''} onClick={()=>selectModule('energy')}><BatteryCharging/><span>Energy Storage</span></a>
 </nav><div className="side-bottom"><a><Settings/><span>Settings</span></a><button aria-label="Collapse sidebar" onClick={()=>setCollapsed(!collapsed)}><Menu/></button></div></aside><main><header><div><small>SCOPE DECISION SUPPORT PLATFORM</small><h1>{title}</h1></div><div className="module-context"><span>{module==='home'?'Select a decision workflow':module==='capacity'?'Strategic & tactical planning':'Dynamic operational planning'}</span></div></header>
 <div className="content">{module==='home'?<DecisionHub openCapacity={()=>selectModule('capacity')} openEnergy={()=>selectModule('energy')}/>:module==='capacity'?<CapacityWorkspace/>:<EnergyWorkspace/>}</div></main></div>
}
