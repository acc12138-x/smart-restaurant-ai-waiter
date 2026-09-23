/* ============================================
   Mode Switch + Hero Video + Table Reader
   All non-ASCII strings escaped as \uXXXX
   ============================================ */
(function(){
  var KEY = 'tsx-mode';
  var body = document.body;

  function apply(mode){
    body.classList.toggle('mode-elder', mode === 'elder');
    document.documentElement.classList.remove('pre-elder');
    body.style.visibility = '';

    var textEl = document.querySelector('.mode-text');
    var iconEl = document.querySelector('.mode-icon');
    if (textEl) textEl.textContent = mode === 'elder' ? '\u5e74\u8f7b\u7248' : '\u5927\u5b57\u7248';
    if (iconEl) iconEl.textContent = mode === 'elder' ? '\uD83D\uDC64' : '\uD83D\uDC41';

    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', mode === 'elder' ? '#FFF6E6' : '#1e0c05');
    if (window.Track) Track.track('mode_switch', { mode: mode });
  }

  var urlMode = new URLSearchParams(location.search).get('mode');
  var mode = urlMode || localStorage.getItem(KEY) || 'youth';
  apply(mode);

  document.addEventListener('click', function(e){
    var btn = e.target.closest('#modeToggle');
    if (!btn) return;
    var next = body.classList.contains('mode-elder') ? 'youth' : 'elder';
    apply(next);
    try { localStorage.setItem(KEY, next); } catch(err){}
    btn.classList.add('pulse');
    setTimeout(function(){ btn.classList.remove('pulse'); }, 320);
  });

  window.tsxSetMode = function(m){
    apply(m);
    try { localStorage.setItem(KEY, m); } catch(err){}
  };

  window.addEventListener('load', function(){
    var l = document.getElementById('pageLoader');
    if (l) setTimeout(function(){ l.classList.add('hide'); }, 300);
  });
})();

/* Hero video */
(function(){
  var section = document.getElementById('heroVideo');
  var video   = document.getElementById('heroMedia');
  if (!section || !video) return;

  // iOS 关键：强制静音 + 内联播放
  video.muted = true;
  video.setAttribute('muted', '');
  video.setAttribute('playsinline', '');
  video.setAttribute('webkit-playsinline', '');
  video.setAttribute('autoplay', '');
  video.setAttribute('loop', '');

  function fallbackToPoster() {
    if (section.querySelector('img.hero-fallback')) return;
    var poster = video.getAttribute('poster');
    if (!poster) return;
    var img = document.createElement('img');
    img.src = poster;
    img.className = 'hero-fallback';
    img.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:1;';
    var pin = section.querySelector('.hero-pin');
    if (pin) pin.appendChild(img);
  }

  video.addEventListener('error', function(){
    console.log('[video] 加载失败，用 poster');
    video.style.display = 'none';
    fallbackToPoster();
  });

  function tryPlay(){
    if (document.body.classList.contains('mode-elder')) return;
    var p = video.play();
    if (p && p.catch){
      p.catch(function(err){
        console.log('[video] play 被拒: ' + err.name);
        fallbackToPoster();
      });
    }
  }

  if ('IntersectionObserver' in window){
    var obs = new IntersectionObserver(function(entries){
      entries.forEach(function(entry){
        if (entry.isIntersecting){ tryPlay(); }
        else { video.pause(); }
      });
    }, { threshold: 0.2 });
    obs.observe(section);
  } else {
    tryPlay();
  }

  // iOS / 安卓兜底：任何交互后重试
  ['touchstart','click','scroll'].forEach(function(evt){
    document.addEventListener(evt, function(){ tryPlay(); },
      { once: true, passive: true });
  });

  document.addEventListener('click', function(e){
    if (e.target.closest('#modeToggle')){
      setTimeout(function(){
        if (document.body.classList.contains('mode-elder')){ video.pause(); }
        else { tryPlay(); }
      }, 80);
    }
  });
})();

/* Table number from URL ?table=XX */
(function(){
  try {
    var params = new URLSearchParams(location.search);
    var table = params.get('table');
    if (table) {
      localStorage.setItem('tsx-table', table);
      try {
        if (!sessionStorage.getItem('tsx-scan-' + table)) {
          sessionStorage.setItem('tsx-scan-' + table, '1');
          fetch('/api/table/scan', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({table_no: table})
          }).catch(function(){});
        }
      } catch(e2) {}
      console.log('[QR] table =', table);
    }
  } catch(e) {}

  window.getCurrentTable = function(){
    try {
      return localStorage.getItem('tsx-table') || '\u5916\u5e26';
    } catch(e) {
      return '\u5916\u5e26';
    }
  };

  window.setCurrentTable = function(t){
    try {
      if (t) localStorage.setItem('tsx-table', t);
      else localStorage.removeItem('tsx-table');
    } catch(e) {}
  };
})();
