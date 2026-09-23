/* ============================================
   购物车（localStorage 持久化）
   ============================================ */
(function(){
  const KEY = 'tsx-cart';

  function load(){
    try {
      return JSON.parse(localStorage.getItem(KEY)) || [];
    } catch(e){
      return [];
    }
  }

  function save(cart){
    localStorage.setItem(KEY, JSON.stringify(cart));
    render();
  }

  function add(name, price){
    const cart = load();
    const existing = cart.find(it => it.name === name);
    if (existing){
      existing.qty += 1;
    } else {
      cart.push({ name, price, qty: 1 });
    }
    save(cart);
    toast(`已添加「${name}」`);
    if (window.Track) {
      Track.track('add_to_cart', { name, price });
    }
  }

  function remove(name){
    const cart = load().filter(it => it.name !== name);
    save(cart);
  }

  function inc(name){
    const cart = load();
    const it = cart.find(x => x.name === name);
    if (it){ it.qty += 1; save(cart); }
  }

  function dec(name){
    const cart = load();
    const it = cart.find(x => x.name === name);
    if (!it) return;
    it.qty -= 1;
    if (it.qty <= 0){
      remove(name);
    } else {
      save(cart);
    }
  }

  function clear(){
    save([]);
  }

  function count(){
    return load().reduce((s, it) => s + it.qty, 0);
  }

  function total(){
    return load().reduce((s, it) => s + it.price * it.qty, 0);
  }

  function render(){
    const btn = document.getElementById('cartCount');
    const itemsBox = document.getElementById('cartItems');
    const totalEl = document.getElementById('cartTotal');
    if (!btn) return;

    const cart = load();
    btn.textContent = count();

    if (cart.length === 0){
      if (itemsBox) itemsBox.innerHTML = '<p class="cart-empty">还没有选择菜品</p>';
      if (totalEl) totalEl.textContent = '合计：0 元';
      return;
    }

    if (itemsBox){
      itemsBox.innerHTML = cart.map(it => `
        <div class="cart-item">
          <span class="ci-name">${it.name}</span>
          <div class="ci-ctrl">
            <button type="button" data-action="dec" data-name="${it.name}">−</button>
            <span class="ci-qty">${it.qty}</span>
            <button type="button" data-action="inc" data-name="${it.name}">+</button>
          </div>
          <span class="ci-sub">${(it.price * it.qty).toFixed(2)} 元</span>
        </div>
      `).join('');

      itemsBox.querySelectorAll('button[data-action]').forEach(b => {
        b.onclick = () => {
          const action = b.dataset.action;
          const name = b.dataset.name;
          if (action === 'inc') inc(name);
          if (action === 'dec') dec(name);
        };
      });
    }
    if (totalEl) totalEl.textContent = `合计：${total().toFixed(2)} 元`;
  }

  function toast(msg){
    const el = document.createElement('div');
    el.className = 'cart-toast';
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.classList.add('show'), 10);
    setTimeout(() => {
      el.classList.remove('show');
      setTimeout(() => el.remove(), 300);
    }, 1200);
  }

  // 下单（v3.8：走专用接口 /api/order/create，跳过 LLM）
  async function checkout(){
    const cart = load();
    if (cart.length === 0){ toast('购物车是空的'); return; }

    // ---------- 必须登录才能下单 ----------
    if (!window.Auth || !Auth.isLogin()) {
      var modalEl0 = document.getElementById('cartModal');
      if (modalEl0) modalEl0.classList.remove('show');
      location.href = '/profile?login=1';
      return;
    }

    // ---------- 防抖：按钮加 loading ----------
    var checkoutBtn = document.getElementById('cartCheckout');
    if (checkoutBtn && checkoutBtn.disabled) return;
    var origText = '下单';
    if (checkoutBtn){
      origText = checkoutBtn.textContent || '下单';
      checkoutBtn.disabled = true;
      checkoutBtn.textContent = '下单中…';
    }

    var tableNo = (window.getCurrentTable && window.getCurrentTable()) || '外带';
    var token = localStorage.getItem('tsx-token') || '';

    try {
      var res = await fetch('/api/order/create', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + token
        },
        body: JSON.stringify({
          items: cart.map(function(it){ return { name: it.name, qty: it.qty }; }),
          table_no: tableNo
        })
      }).then(function(r){ return r.json(); });

      if (res.code === 401) {
        if (window.Auth && Auth.logout) Auth.logout();
        toast('登录已过期，请重新登录');
        setTimeout(function(){ location.href = '/profile?login=1'; }, 800);
        return;
      }

      var order = res.data && res.data.order;
      if (res.code === 0 && order){
        var m = document.getElementById('cartModal');
        if (m) m.classList.remove('show');
        showOrderSuccess(order);
        clear();
      } else {
        toast(res.msg || '下单失败');
      }
    } catch(e){
      toast('网络错误');
    } finally {
      if (checkoutBtn){
        checkoutBtn.disabled = false;
        checkoutBtn.textContent = origText;
      }
    }
  }

  function showOrderSuccess(order){
    const modal = document.getElementById('orderSuccessModal');
    if (!modal) return;

    document.getElementById('osOrderId').textContent = '订单号 ' + order.id;

    document.getElementById('osItems').innerHTML = order.items.map(it => `
      <div class="os-item">
        <span>${it.name} × ${it.qty}</span>
        <span>${it.subtotal} 元</span>
      </div>
    `).join('');

    document.getElementById('osTotal').textContent = order.total + ' 元';

    // "查看订单"：始终直接跳订单跟踪页（不需要登录）
    const profileBtn = document.getElementById('osProfile');
    if (profileBtn) {
      profileBtn.href = '/order/' + order.id;
      profileBtn.textContent = '查看订单 →';
      profileBtn.style.display = '';
    }

    // 底部提示
    const loginTip = document.getElementById('osLoginTip');
    if (loginTip) {
      const isLogin = window.Auth && Auth.isLogin && Auth.isLogin();
      if (isLogin) {
        loginTip.style.display = 'none';
      } else {
        loginTip.textContent = '（未登录下单，订单与本账号无关）';
        loginTip.style.display = 'block';
      }
    }

    // 把订单号存到 localStorage（匿名用户也能在"我的"里看到）
    try {
      var orders = JSON.parse(localStorage.getItem('tsx-orders') || '[]');
      if (!orders.find(function(o){ return o.id === order.id; })) {
        orders.unshift({
          id: order.id,
          total: order.total,
          items: order.items,
          status: order.status || 'pending',
          created_at: order.created_at || new Date().toISOString().slice(0,16).replace('T', ' ')
        });
        localStorage.setItem('tsx-orders', JSON.stringify(orders.slice(0, 20)));
      }
    } catch(e) {}

    // 绑定"取消订单"按钮
    var cancelBtn = document.getElementById('osCancel');
    if (cancelBtn && !cancelBtn.dataset.osCancelBtnBound) {
      cancelBtn.dataset.osCancelBtnBound = '1';
      cancelBtn.onclick = async function(){
        if (!confirm('确定取消订单 ' + order.id + '？\n取消后不可恢复。')) return;
        cancelBtn.disabled = true;
        cancelBtn.textContent = '取消中…';

        var token = localStorage.getItem('tsx-token') || '';
        var headers = {'Content-Type': 'application/json'};
        if (token) headers['Authorization'] = 'Bearer ' + token;

        try {
          var r = await fetch('/api/order/' + order.id + '/cancel', {
            method: 'POST', headers: headers
          });
          var d = await r.json();
          if (d.code === 0) {
            // 同步 localStorage
            try {
              var orders = JSON.parse(localStorage.getItem('tsx-orders') || '[]');
              for (var i = 0; i < orders.length; i++) {
                if (orders[i].id === order.id) { orders[i].status = 'cancelled'; break; }
              }
              localStorage.setItem('tsx-orders', JSON.stringify(orders));
            } catch(e) {}
            // 关弹窗 + 提示
            document.getElementById('orderSuccessModal').classList.remove('show');
            toast('订单已取消');
          } else {
            alert(d.msg || '取消失败');
            cancelBtn.disabled = false;
            cancelBtn.textContent = '取消订单';
          }
        } catch (e) {
          alert('网络错误');
          cancelBtn.disabled = false;
          cancelBtn.textContent = '取消订单';
        }
      };
    }

    modal.classList.add('show');
  }

  // 绑定 UI
  function bindUI(){
    const cartBtn = document.getElementById('cartBtn');
    const cartModal = document.getElementById('cartModal');
    const cartClose = document.getElementById('cartClose');
    const checkoutBtn = document.getElementById('cartCheckout');

    if (cartBtn && cartModal){
      cartBtn.onclick = () => cartModal.classList.add('show');
    }
    if (cartClose && cartModal){
      cartClose.onclick = () => cartModal.classList.remove('show');
    }
    if (cartModal){
      cartModal.onclick = (e) => {
        if (e.target === cartModal) cartModal.classList.remove('show');
      };
    }
    if (checkoutBtn){
      checkoutBtn.onclick = checkout;
    }

    // 关闭弹窗时刷新
    if (cartModal){
      const observer = new MutationObserver(render);
      observer.observe(cartModal, { attributes: true, attributeFilter: ['class'] });
    }

    render();
        // 订单成功弹窗交互
    const osModal = document.getElementById('orderSuccessModal');
    const osClose = document.getElementById('osClose');
    if (osModal){
      osModal.onclick = (e) => {
        if (e.target === osModal) osModal.classList.remove('show');
      };
    }
    if (osClose && osModal){
      osClose.onclick = () => osModal.classList.remove('show');
    }
  }

  // 暴露给外部
  window.Cart = { add, remove, inc, dec, clear, count, total, render, checkout };

  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', bindUI);
  } else {
    bindUI();
  }
})();

