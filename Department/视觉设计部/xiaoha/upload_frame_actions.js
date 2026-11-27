(() => {
  const w = window, d = w.document;
  if (w.__xiaohaFrameActionsV2) return;
  w.__xiaohaFrameActionsV2 = true;
  let menu, dialog, previousFocus;
  const closeMenu = () => { if (menu) menu.remove(); menu = null; };
  const closeDialog = () => { if (dialog) dialog.remove(); dialog = null; previousFocus?.focus?.(); };
  const styles = d.createElement('style');
  styles.textContent = `
    .xiaoha-image-menu{position:fixed;z-index:1000002;min-width:168px;padding:6px;background:#111b30;color:#edf0ff;border:1px solid #455174;border-radius:12px;box-shadow:0 12px 35px #0008}
    .xiaoha-image-menu button,.xiaoha-image-dialog button{border:0;border-radius:7px;padding:10px 14px;background:transparent;color:inherit;cursor:pointer;font:14px system-ui}
    .xiaoha-image-menu button{display:block;text-align:left;width:100%}
    .xiaoha-image-menu button:hover,.xiaoha-image-dialog button:hover{background:#354466}
    .xiaoha-image-dialog{position:fixed;inset:0;z-index:1000001;background:#020611ee;color:#edf0ff;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px;box-sizing:border-box}
    .xiaoha-image-dialog header{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px;width:min(1400px,100%);margin-bottom:16px}
    .xiaoha-image-dialog header span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:45vw}
    .xiaoha-image-dialog img{display:block;max-width:94vw;max-height:82vh;object-fit:contain}
  `;
  d.head.appendChild(styles);
  function frame(event) {
    const zone = event.target.closest?.('[data-testid="stFileUploaderDropzone"]');
    const root = zone?.closest('[class*="st-key-upload_frame_"]');
    const meta = root?.querySelector('.upload-frame-meta');
    const input = zone?.querySelector('input[type="file"]');
    return meta?.dataset.source && input ? {meta, input, zone} : null;
  }
  function replace(f) { closeMenu(); closeDialog(); if (f.input.isConnected && !f.input.disabled) f.input.click(); }
  async function download(f) {
    closeMenu();
    const response = await fetch(f.meta.dataset.source);
    const url = URL.createObjectURL(await response.blob());
    const a = d.createElement('a'); a.href = url;
    a.download = (f.meta.dataset.filename || 'image.png').replace(/[\\/:*?"<>|]/g, '_');
    d.body.appendChild(a); a.click(); a.remove();
    w.setTimeout(() => URL.revokeObjectURL(url), 30000);
  }
  function button(label, action, parent) {
    const b = d.createElement('button'); b.type = 'button'; b.textContent = label;
    b.addEventListener('click', action); parent.appendChild(b); return b;
  }
  function enlarge(f) {
    closeMenu(); closeDialog(); previousFocus = d.activeElement;
    dialog = d.createElement('div'); dialog.className = 'xiaoha-image-dialog';
    dialog.setAttribute('role', 'dialog'); dialog.setAttribute('aria-modal', 'true'); dialog.setAttribute('aria-label', '图片放大预览');
    const header = d.createElement('header');
    const name = d.createElement('span'); name.textContent = f.meta.dataset.filename || '图片预览'; header.appendChild(name);
    const actions = d.createElement('div');
    button('下载原图', () => download(f), actions);
    button('更换图片', () => replace(f), actions);
    const close = button('关闭', closeDialog, actions);
    header.appendChild(actions); dialog.appendChild(header);
    const img = d.createElement('img'); img.src = f.meta.dataset.source; img.alt = name.textContent;
    dialog.appendChild(img); dialog.addEventListener('click', event => { if (event.target === dialog) closeDialog(); });
    d.body.appendChild(dialog); close.focus();
  }
  d.addEventListener('click', event => {
    if (event.target.matches?.('input[type="file"]')) return;
    const f = frame(event); if (!f) return;
    event.preventDefault(); event.stopImmediatePropagation(); enlarge(f);
  }, true);
  d.addEventListener('contextmenu', event => {
    const f = frame(event); if (!f) return;
    event.preventDefault(); event.stopImmediatePropagation(); closeMenu();
    menu = d.createElement('div'); menu.className = 'xiaoha-image-menu'; menu.setAttribute('role', 'menu');
    button('放大查看', () => enlarge(f), menu);
    button('下载原图', () => download(f), menu);
    button('更换图片', () => replace(f), menu);
    if (f.meta.dataset.removeKey) button('移除图片', () => {
      const key = f.meta.dataset.removeKey;
      closeMenu(); closeDialog();
      d.getElementsByClassName('st-key-' + key)[0]?.querySelector('button')?.click();
    }, menu);
    d.body.appendChild(menu);
    menu.style.left = Math.max(8, Math.min(event.clientX, w.innerWidth - menu.offsetWidth - 8)) + 'px';
    menu.style.top = Math.max(8, Math.min(event.clientY, w.innerHeight - menu.offsetHeight - 8)) + 'px';
    menu.querySelector('button').focus();
  }, true);
  d.addEventListener('pointerdown', event => { if (menu && !menu.contains(event.target)) closeMenu(); }, true);
  d.addEventListener('keydown', event => { if (event.key === 'Escape') { closeMenu(); closeDialog(); } }, true);
})();
