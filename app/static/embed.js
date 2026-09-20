/* SeatSetu embed — one-line integration for any college website.
   Usage:  <script src="https://YOUR-SEATSETU-HOST/embed.js" data-college="1" defer></script>
   Optional: data-base="https://your-seatsetu-host" (auto-detected from script src if omitted). */
(function () {
  var s = document.currentScript; if (!s) return;
  var cid = s.getAttribute('data-college') || '1';
  var base = s.getAttribute('data-base');
  if (!base) { try { base = new URL(s.src).origin; } catch (e) { base = ''; } }
  var W = base + '/widget/' + cid;

  var css = document.createElement('style');
  css.textContent =
    '#ss-bub{position:fixed;right:20px;bottom:20px;width:60px;height:60px;border-radius:50%;border:0;cursor:pointer;' +
    'background:linear-gradient(135deg,#0D9488,#0F766E);box-shadow:0 10px 30px rgba(11,31,28,.35);z-index:999999;' +
    'font-size:26px;line-height:60px;text-align:center;color:#fff;transition:transform .2s}' +
    '#ss-bub:hover{transform:scale(1.08)}' +
    '#ss-panel{position:fixed;right:20px;bottom:92px;width:min(390px,calc(100vw - 24px));height:min(620px,72vh);' +
    'border-radius:18px;overflow:hidden;box-shadow:0 24px 70px rgba(11,31,28,.45);z-index:999999;display:none;' +
    'border:1px solid #DCE9E6;background:#fff}' +
    '#ss-panel iframe{width:100%;height:100%;border:0}' +
    '#ss-x{position:absolute;top:8px;right:10px;z-index:2;width:30px;height:30px;border-radius:50%;border:0;' +
    'background:rgba(11,31,28,.55);color:#fff;font-size:15px;cursor:pointer}';
  document.head.appendChild(css);

  var panel = document.createElement('div'); panel.id = 'ss-panel';
  var x = document.createElement('button'); x.id = 'ss-x'; x.textContent = '✕';
  x.onclick = function () { panel.style.display = 'none'; };
  var fr = document.createElement('iframe');
  fr.src = W; fr.title = 'AI Counselor'; fr.loading = 'lazy';
  panel.appendChild(x); panel.appendChild(fr);

  var bub = document.createElement('button'); bub.id = 'ss-bub';
  bub.setAttribute('aria-label', 'Chat with AI counselor'); bub.textContent = '💬';
  bub.onclick = function () {
    var open = panel.style.display === 'block';
    panel.style.display = open ? 'none' : 'block';
    bub.textContent = open ? '💬' : '✕';
  };
  document.body.appendChild(bub); document.body.appendChild(panel);
})();
