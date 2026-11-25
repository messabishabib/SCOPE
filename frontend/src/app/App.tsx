import {useState} from 'react'
import {BatteryCharging,Boxes,LayoutDashboard,Menu,Settings} from 'lucide-react'
import {CapacityWorkspace} from '../modules/capacity_planning/CapacityWorkspace'
import {EnergyWorkspace} from '../modules/energy_storage/EnergyWorkspace'
import {DecisionHub} from './DecisionHub'

type Module='home'|'capacity'|'energy'

export function App(){
 const [module,setModule]=useState<Module>('home'),[collapsed,setCollapsed]=useState(false)
 const title=module==='capacity'?'Capacity Planning':module==='energy'?'Energy Storage':'Decision Hub'
 return <div className={`shell ${collapsed?'collapsed':''}`}><aside><div className="brand"><div className="mark">S</div><div><b>SCOPE</b><span>DECISION TOOLS</span></div></div><nav>
  <a className={module==='home'?'active':''} onClick={()=>setModule('home')}><LayoutDashboard/><span>Decision Hub</span></a><div className="nav-divider"><span>OPTIMIZATION MODULES</span></div><a className={module==='capacity'?'active':''} onClick={()=>setModule('capacity')}><Boxes/><span>Capacity Planning</span></a><a className={module==='energy'?'active':''} onClick={()=>setModule('energy')}><BatteryCharging/><span>Energy Storage</span></a>
 </nav><div className="side-bottom"><a><Settings/><span>Settings</span></a><button aria-label="Collapse sidebar" onClick={()=>setCollapsed(!collapsed)}><Menu/></button></div></aside><main><header><div><small>SCOPE DECISION SUPPORT PLATFORM</small><h1>{title}</h1></div><div className="module-context"><span>{module==='home'?'Select a decision workflow':module==='capacity'?'Strategic & tactical planning':'Dynamic operational planning'}</span></div></header>
 <div className="content">{module==='home'?<DecisionHub openCapacity={()=>setModule('capacity')} openEnergy={()=>setModule('energy')}/>:module==='capacity'?<CapacityWorkspace/>:<EnergyWorkspace/>}</div></main></div>
}
