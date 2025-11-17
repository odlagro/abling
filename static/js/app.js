
document.addEventListener('click',e=>{
  const b=e.target.closest('.toggle');if(!b)return;
  const id=b.getAttribute('data-target');const el=document.querySelector(id);
  if(el){el.hidden=!el.hidden;}
});
// Auto refresh a cada 60s (apenas quando a aba está visível)
const REFRESH_MS = 60000;
let timer = setInterval(()=>{ if(!document.hidden){ location.reload(); } }, REFRESH_MS);
