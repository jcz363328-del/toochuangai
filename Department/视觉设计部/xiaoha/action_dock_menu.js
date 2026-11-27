(() => {
  const w = window, d = w.document;
  if (w.__xiaohaDockMenus) return;
  w.__xiaohaDockMenus = true;
  const docks = '.st-key-workbench_action_dock, .st-key-fusion_action_dock';
  let scheduled = false;
  function place() {
    scheduled = false;
    const input = d.querySelector(docks.split(', ').map(s => s + ' [role="combobox"][aria-expanded="true"]').join(', '));
    if (!input) {
      d.querySelectorAll('[data-xiaoha-dock-menu="true"]').forEach(menu => {
        for (const key of ['position','transform','left','top','width','max-height','overflow-y','overscroll-behavior']) menu.style.removeProperty(key);
        delete menu.dataset.xiaohaDockMenu;
      });
      return;
    }
    const anchor = input.closest('[data-baseweb="select"]');
    const menu = d.querySelector('[data-baseweb="popover"]:has([data-testid="stSelectboxVirtualDropdown"])');
    if (!anchor || !menu) return;
    const rect = anchor.getBoundingClientRect();
    const available = Math.max(60, rect.top - 16);
    const height = Math.min(menu.scrollHeight, 320, available);
    const width = Math.min(rect.width, w.innerWidth - 16);
    const left = Math.max(8, Math.min(rect.left, w.innerWidth - width - 8));
    menu.dataset.xiaohaDockMenu = 'true';
    const values = {position:'fixed', transform:'none', left:left + 'px',
      top:Math.max(8, rect.top - height - 8) + 'px', width:width + 'px',
      maxHeight:height + 'px', overflowY:'auto', overscrollBehavior:'contain'};
    for (const [key, value] of Object.entries(values)) {
      const property = key.replace(/[A-Z]/g, c => '-' + c.toLowerCase());
      if (menu.style.getPropertyValue(property) !== value) menu.style.setProperty(property, value, 'important');
    }
  }
  function schedule() {
    if (!scheduled) { scheduled = true; w.requestAnimationFrame(place); }
  }
  new MutationObserver(schedule).observe(d.body, {childList:true, subtree:true,
    attributes:true, attributeFilter:['aria-expanded']});
  w.addEventListener('resize', schedule);
  d.addEventListener('scroll', schedule, true);
  d.addEventListener('wheel', event => {
    const menu = event.target.closest?.('[data-xiaoha-dock-menu="true"]');
    if (menu && menu.scrollHeight <= menu.clientHeight) event.preventDefault();
  }, {passive:false});
})();
