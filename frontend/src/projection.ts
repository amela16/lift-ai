// Equirectangular projection around Alexanderplatz; y is scaled by 1/cos(52.5°) to keep true proportions.
export const planar=([lon,lat]:[number,number]):[number,number]=>[(lon-13.4)*49,-(lat-52.52)*80.6];
export function supportsWebGL(){
 try{const canvas=document.createElement('canvas');return !!(canvas.getContext('webgl2')||canvas.getContext('webgl'));}catch{return false;}
}
