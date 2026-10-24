import { Canvas } from '@react-three/fiber';
import { OrbitControls, Line } from '@react-three/drei';
import { useEffect, useMemo, useState } from 'react';
import { Color, SRGBColorSpace, TextureLoader, type Texture } from 'three';
import type { Station } from '../types';
import lines from '../data/lines.json';
type Line3={ref:string;mode:string;colour:string;segments:[number,number][][]};
const network=lines as Line3[];
// Equirectangular projection around Alexanderplatz; z is scaled by 1/cos(52.5°) to keep true proportions.
const project=([lon,lat]:[number,number]):[number,number,number]=>[(lon-13.4)*49,.1,-(lat-52.52)*80.6];
const point=(s:Station)=>project(s.coordinates!);
const GAP=.075;
// Scene colours per theme; lines keep their official colours in both.
const PALETTE={dark:{background:'#0a111b',grid:['#172c38','#12222c'],map:{tint:'#6f8796',opacity:.3},light:'#7abfb7',station:'#63d9c4',unknown:'#a99cc9',outage:'#ffb59e',marker:'#fd987c',noLift:'#f2c14e'},
 light:{background:'#eef2f6',grid:['#c9d3dc','#dbe2e9'],map:{tint:'#ffffff',opacity:.5},light:'#ffffff',station:'#0f9b82',unknown:'#7b66b0',outage:'#e0603e',marker:'#e0603e',noLift:'#c9920f'}};
