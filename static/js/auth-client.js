/* ============================================
   前端登录态管理
   ============================================ */
(function(){
  const TOKEN_KEY = 'tsx-token';
  const USER_KEY = 'tsx-user';

  window.Auth = {
    // 登录/注册成功后调用
    save(token, member){
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(USER_KEY, JSON.stringify(member));
    },

    // 获取 token
    getToken(){
      return localStorage.getItem(TOKEN_KEY) || '';
    },

    // 获取用户信息
    getUser(){
      try {
        return JSON.parse(localStorage.getItem(USER_KEY)) || null;
      } catch(e){ return null; }
    },

    // 是否登录
    isLogin(){
      return !!this.getToken();
    },

    // 登出
    logout(){
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    }
  };
})();