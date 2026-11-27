(function () {
  const win = window.parent, doc = win.document;
  if (win.__xiaohaUploadSortCleanup) win.__xiaohaUploadSortCleanup();
  doc.querySelectorAll('.upload-sort-grip,.upload-sort-drop-zone').forEach(el => el.remove());
  let drag = null;
  const markers = () => Array.from(doc.querySelectorAll('.upload-preview-root[data-upload-sortable="true"]'));
  const cardOf = marker => marker.closest('div[data-testid="stVerticalBlock"]');
  function clear() {
    drag = null;
    doc.querySelectorAll('.upload-sort-drop-zone').forEach(el => el.remove());
    doc.querySelectorAll('.upload-sort-dragging').forEach(el => el.classList.remove('upload-sort-dragging'));
  }
  function commit(widget, source, target) {
    const bytes = new TextEncoder().encode(JSON.stringify({widget_key: widget, source_index: source, target_index: target}));
    const token = btoa(Array.from(bytes, byte => String.fromCharCode(byte)).join('')).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    const url = new URL(win.location.href);
    url.searchParams.set('__UPLOAD_REORDER_QUERY_KEY__', token);
    win.location.href = url.toString();
  }
  function install() {
    markers().forEach(marker => {
      const card = cardOf(marker);
      if (!card) return;
      card.classList.add('upload-sortable-item');
      let grip = card.querySelector(':scope > .upload-sort-grip');
      if (!grip) {
        grip = doc.createElement('div');
        grip.className = 'upload-sort-grip';
        grip.style.touchAction = 'none';
        grip.style.userSelect = 'none';
        grip.title = '按住拖动调整顺序';
        card.appendChild(grip);
      }
      grip.dataset.widget = marker.dataset.uploadWidget;
      grip.dataset.index = marker.dataset.uploadIndex;
      const label = '⠿ 优先级 ' + (Number(marker.dataset.uploadIndex) + 1);
      if (grip.textContent !== label) grip.textContent = label;
    });
  }
  function down(event) {
    const grip = event.target.closest('.upload-sort-grip');
    if (!grip || event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    drag = {widget: grip.dataset.widget, source: Number(grip.dataset.index), x: event.clientX, y: event.clientY, pointer: event.pointerId, moved: false, target: null};
  }
  function move(event) {
    if (!drag || drag.pointer !== event.pointerId) return;
    if (!drag.moved && Math.hypot(event.clientX - drag.x, event.clientY - drag.y) < 5) return;
    drag.moved = true;
    event.preventDefault();
    doc.querySelectorAll('.upload-sort-drop-zone').forEach(el => el.remove());
    drag.target = null;
    markers().filter(marker => marker.dataset.uploadWidget === drag.widget).forEach(marker => {
      const card = cardOf(marker);
      if (!card) return;
      const rect = card.getBoundingClientRect(), index = Number(marker.dataset.uploadIndex);
      const inside = event.clientX >= rect.left && event.clientX <= rect.right && event.clientY >= rect.top && event.clientY <= rect.bottom;
      if (inside) drag.target = index;
      card.classList.toggle('upload-sort-dragging', index === drag.source);
      const zone = doc.createElement('div');
      zone.className = 'upload-sort-drop-zone' + (inside ? ' is-target' : '') + (index === drag.source ? ' is-source' : '');
      Object.assign(zone.style, {pointerEvents: 'none', left: rect.left + 'px', top: rect.top + 'px', width: rect.width + 'px', height: rect.height + 'px'});
      zone.textContent = index === drag.source ? '当前图片' : '移到优先级 ' + (index + 1);
      doc.body.appendChild(zone);
    });
  }
  function up(event) {
    if (!drag || drag.pointer !== event.pointerId) return;
    const result = drag;
    clear();
    if (result.moved && result.target !== null && result.target !== result.source) commit(result.widget, result.source, result.target);
  }
  const cancel = () => clear();
  const key = event => { if (event.key === 'Escape') clear(); };
  const nativeDrag = event => { if (event.target.closest('.upload-sort-grip')) event.preventDefault(); };
  const listeners = [['pointerdown', down], ['pointermove', move], ['pointerup', up], ['pointercancel', cancel], ['keydown', key], ['dragstart', nativeDrag]];
  listeners.forEach(([name, handler]) => doc.addEventListener(name, handler, {capture: true, passive: false}));
  const observer = new MutationObserver(install);
  observer.observe(doc.body, {childList: true, subtree: true, attributes: true, attributeFilter: ['data-upload-index', 'data-upload-widget']});
  win.addEventListener('blur', cancel);
  win.__xiaohaUploadSortCleanup = () => {
    observer.disconnect();
    listeners.forEach(([name, handler]) => doc.removeEventListener(name, handler, true));
    win.removeEventListener('blur', cancel);
    clear();
  };
  install();
})();
