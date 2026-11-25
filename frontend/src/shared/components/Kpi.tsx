import type {ReactNode} from 'react'

export function Kpi({label,value,detail,icon}:{label:string;value:string;detail:string;icon:ReactNode}){return <div className="kpi"><div className="kpi-icon">{icon}</div><div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div></div>}

