/* ============================================
   前端埋点
   ============================================ */
(function(){
  function track(event, payload){
    try {
      const token = localStorage.getItem('tsx-token') || '';
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = 'Bearer ' + token;

      // 用 sendBeacon 更可靠（页面关闭也能发出去）
      const data = JSON.stringify({ event, payload });
      if (navigator.sendBeacon) {
        const blob = new Blob([data], { type: 'application/json' });
        navigator.sendBeacon('/api/track', blob);
      } else {
        fetch('/api/track', { method: 'POST', headers, body: data, keepalive: true });
      }
    } catch(e){}
  }

  window.Track = { track };

  // 自动记录页面浏览
  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', () => {
      track('page_view', { page: location.pathname });
    });
  } else {
    track('page_view', { page: location.pathname });
  }
})();