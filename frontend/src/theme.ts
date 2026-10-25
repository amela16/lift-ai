export type ThemeMode='system'|'light'|'dark'|'daytime';
export type Theme='light'|'dark';
export const THEME_MODES:ThemeMode[]=['system','light','dark','daytime'];

// Sunrise/sunset for Berlin (NOAA approximation, ±2 min). Keep in sync with the copy in index.html.
export function isBerlinDaytime(d=new Date()){
 const rad=Math.PI/180,lat=52.52,lon=13.405;
 const day=(Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),d.getUTCDate())-Date.UTC(d.getUTCFullYear(),0,0))/864e5;
 const g=2*Math.PI/365*(day-1+(d.getUTCHours()-12)/24);
 const eq=229.18*(.000075+.001868*Math.cos(g)-.032077*Math.sin(g)-.014615*Math.cos(2*g)-.040849*Math.sin(2*g));
 const decl=.006918-.399912*Math.cos(g)+.070257*Math.sin(g)-.006758*Math.cos(2*g)+.000907*Math.sin(2*g)-.002697*Math.cos(3*g)+.00148*Math.sin(3*g);
 const ha=Math.acos(Math.cos(90.833*rad)/(Math.cos(lat*rad)*Math.cos(decl))-Math.tan(lat*rad)*Math.tan(decl))/rad;
 const noon=720-4*lon-eq,now=d.getUTCHours()*60+d.getUTCMinutes();
 return now>=noon-4*ha&&now<noon+4*ha;
}
export const systemTheme=():Theme=>matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';
export function resolveTheme(mode:ThemeMode):Theme{
 return mode==='system'?systemTheme():mode==='daytime'?(isBerlinDaytime()?'light':'dark'):mode;
}
export function initialThemeMode():ThemeMode{
 try{const saved=localStorage.getItem('lift-theme');if(THEME_MODES.includes(saved as ThemeMode))return saved as ThemeMode;}catch{/* storage unavailable */}
 return 'system';
}
export function saveThemeMode(mode:ThemeMode){try{localStorage.setItem('lift-theme',mode);}catch{/* storage unavailable */}}
