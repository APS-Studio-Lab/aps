const clamp=(x)=>Math.max(0,Math.min(1,x));
const seg=(t,a,b)=>clamp((t-a)/(b-a));
const eOut=(x)=>1-Math.pow(1-x,3);
const eInOut=(x)=>x<.5?4*x*x*x:1-Math.pow(-2*x+2,3)/2;
const eBack=(x)=>{const c1=1.70158,c3=c1+1;return 1+c3*Math.pow(x-1,3)+c1*Math.pow(x-1,2)};
const $=(id)=>document.getElementById(id);
function show(el,p,dy=40){el.style.opacity=p;el.style.transform=`translateY(${(1-p)*dy}px)`}
