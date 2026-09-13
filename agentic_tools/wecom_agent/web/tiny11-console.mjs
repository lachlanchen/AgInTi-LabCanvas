// Crops match Set-Tiny11AppScreens.ps1's shared login-window placement.
export function loginCrop(width, height, mode) {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width < 2000 || height < 800) return null;
  if (mode !== 'wecom' && mode !== 'wechat') return null;
  const half = Math.floor(width / 2);
  const centerX = (half - 4) / 2 + (mode === 'wechat' ? half + 4 : 0);
  const centerY = (height - 48) / 2;
  const w = mode === 'wecom' ? 320 : 360;
  const h = mode === 'wecom' ? 340 : 440;
  return { x: Math.round(centerX - w / 2), y: Math.round(centerY - h / 2), width: w, height: h };
}

// Use noVNC's own local scaling control; never resize the guest desktop.
export function setDesktopZoom(doc, zoom) {
  if (!doc?.documentElement.classList.contains('noVNC_connected')) return false;
  const resize = doc.querySelector('#noVNC_setting_resize');
  if (!resize) return false;
  const changed = (input) => input.dispatchEvent(new doc.defaultView.Event('change', { bubbles: true }));
  resize.value = zoom === '100' ? 'off' : 'scale';
  changed(resize);
  return true;
}

if (typeof document !== 'undefined') {
  const frame = document.querySelector('#desktop');
  const preview = document.querySelector('#preview');
  const canvas = document.querySelector('#login');
  const state = document.querySelector('#state');
  const zoom = document.querySelector('#zoom');
  const ctx = canvas.getContext('2d');
  let mode = 'desktop';
  let zoomPending = true;
  zoom.value = new URL(location.href).searchParams.get('zoom') === '100' ? '100' : 'fit';

  function selectView(next) {
    mode = ['wecom', 'wechat'].includes(next) ? next : 'desktop';
    document.body.dataset.view = mode;
    preview.hidden = mode === 'desktop';
    // Enlarged views cannot forward accidental clicks/keys to a login dialog.
    frame.inert = mode !== 'desktop';
    frame.tabIndex = mode === 'desktop' ? 0 : -1;
    zoom.disabled = mode !== 'desktop';
    zoomPending = true;
    for (const button of document.querySelectorAll('button[data-view]')) {
      button.setAttribute('aria-pressed', String(button.dataset.view === mode));
    }
    state.textContent = mode === 'desktop' ? '' : 'View only';
    const url = new URL(location.href);
    if (mode === 'desktop') url.searchParams.delete('view');
    else url.searchParams.set('view', mode);
    history.replaceState(null, '', url);
    draw();
  }

  function draw() {
    if (document.hidden) return;
    if (zoomPending) {
      // QR crops need the full framebuffer even when 100% uses native panning.
      zoomPending = !setDesktopZoom(frame.contentDocument, mode === 'desktop' ? zoom.value : 'fit');
    }
    if (mode === 'desktop') return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    try {
      const doc = frame.contentDocument;
      if (!doc?.documentElement.classList.contains('noVNC_connected')) {
        state.textContent = 'Reconnecting'; return;
      }
      const source = doc.querySelector('canvas');
      const rect = source && loginCrop(source.width, source.height, mode);
      if (!rect) { state.textContent = 'Connecting'; return; }
      if (canvas.width !== rect.width || canvas.height !== rect.height) {
        canvas.width = rect.width; canvas.height = rect.height;
      }
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(source, rect.x, rect.y, rect.width, rect.height, 0, 0, rect.width, rect.height);
      state.textContent = 'View only';
    } catch { state.textContent = 'Reconnecting'; }
  }

  for (const button of document.querySelectorAll('button[data-view]')) {
    button.addEventListener('click', () => selectView(button.dataset.view));
  }
  zoom.addEventListener('change', () => {
    const url = new URL(location.href);
    if (zoom.value === '100') url.searchParams.set('zoom', '100');
    else url.searchParams.delete('zoom');
    history.replaceState(null, '', url);
    zoomPending = true;
    draw();
  });
  frame.addEventListener('load', () => { zoomPending = true; });
  selectView(new URL(location.href).searchParams.get('view'));
  // Display-only local pixels: no extra VNC connection, API polling, or QR cache.
  let timer = setInterval(draw, 250);
  addEventListener('pagehide', () => {
    clearInterval(timer); timer = null;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  });
  addEventListener('pageshow', () => {
    if (timer === null) timer = setInterval(draw, 250);
  });
}
