import {useEffect,useMemo,useRef,useState} from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import {Search,X} from 'lucide-react';
import type {Station} from '../types';
export type MapLabels={station:(s:Station)=>string;tilesFailed:string;search:string;noResults:string;clear:string};
const fold=(s:string)=>s.toLowerCase().replace(/ß/g,'ss').replace(/strasse/g,'str').normalize('NFKD').replace(/[^a-z0-9]/g,'');
export default function BerlinMap({stations,onSelect,labels}:{stations:Station[];onSelect:(s:Station)=>void;labels:MapLabels}){
 const ref=useRef<HTMLDivElement>(null), select=useRef(onSelect),label=useRef(labels);select.current=onSelect;label.current=labels;
 const mapRef=useRef<maplibregl.Map|null>(null),markers=useRef(new Map<number,HTMLElement>()),popup=useRef<maplibregl.Popup|null>(null);
 const [failed,setFailed]=useState(false),[query,setQuery]=useState(''),[open,setOpen]=useState(false),[active,setActive]=useState(0);
 const located=useMemo(()=>stations.filter(s=>s.coordinates),[stations]);
 const results=useMemo(()=>{const q=fold(query);return q?located.filter(s=>fold(s.name).includes(q)).sort((a,b)=>fold(a.name).indexOf(q)-fold(b.name).indexOf(q)).slice(0,6):[];},[query,located]);
 useEffect(()=>{
 if(!ref.current)return;
 const map=new maplibregl.Map({container:ref.current,center:[13.405,52.52],zoom:10.4,style:{version:8,sources:{osm:{type:'raster',tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors',maxzoom:19}},layers:[{id:'osm',type:'raster',source:'osm',paint:{'raster-saturation':-1}}]}});
 mapRef.current=map;
 map.addControl(new maplibregl.NavigationControl(),'bottom-right');
 map.on('error',()=>setFailed(true));
 const added=located.map(s=>{const el=document.createElement('button');el.className=`map-dot ${s.outages?'outage':s.unknown?'unknown':''} ${s.no_elevator?'no-lift':''}`;el.setAttribute('aria-label',label.current.station(s));el.title=label.current.station(s);el.onclick=()=>select.current(s);markers.current.set(s.id,el);return new maplibregl.Marker({element:el}).setLngLat(s.coordinates!).addTo(map);});
 return()=>{added.forEach(m=>m.remove());markers.current.clear();popup.current?.remove();map.remove();mapRef.current=null;};
 },[located,labels.tilesFailed]);
 const focus=(s:Station)=>{
  const map=mapRef.current;if(!map||!s.coordinates)return;
  markers.current.forEach(el=>el.classList.remove('focused'));markers.current.get(s.id)?.classList.add('focused');
  popup.current?.remove();
  popup.current=new maplibregl.Popup({closeButton:false,offset:14,className:'map-popup'}).setLngLat(s.coordinates).setText(label.current.station(s)).addTo(map);
  map.flyTo({center:s.coordinates,zoom:Math.max(map.getZoom(),14.5),essential:true});
  setQuery(s.name);setOpen(false);
 };
 const onKey=(e:React.KeyboardEvent)=>{
  if(e.key==='ArrowDown'){e.preventDefault();setOpen(true);setActive(a=>Math.min(a+1,results.length-1));}
  else if(e.key==='ArrowUp'){e.preventDefault();setActive(a=>Math.max(a-1,0));}
  else if(e.key==='Enter'&&results[active]){e.preventDefault();focus(results[active]);}
  else if(e.key==='Escape')setOpen(false);
 };
 return <><div ref={ref} className="map-container"/>
 <div className="map-search" role="combobox" aria-expanded={open&&results.length>0} aria-haspopup="listbox" aria-owns="map-search-results">
  <Search size={14}/><input aria-label={labels.search} placeholder={labels.search} value={query} onChange={e=>{setQuery(e.target.value);setActive(0);setOpen(true);}} onFocus={()=>setOpen(true)} onBlur={()=>setTimeout(()=>setOpen(false),150)} onKeyDown={onKey} aria-autocomplete="list" aria-controls="map-search-results" aria-activedescendant={open&&results[active]?`map-result-${results[active].id}`:undefined}/>
  {query&&<button aria-label={labels.clear} onClick={()=>{setQuery('');popup.current?.remove();markers.current.forEach(el=>el.classList.remove('focused'));}}><X size={13}/></button>}
  {open&&query&&<ul id="map-search-results" role="listbox">{results.map((s,i)=><li key={s.id} id={`map-result-${s.id}`} role="option" aria-selected={i===active} onMouseDown={e=>{e.preventDefault();focus(s);}}><i className={`map-dot ${s.outages?'outage':s.unknown?'unknown':''} ${s.no_elevator?'no-lift':''}`}/>{s.name}<small>{s.modes.join(' · ')}</small></li>)}{!results.length&&<li className="none">{labels.noResults}</li>}</ul>}
 </div>
 {failed&&<div className="map-warning">{labels.tilesFailed}</div>}</>;
}