const ink=(hex:string)=>{const c=new Color(hex);return .2126*c.r+.7152*c.g+.0722*c.b>.45?'#111':'#fff';};
// OpenStreetMap tiles (zoom 11) laid flat under the network at their true positions.
const ZOOM=11,TILES={x:[1097,1103],y:[669,674]};
const tileLon=(x:number)=>x/2**ZOOM*360-180,tileLat=(y:number)=>Math.atan(Math.sinh(Math.PI*(1-2*y/2**ZOOM)))*180/Math.PI;
function MapGround({tint,opacity}:{tint:string;opacity:number}){
 const [tiles,setTiles]=useState<{key:string;texture:Texture;position:[number,number,number];scale:[number,number,number]}[]>([]);
 useEffect(()=>{
  const loader=new TextureLoader(),loaded:Texture[]=[];let alive=true;
  for(let x=TILES.x[0];x<=TILES.x[1];x++)for(let y=TILES.y[0];y<=TILES.y[1];y++){
   const [x0,,z0]=project([tileLon(x),tileLat(y)]),[x1,,z1]=project([tileLon(x+1),tileLat(y+1)]);
   // A tile that fails to load is simply left out; the scene works without the map.
   loader.load(`https://tile.openstreetmap.org/${ZOOM}/${x}/${y}.png`,texture=>{texture.colorSpace=SRGBColorSpace;loaded.push(texture);if(alive)setTiles(t=>[...t,{key:`${x}/${y}`,texture,position:[(x0+x1)/2,-.14,(z0+z1)/2],scale:[x1-x0,z1-z0,1]}]);},undefined,()=>{});
  }
  return()=>{alive=false;loaded.forEach(t=>t.dispose());};
 },[]);
 return <>{tiles.map(t=><mesh key={t.key} position={t.position} rotation={[-Math.PI/2,0,0]} scale={t.scale}><planeGeometry/><meshBasicMaterial map={t.texture} color={tint} transparent opacity={opacity} depthWrite={false}/></mesh>)}</>;
}
function useTracks(){
 // Lines sharing a track are drawn side by side, like the BVG network map.
 return useMemo(()=>{const shared=new Map<string,string[]>();network.forEach(l=>l.segments.forEach(s=>{const k=s.flat().join();shared.set(k,[...(shared.get(k)??[]),l.ref]);}));
 return network.map(l=>({...l,points:l.segments.flatMap(([a,b])=>{const refs=shared.get([a,b].flat().join())!,i=refs.indexOf(l.ref),off=(i-(refs.length-1)/2)*GAP,p=project(a),q=project(b),dx=q[0]-p[0],dz=q[2]-p[2],len=Math.hypot(dx,dz)||1,ox=-dz/len*off,oz=dx/len*off;
 return [[p[0]+ox,.04,p[2]+oz],[q[0]+ox,.04,q[2]+oz]] as [number,number,number][];})}));},[]);
}
function Scene({stations,onSelect,reduced,onHover,focus,theme}:{stations:Station[];onSelect:(s:Station)=>void;reduced:boolean;onHover:(s:Station|null)=>void;focus:string|null;theme:'light'|'dark'}) {
 const c=PALETTE[theme];
 const plotted=useMemo(()=>stations.filter(s=>s.coordinates),[stations]);
 const tracks=useTracks();
 const {points,colors}=useMemo(()=>{const dim=(hex:string)=>new Color(hex).lerp(new Color(c.background),.9);
 return {points:tracks.flatMap(t=>t.points),colors:tracks.flatMap(t=>{const col=focus&&focus!==t.ref?dim(t.colour):new Color(t.colour);return t.points.map(()=>col);})};},[tracks,focus,c.background]);
 return <><color attach="background" args={[c.background]}/><fog attach="fog" args={[c.background,24,65]}/><ambientLight intensity={.8}/><directionalLight position={[6,12,8]} intensity={2} color={c.light}/>
 <MapGround tint={c.map.tint} opacity={c.map.opacity}/>
 <gridHelper key={theme} args={[70,70,c.grid[0],c.grid[1]]} position={[0,-.16,0]}/>
 <Line points={points} segments vertexColors={colors} lineWidth={2.4}/>
 {plotted.map(s=>{const p=point(s),active=s.outages>0;return <group key={s.id} position={p}>
 {active&&<><mesh position={[0,.65,0]}><cylinderGeometry args={[.013,.013,1.3,6]}/><meshBasicMaterial color={c.marker} transparent opacity={.75}/></mesh><mesh rotation={[-Math.PI/2,0,0]} position={[0,.015,0]}><ringGeometry args={[.18,.22,32]}/><meshBasicMaterial color={c.marker} transparent opacity={.6}/></mesh></>}
 <mesh position={[0,active?1.3:.06,0]} onClick={e=>{e.stopPropagation();onSelect(s);}} onPointerOver={e=>{e.stopPropagation();onHover(s);document.body.style.cursor='pointer';}} onPointerOut={()=>{onHover(null);document.body.style.cursor='auto';}}><sphereGeometry args={[active?.13:s.no_elevator?.11:.075,10,8]}/><meshBasicMaterial color={active?c.outage:s.no_elevator?c.noLift:s.unknown?c.unknown:c.station}/></mesh>
 </group>})}
 <OrbitControls makeDefault enablePan minDistance={8} maxDistance={45} maxPolarAngle={Math.PI/2.3} minPolarAngle={.15} autoRotate={!reduced} autoRotateSpeed={.12} enableDamping/>
 </>;
}
export default function Network({offlineLabel,legendLabel,...props}:{stations:Station[];onSelect:(s:Station)=>void;reset:number;reduced:boolean;theme:'light'|'dark';offlineLabel:(n:number)=>string;legendLabel:string}){
 const [hover,setHover]=useState<Station|null>(null),[focus,setFocus]=useState<string|null>(null);
 return <><Canvas key={props.reset} dpr={[1,1.5]} camera={{position:[3,19,19],fov:47}} gl={{antialias:true,alpha:false}} frameloop={props.reduced?'demand':'always'}><Scene {...props} onHover={setHover} focus={focus}/></Canvas>{hover&&<div className="scene-hover scene-label">{hover.name}<span>{offlineLabel(hover.outages)}</span></div>}
 <div className="line-legend" role="group" aria-label={legendLabel}>{network.map(l=><button key={l.ref} className={`line-chip ${l.mode==='S-Bahn'?'sbahn':''}`} style={{background:l.colour,color:ink(l.colour)}} aria-pressed={focus===l.ref} data-dim={focus!==null&&focus!==l.ref} onClick={()=>setFocus(focus===l.ref?null:l.ref)}>{l.ref}</button>)}</div></>;
}
