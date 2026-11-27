(() => {
  const w = window, d = w.document;
  if (w.__xiaohaProcessingTransition) return;
  w.__xiaohaProcessingTransition = true;
  const style = d.createElement('style');
  style.textContent = `
    [data-testid="stElementContainer"][data-stale="true"] {opacity:1!important;}
    .xiaoha-processing-host {position:relative!important;}
    .xiaoha-submit-loading {position:absolute;inset:0;z-index:20;background:#0a1326;border-radius:12px;display:flex;}
    .xiaoha-submit-loading>.result-empty {flex:1;margin:0!important;min-height:100%!important;}
  `;
  d.head.appendChild(style);
  let pending = null;
  function remove() {
    if (!pending) return;
    pending.overlay.remove();
    pending.host.classList.remove('xiaoha-processing-host');
    pending = null;
  }
  function target() {
    return d.querySelector('.st-key-workbench_results, .st-key-fusion_results, .st-key-composer_results, .st-key-poster_fusion_results')
      || d.querySelector('.result-empty')?.closest('[data-testid="stElementContainer"]');
  }
  function refresh() {
    if (!pending) return;
    const real = [...d.querySelectorAll('.xiaoha-result-loading')].find(el =>
      !el.closest('.xiaoha-submit-loading') && !el.closest('[data-stale="true"]'));
    const error = [...d.querySelectorAll('[data-testid="stAlertContentError"], [data-testid="stAlertContentWarning"], [data-testid="stException"]')]
      .some(el => !pending.alerts.has(el) && !el.closest('[data-stale="true"]'));
    if (real || Date.now() > pending.until || error) {
      remove();
      return;
    }
    if (!pending.host.isConnected) {
      const next = target();
      if (next) {
        pending.host = next;
        next.classList.add('xiaoha-processing-host');
        next.appendChild(pending.overlay);
      }
    }
  }
  d.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button || button.disabled) return;
    const widget = button.closest('[class*="st-key-process_"], .st-key-poster_fusion_generate, .st-key-composer_generate');
    if (!widget) return;
    const host = target();
    if (!host || host.querySelector('.xiaoha-result-loading')) return;
    remove();
    const overlay = d.createElement('div');
    overlay.className = 'xiaoha-submit-loading';
    overlay.innerHTML = __XIAOHA_LOADING_HTML__;
    pending = {host, overlay, until: Date.now() + 20000, alerts: new Set(d.querySelectorAll('[data-testid="stAlertContentError"], [data-testid="stAlertContentWarning"], [data-testid="stException"]'))};
    host.classList.add('xiaoha-processing-host');
    host.appendChild(overlay);
  }, true);
  new MutationObserver(refresh).observe(d.body, {childList:true, subtree:true, attributes:true, attributeFilter:['data-stale']});
  w.setInterval(refresh, 500);
})();
