import{o as e}from"./rolldown-runtime.BCiCTKAo.js";import{r as t}from"./emotion-is-prop-valid.esm.CkL99N7j.js";import{i as n,t as r}from"./emotion-styled.browser.esm.DdOkyKg_.js";import"./src.ClCGuae5.js";import{n as i,r as a,t as o}from"./types.DosXGzv6.js";import{n as s,t as c}from"./IFrameUtil.PlC_b34Z.js";var l=e(t(),1),u=r(`iframe`,{target:`ei36xw10`})(({theme:e,disableScrolling:t,width:n,height:r})=>({width:n??`100%`,height:r??`100%`,colorScheme:`normal`,border:`none`,padding:e.spacing.none,margin:e.spacing.none,overflow:t?`hidden`:void 0})),d=`streamlit:iframe:setSize`,f=`25rem`,p=`<script>
(function() {
  var lastW = 0, lastH = 0;
  function sendSize() {
    // Guard against malformed HTML (e.g., <frameset>) or script running before body init
    if (!document.body) return;
    // Use getBoundingClientRect for accurate fractional pixel measurement,
    // then ceil to avoid scrollbars from sub-pixel rounding
    var rect = document.body.getBoundingClientRect();
    var w = Math.ceil(Math.max(
      rect.width,
      document.body.scrollWidth,
      document.body.offsetWidth,
      document.documentElement.scrollWidth,
      document.documentElement.offsetWidth
    ));
    var h = Math.ceil(Math.max(
      rect.height,
      document.body.scrollHeight,
      document.body.offsetHeight,
      document.documentElement.scrollHeight,
      document.documentElement.offsetHeight
    ));
    if (w !== lastW || h !== lastH) {
      lastW = w; lastH = h;
      // Note: postMessage with '*' broadcasts to any origin, but this is safe because:
      // 1. This script only runs inside srcdoc (same-origin, sandboxed)
      // 2. The payload is just dimension integers
      // 3. The frontend receiver validates event.source === iframe.contentWindow
      window.parent.postMessage({type: '${d}', width: w, height: h}, '*');
    }
  }
  // Send initial size after DOM is ready
  if (document.readyState === 'complete') {
    sendSize();
  } else {
    window.addEventListener('load', sendSize);
  }
  // Re-measure on DOM changes
  if (typeof MutationObserver !== 'undefined') {
    new MutationObserver(sendSize).observe(document.body, {
      childList: true, subtree: true, attributes: true, characterData: true
    });
  }
  // Re-measure on resize and image/font loading
  window.addEventListener('resize', sendSize);
  document.addEventListener('load', sendSize, true);
})();
<\/script>`;function m(e){return e+p}function h(e){return i(e)||e===``?void 0:e}function g({element:e,widthConfig:t,heightConfig:r}){let i=h(e.src),p=a(i)?void 0:h(e.srcdoc),g=(0,l.useRef)(null),[_,v]=(0,l.useState)({width:null,height:null}),y=t?.useContent??!1,b=r?.useContent??!1,x=a(p)&&(y||b),S=x?m(p):p;(0,l.useEffect)(()=>{if(!x)return;let e=e=>{if(e.source&&e.source===g.current?.contentWindow){let t=e.data;if(t?.type===d&&typeof t.width==`number`&&typeof t.height==`number`&&Number.isFinite(t.width)&&Number.isFinite(t.height)&&t.width>=0&&t.height>=0){let e=t.width,n=t.height;v(t=>t.width===e&&t.height===n?t:{width:e,height:n})}}};return window.addEventListener(`message`,e),()=>{window.removeEventListener(`message`,e)}},[x]);let C=x&&y&&_.width!==null?`${_.width}px`:void 0,w;b&&(x&&_.height!==null?w=`${_.height}px`:a(i)&&(w=f));let T=e.alt?.trim();return n(u,{ref:g,className:`stIFrame`,"data-testid":`stIFrame`,allow:c,disableScrolling:!e.scrolling,src:i,srcDoc:S,scrolling:e.scrolling?`auto`:`no`,sandbox:s,title:o(T)?`st.iframe`:T,tabIndex:e.tabIndex??void 0,width:C,height:w})}var _=(0,l.memo)(g);export{_ as default};