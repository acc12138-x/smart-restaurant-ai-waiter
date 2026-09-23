/* ============================================
   首页全屏 Hero v2
   - 无左右箭头
   - 无中央菜名
   - 左上角品牌
   - 底部标签 glow
   - 自动轮播 + 键盘左右 + 触摸滑动
   ============================================ */
(function(){
  var stage = document.getElementById('heroStage');
  var dotsEl = document.getElementById('heroDots');
  var labelBar = document.getElementById('heroLabelBar');

  if (!stage) return;

  var items = [];
  var labels = [];
  var autoplayMs = 8000;
  var currentIndex = 0;
  var autoplayTimer = null;

  function isVideo(path){
    return /\.(mp4|webm|mov)(\?|$)/i.test(path);
  }

  function escapeHtml(s){
    return String(s).replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }

  function buildStage(){
    stage.innerHTML = '';
    items.forEach(function(it, i){
      var wrap = document.createElement('div');
      wrap.className = 'hero-media' + (i === 0 ? ' is-active' : '');
      wrap.dataset.index = i;

      if (isVideo(it.video)){
        var v = document.createElement('video');
        v.src = it.video;
        v.muted = true;
        v.loop = true;
        v.playsInline = true;
        v.setAttribute('playsinline', '');
        v.setAttribute('webkit-playsinline', '');
        v.preload = i === 0 ? 'auto' : 'metadata';
        wrap.appendChild(v);
      } else {
        var img = document.createElement('img');
        img.src = it.video;
        img.alt = it.dish || '';
        wrap.appendChild(img);
      }
      stage.appendChild(wrap);
    });
  }

  function buildDots(){
    dotsEl.innerHTML = items.map(function(_, i){
      return '<span class="hero-dot' + (i === 0 ? ' is-active' : '') + '"></span>';
    }).join('');
  }

  function buildLabels(){
    if (!labels.length){
      labelBar.innerHTML = '';
      return;
    }
    labelBar.innerHTML = labels.map(function(lb){
      var url = '/menu?category=' + encodeURIComponent(lb.category);
      return '<a class="hero-label" href="' + url + '">' + escapeHtml(lb.name) + '</a>';
    }).join('');
  }

  function show(index){
    if (!items.length) return;
    currentIndex = ((index % items.length) + items.length) % items.length;

    var allMedia = stage.querySelectorAll('.hero-media');
    allMedia.forEach(function(m, i){
      m.classList.toggle('is-active', i === currentIndex);
      var v = m.querySelector('video');
      if (v){
        if (i === currentIndex){
          v.currentTime = 0;
          var p = v.play();
          if (p && p.catch) p.catch(function(){});
        } else {
          v.pause();
        }
      }
    });

    dotsEl.querySelectorAll('.hero-dot').forEach(function(d, i){
      d.classList.toggle('is-active', i === currentIndex);
    });
  }

  function next(){ show(currentIndex + 1); }
  function prev(){ show(currentIndex - 1); }

  function startAutoplay(){
    stopAutoplay();
    if (autoplayMs < 2000) return;
    autoplayTimer = setInterval(next, autoplayMs);
  }
  function stopAutoplay(){
    if (autoplayTimer){ clearInterval(autoplayTimer); autoplayTimer = null; }
  }
  function resetAutoplay(){
    stopAutoplay();
    startAutoplay();
  }

  document.addEventListener('keydown', function(e){
    if (e.key === 'ArrowLeft'){ prev(); resetAutoplay(); }
    if (e.key === 'ArrowRight'){ next(); resetAutoplay(); }
  });

  var touchStartX = null;
  stage.addEventListener('touchstart', function(e){
    touchStartX = e.touches[0].clientX;
  }, { passive: true });
  stage.addEventListener('touchend', function(e){
    if (touchStartX === null) return;
    var dx = e.changedTouches[0].clientX - touchStartX;
    if (Math.abs(dx) > 50){
      if (dx < 0) next(); else prev();
      resetAutoplay();
    }
    touchStartX = null;
  });

  document.addEventListener('visibilitychange', function(){
    if (document.hidden) stopAutoplay();
    else startAutoplay();
  });

  fetch('/api/hero')
    .then(function(r){ return r.json(); })
    .then(function(d){
      if (d.code !== 0){ return; }
      items = d.data.items || [];
      labels = d.data.labels || [];
      autoplayMs = d.data.autoplay_ms || 8000;

      if (!items.length){
        stage.innerHTML = '<div class="hero-skeleton">' +
          '<div class="hero-skeleton-icon">🍜</div>' +
          '<p>还没配置视频，请去后台"首页 Hero"添加</p></div>';
        return;
      }

      buildStage();
      buildDots();
      buildLabels();
      show(0);
      startAutoplay();
    })
    .catch(function(){
      stage.innerHTML = '<div class="hero-skeleton">' +
        '<div class="hero-skeleton-icon">😵</div><p>加载失败</p></div>';
    });
})();
