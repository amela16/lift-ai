import {useMemo} from 'react';
import type {Station} from '../types';
import lines from '../data/lines.json';
import {planar} from '../projection';
type Line2={ref:string;mode:string;colour:string;segments:[number,number][][]};
const network=lines as Line2[];
// Plain SVG version of the 3D network for browsers without WebGL; same lines, stations and colours.
export default function Network2D({stations,onSelect,label,note,stationLabel}:{stations:Station[];onSelect:(s:Station)=>void;label:string;note:string;stationLabel:(s:Station)=>string}){
 const box=useMemo(()=>{const pts=network.flatMap(l=>l.segments.flat().map(planar)),xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);
  return [Math.min(...xs)-1,Math.min(...ys)-1,Math.max(...xs)-Math.min(...xs)+2,Math.max(...ys)-Math.min(...ys)+2].join(' ');},[]);
 return <div className="network-2d">
  <svg viewBox={box} role="img" aria-label={label} preserveAspectRatio="xMidYMid meet">
   {network.flatMap(l=>l.segments.map(([a,b],i)=>{const [x1,y1]=planar(a),[x2,y2]=planar(b);return <line key={`${l.ref}-${i}`} x1={x1} y1={y1} x2={x2} y2={y2} stroke={l.colour} strokeWidth={.3} strokeLinecap="round"/>;}))}
   {stations.filter(s=>s.coordinates).map(s=>{const [x,y]=planar(s.coordinates!);return <circle key={s.id} cx={x} cy={y} r={s.outages?.42:s.no_elevator?.36:.24} className={s.outages?'outage':s.no_elevator?'no-lift':s.unknown?'unknown':''} onClick={()=>onSelect(s)}><title>{stationLabel(s)}</title></circle>;})}
  </svg>
  <p className="network-2d-note">{note}</p>
 </div>;
}
