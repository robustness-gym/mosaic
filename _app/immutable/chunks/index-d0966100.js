function b(){}const ft=t=>t;function _t(t,e){for(const n in e)t[n]=e[n];return t}function dt(t){return!!t&&(typeof t=="object"||typeof t=="function")&&typeof t.then=="function"}function V(t){return t()}function K(){return Object.create(null)}function k(t){t.forEach(V)}function P(t){return typeof t=="function"}function It(t,e){return t!=t?e==e:t!==e||t&&typeof t=="object"||typeof t=="function"}let C;function Wt(t,e){return C||(C=document.createElement("a")),C.href=e,t===C.href}function ht(t){return Object.keys(t).length===0}function X(t,...e){if(t==null)return b;const n=t.subscribe(...e);return n.unsubscribe?()=>n.unsubscribe():n}function Gt(t){let e;return X(t,n=>e=n)(),e}function Jt(t,e,n){t.$$.on_destroy.push(X(e,n))}function Kt(t,e,n,r){if(t){const i=Y(t,e,n,r);return t[0](i)}}function Y(t,e,n,r){return t[1]&&r?_t(n.ctx.slice(),t[1](r(e))):n.ctx}function Qt(t,e,n,r){if(t[2]&&r){const i=t[2](r(n));if(e.dirty===void 0)return i;if(typeof i=="object"){const l=[],s=Math.max(e.dirty.length,i.length);for(let o=0;o<s;o+=1)l[o]=e.dirty[o]|i[o];return l}return e.dirty|i}return e.dirty}function Ut(t,e,n,r,i,l){if(i){const s=Y(e,n,r,l);t.p(s,i)}}function Vt(t){if(t.ctx.length>32){const e=[],n=t.ctx.length/32;for(let r=0;r<n;r++)e[r]=-1;return e}return-1}function Xt(t){const e={};for(const n in t)n[0]!=="$"&&(e[n]=t[n]);return e}function Yt(t,e){const n={};e=new Set(e);for(const r in t)!e.has(r)&&r[0]!=="$"&&(n[r]=t[r]);return n}function Zt(t){const e={};for(const n in t)e[n]=!0;return e}function te(t){return t&&P(t.destroy)?t.destroy:b}const Z=typeof window<"u";let mt=Z?()=>window.performance.now():()=>Date.now(),I=Z?t=>requestAnimationFrame(t):b;const v=new Set;function tt(t){v.forEach(e=>{e.c(t)||(v.delete(e),e.f())}),v.size!==0&&I(tt)}function pt(t){let e;return v.size===0&&I(tt),{promise:new Promise(n=>{v.add(e={c:t,f:n})}),abort(){v.delete(e)}}}let q=!1;function yt(){q=!0}function gt(){q=!1}function bt(t,e,n,r){for(;t<e;){const i=t+(e-t>>1);n(i)<=r?t=i+1:e=i}return t}function $t(t){if(t.hydrate_init)return;t.hydrate_init=!0;let e=t.childNodes;if(t.nodeName==="HEAD"){const c=[];for(let u=0;u<e.length;u++){const f=e[u];f.claim_order!==void 0&&c.push(f)}e=c}const n=new Int32Array(e.length+1),r=new Int32Array(e.length);n[0]=-1;let i=0;for(let c=0;c<e.length;c++){const u=e[c].claim_order,f=(i>0&&e[n[i]].claim_order<=u?i+1:bt(1,i,d=>e[n[d]].claim_order,u))-1;r[c]=n[f]+1;const a=f+1;n[a]=c,i=Math.max(a,i)}const l=[],s=[];let o=e.length-1;for(let c=n[i]+1;c!=0;c=r[c-1]){for(l.push(e[c-1]);o>=c;o--)s.push(e[o]);o--}for(;o>=0;o--)s.push(e[o]);l.reverse(),s.sort((c,u)=>c.claim_order-u.claim_order);for(let c=0,u=0;c<s.length;c++){for(;u<l.length&&s[c].claim_order>=l[u].claim_order;)u++;const f=u<l.length?l[u]:null;t.insertBefore(s[c],f)}}function xt(t,e){t.appendChild(e)}function et(t){if(!t)return document;const e=t.getRootNode?t.getRootNode():t.ownerDocument;return e&&e.host?e:t.ownerDocument}function wt(t){const e=rt("style");return vt(et(t),e),e.sheet}function vt(t,e){return xt(t.head||t,e),e.sheet}function kt(t,e){if(q){for($t(t),(t.actual_end_child===void 0||t.actual_end_child!==null&&t.actual_end_child.parentNode!==t)&&(t.actual_end_child=t.firstChild);t.actual_end_child!==null&&t.actual_end_child.claim_order===void 0;)t.actual_end_child=t.actual_end_child.nextSibling;e!==t.actual_end_child?(e.claim_order!==void 0||e.parentNode!==t)&&t.insertBefore(e,t.actual_end_child):t.actual_end_child=e.nextSibling}else(e.parentNode!==t||e.nextSibling!==null)&&t.appendChild(e)}function ee(t,e,n){q&&!n?kt(t,e):(e.parentNode!==t||e.nextSibling!=n)&&t.insertBefore(e,n||null)}function nt(t){t.parentNode&&t.parentNode.removeChild(t)}function ne(t,e){for(let n=0;n<t.length;n+=1)t[n]&&t[n].d(e)}function rt(t){return document.createElement(t)}function Et(t){return document.createElementNS("http://www.w3.org/2000/svg",t)}function W(t){return document.createTextNode(t)}function re(){return W(" ")}function ie(){return W("")}function se(t,e,n,r){return t.addEventListener(e,n,r),()=>t.removeEventListener(e,n,r)}function G(t,e,n){n==null?t.removeAttribute(e):t.getAttribute(e)!==n&&t.setAttribute(e,n)}function ce(t,e){const n=Object.getOwnPropertyDescriptors(t.__proto__);for(const r in e)e[r]==null?t.removeAttribute(r):r==="style"?t.style.cssText=e[r]:r==="__value"?t.value=t[r]=e[r]:n[r]&&n[r].set?t[r]=e[r]:G(t,r,e[r])}function oe(t,e){for(const n in e)G(t,n,e[n])}function le(t,e){Object.keys(e).forEach(n=>{Nt(t,n,e[n])})}function Nt(t,e,n){e in t?t[e]=typeof t[e]=="boolean"&&n===""?!0:n:G(t,e,n)}function ue(t){return t===""?null:+t}function At(t){return Array.from(t.childNodes)}function jt(t){t.claim_info===void 0&&(t.claim_info={last_index:0,total_claimed:0})}function it(t,e,n,r,i=!1){jt(t);const l=(()=>{for(let s=t.claim_info.last_index;s<t.length;s++){const o=t[s];if(e(o)){const c=n(o);return c===void 0?t.splice(s,1):t[s]=c,i||(t.claim_info.last_index=s),o}}for(let s=t.claim_info.last_index-1;s>=0;s--){const o=t[s];if(e(o)){const c=n(o);return c===void 0?t.splice(s,1):t[s]=c,i?c===void 0&&t.claim_info.last_index--:t.claim_info.last_index=s,o}}return r()})();return l.claim_order=t.claim_info.total_claimed,t.claim_info.total_claimed+=1,l}function st(t,e,n,r){return it(t,i=>i.nodeName===e,i=>{const l=[];for(let s=0;s<i.attributes.length;s++){const o=i.attributes[s];n[o.name]||l.push(o.name)}l.forEach(s=>i.removeAttribute(s))},()=>r(e))}function ae(t,e,n){return st(t,e,n,rt)}function fe(t,e,n){return st(t,e,n,Et)}function Ct(t,e){return it(t,n=>n.nodeType===3,n=>{const r=""+e;if(n.data.startsWith(r)){if(n.data.length!==r.length)return n.splitText(r.length)}else n.data=r},()=>W(e),!0)}function _e(t){return Ct(t," ")}function de(t,e){e=""+e,t.wholeText!==e&&(t.data=e)}function he(t,e){t.value=e??""}function me(t,e,n,r){n===null?t.style.removeProperty(e):t.style.setProperty(e,n,r?"important":"")}function pe(t,e){for(let n=0;n<t.options.length;n+=1){const r=t.options[n];if(r.__value===e){r.selected=!0;return}}t.selectedIndex=-1}function ye(t){const e=t.querySelector(":checked")||t.options[0];return e&&e.__value}function ge(t,e,n){t.classList[n?"add":"remove"](e)}function ct(t,e,{bubbles:n=!1,cancelable:r=!1}={}){const i=document.createEvent("CustomEvent");return i.initCustomEvent(t,n,r,e),i}function be(t,e){const n=[];let r=0;for(const i of e.childNodes)if(i.nodeType===8){const l=i.textContent.trim();l===`HEAD_${t}_END`?(r-=1,n.push(i)):l===`HEAD_${t}_START`&&(r+=1,n.push(i))}else r>0&&n.push(i);return n}function $e(t,e){return new t(e)}const O=new Map;let T=0;function St(t){let e=5381,n=t.length;for(;n--;)e=(e<<5)-e^t.charCodeAt(n);return e>>>0}function Dt(t,e){const n={stylesheet:wt(e),rules:{}};return O.set(t,n),n}function Q(t,e,n,r,i,l,s,o=0){const c=16.666/r;let u=`{
`;for(let g=0;g<=1;g+=c){const $=e+(n-e)*l(g);u+=g*100+`%{${s($,1-$)}}
`}const f=u+`100% {${s(n,1-n)}}
}`,a=`__svelte_${St(f)}_${o}`,d=et(t),{stylesheet:_,rules:h}=O.get(d)||Dt(d,t);h[a]||(h[a]=!0,_.insertRule(`@keyframes ${a} ${f}`,_.cssRules.length));const m=t.style.animation||"";return t.style.animation=`${m?`${m}, `:""}${a} ${r}ms linear ${i}ms 1 both`,T+=1,a}function Ot(t,e){const n=(t.style.animation||"").split(", "),r=n.filter(e?l=>l.indexOf(e)<0:l=>l.indexOf("__svelte")===-1),i=n.length-r.length;i&&(t.style.animation=r.join(", "),T-=i,T||Tt())}function Tt(){I(()=>{T||(O.forEach(t=>{const{ownerNode:e}=t.stylesheet;e&&nt(e)}),O.clear())})}let A;function p(t){A=t}function E(){if(!A)throw new Error("Function called outside component initialization");return A}function xe(t){E().$$.on_mount.push(t)}function we(t){E().$$.after_update.push(t)}function ve(){const t=E();return(e,n,{cancelable:r=!1}={})=>{const i=t.$$.callbacks[e];if(i){const l=ct(e,n,{cancelable:r});return i.slice().forEach(s=>{s.call(t,l)}),!l.defaultPrevented}return!0}}function ke(t,e){return E().$$.context.set(t,e),e}function Ee(t){return E().$$.context.get(t)}function Ne(t,e){const n=t.$$.callbacks[e.type];n&&n.slice().forEach(r=>r.call(this,e))}const w=[],U=[],S=[],H=[],ot=Promise.resolve();let F=!1;function lt(){F||(F=!0,ot.then(J))}function Ae(){return lt(),ot}function M(t){S.push(t)}function je(t){H.push(t)}const z=new Set;let x=0;function J(){if(x!==0)return;const t=A;do{try{for(;x<w.length;){const e=w[x];x++,p(e),Mt(e.$$)}}catch(e){throw w.length=0,x=0,e}for(p(null),w.length=0,x=0;U.length;)U.pop()();for(let e=0;e<S.length;e+=1){const n=S[e];z.has(n)||(z.add(n),n())}S.length=0}while(w.length);for(;H.length;)H.pop()();F=!1,z.clear(),p(t)}function Mt(t){if(t.fragment!==null){t.update(),k(t.before_update);const e=t.dirty;t.dirty=[-1],t.fragment&&t.fragment.p(t.ctx,e),t.after_update.forEach(M)}}let N;function Pt(){return N||(N=Promise.resolve(),N.then(()=>{N=null})),N}function B(t,e,n){t.dispatchEvent(ct(`${e?"intro":"outro"}${n}`))}const D=new Set;let y;function qt(){y={r:0,c:[],p:y}}function Rt(){y.r||k(y.c),y=y.p}function ut(t,e){t&&t.i&&(D.delete(t),t.i(e))}function Lt(t,e,n,r){if(t&&t.o){if(D.has(t))return;D.add(t),y.c.push(()=>{D.delete(t),r&&(n&&t.d(1),r())}),t.o(e)}else r&&r()}const zt={duration:0};function Ce(t,e,n,r){const i={direction:"both"};let l=e(t,n,i),s=r?0:1,o=null,c=null,u=null;function f(){u&&Ot(t,u)}function a(_,h){const m=_.b-s;return h*=Math.abs(m),{a:s,b:_.b,d:m,duration:h,start:_.start,end:_.start+h,group:_.group}}function d(_){const{delay:h=0,duration:m=300,easing:g=ft,tick:$=b,css:R}=l||zt,L={start:mt()+h,b:_};_||(L.group=y,y.r+=1),o||c?c=L:(R&&(f(),u=Q(t,s,_,m,h,g,R)),_&&$(0,1),o=a(L,m),M(()=>B(t,_,"start")),pt(j=>{if(c&&j>c.start&&(o=a(c,m),c=null,B(t,o.b,"start"),R&&(f(),u=Q(t,s,o.b,o.duration,0,g,l.css))),o){if(j>=o.end)$(s=o.b,1-s),B(t,o.b,"end"),c||(o.b?f():--o.group.r||k(o.group.c)),o=null;else if(j>=o.start){const at=j-o.start;s=o.a+o.d*g(at/o.duration),$(s,1-s)}}return!!(o||c)}))}return{run(_){P(l)?Pt().then(()=>{l=l(i),d(_)}):d(_)},end(){f(),o=c=null}}}function Se(t,e){const n=e.token={};function r(i,l,s,o){if(e.token!==n)return;e.resolved=o;let c=e.ctx;s!==void 0&&(c=c.slice(),c[s]=o);const u=i&&(e.current=i)(c);let f=!1;e.block&&(e.blocks?e.blocks.forEach((a,d)=>{d!==l&&a&&(qt(),Lt(a,1,1,()=>{e.blocks[d]===a&&(e.blocks[d]=null)}),Rt())}):e.block.d(1),u.c(),ut(u,1),u.m(e.mount(),e.anchor),f=!0),e.block=u,e.blocks&&(e.blocks[l]=u),f&&J()}if(dt(t)){const i=E();if(t.then(l=>{p(i),r(e.then,1,e.value,l),p(null)},l=>{if(p(i),r(e.catch,2,e.error,l),p(null),!e.hasCatch)throw l}),e.current!==e.pending)return r(e.pending,0),!0}else{if(e.current!==e.then)return r(e.then,1,e.value,t),!0;e.resolved=t}}function De(t,e,n){const r=e.slice(),{resolved:i}=t;t.current===t.then&&(r[t.value]=i),t.current===t.catch&&(r[t.error]=i),t.block.p(r,n)}function Oe(t,e){const n={},r={},i={$$scope:1};let l=t.length;for(;l--;){const s=t[l],o=e[l];if(o){for(const c in s)c in o||(r[c]=1);for(const c in o)i[c]||(n[c]=o[c],i[c]=1);t[l]=o}else for(const c in s)i[c]=1}for(const s in r)s in n||(n[s]=void 0);return n}function Te(t){return typeof t=="object"&&t!==null?t:{}}function Me(t,e,n){const r=t.$$.props[e];r!==void 0&&(t.$$.bound[r]=n,n(t.$$.ctx[r]))}function Pe(t){t&&t.c()}function qe(t,e){t&&t.l(e)}function Bt(t,e,n,r){const{fragment:i,after_update:l}=t.$$;i&&i.m(e,n),r||M(()=>{const s=t.$$.on_mount.map(V).filter(P);t.$$.on_destroy?t.$$.on_destroy.push(...s):k(s),t.$$.on_mount=[]}),l.forEach(M)}function Ht(t,e){const n=t.$$;n.fragment!==null&&(k(n.on_destroy),n.fragment&&n.fragment.d(e),n.on_destroy=n.fragment=null,n.ctx=[])}function Ft(t,e){t.$$.dirty[0]===-1&&(w.push(t),lt(),t.$$.dirty.fill(0)),t.$$.dirty[e/31|0]|=1<<e%31}function Re(t,e,n,r,i,l,s,o=[-1]){const c=A;p(t);const u=t.$$={fragment:null,ctx:[],props:l,update:b,not_equal:i,bound:K(),on_mount:[],on_destroy:[],on_disconnect:[],before_update:[],after_update:[],context:new Map(e.context||(c?c.$$.context:[])),callbacks:K(),dirty:o,skip_bound:!1,root:e.target||c.$$.root};s&&s(u.root);let f=!1;if(u.ctx=n?n(t,e.props||{},(a,d,..._)=>{const h=_.length?_[0]:d;return u.ctx&&i(u.ctx[a],u.ctx[a]=h)&&(!u.skip_bound&&u.bound[a]&&u.bound[a](h),f&&Ft(t,a)),d}):[],u.update(),f=!0,k(u.before_update),u.fragment=r?r(u.ctx):!1,e.target){if(e.hydrate){yt();const a=At(e.target);u.fragment&&u.fragment.l(a),a.forEach(nt)}else u.fragment&&u.fragment.c();e.intro&&ut(t.$$.fragment),Bt(t,e.target,e.anchor,e.customElement),gt(),J()}p(c)}class Le{$destroy(){Ht(this,1),this.$destroy=b}$on(e,n){if(!P(n))return b;const r=this.$$.callbacks[e]||(this.$$.callbacks[e]=[]);return r.push(n),()=>{const i=r.indexOf(n);i!==-1&&r.splice(i,1)}}$set(e){this.$$set&&!ht(e)&&(this.$$.skip_bound=!0,this.$$set(e),this.$$.skip_bound=!1)}}export{Et as $,Ae as A,b as B,Kt as C,Ut as D,Vt as E,Qt as F,kt as G,Jt as H,Wt as I,se as J,Yt as K,ke as L,_t as M,Xt as N,Ne as O,U as P,le as Q,ce as R,Le as S,te as T,Oe as U,P as V,k as W,M as X,Ce as Y,Ee as Z,Te as _,re as a,fe as a0,oe as a1,ge as a2,Zt as a3,he as a4,ne as a5,Gt as a6,Se as a7,Me as a8,De as a9,je as aa,ve as ab,be as ac,pe as ad,ye as ae,ue as af,ee as b,_e as c,Rt as d,ie as e,ut as f,qt as g,nt as h,Re as i,we as j,rt as k,ae as l,At as m,G as n,xe as o,me as p,W as q,Ct as r,It as s,Lt as t,de as u,$e as v,Pe as w,qe as x,Bt as y,Ht as z};