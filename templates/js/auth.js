(function(){
  'use strict';

  // ===== 分享裂变 =====
  window.getInviteCode = function(){
    var token = localStorage.getItem('user_token');
    if(!token){ window.toast('请先登录'); return; }
    fetch(window.API + '/api/invite-code', {headers:{'Authorization':'Bearer '+token}})
    .then(function(r){ return r.json(); })
    .then(function(d){
      if(d.invite_url){
        var text = '用滇边AI做视频，超简单！点这里试试 → ' + d.invite_url;
        if(navigator.clipboard){
          navigator.clipboard.writeText(text).then(function(){ window.toast('邀请链接已复制，快去分享给好友！'); });
        } else {
          prompt('复制以下邀请链接分享给好友：', text);
        }
      }
    }).catch(function(){ window.toast('获取邀请码失败'); });
  };

  window.pushToWechat = function(){
    var token = localStorage.getItem('user_token');
    var name = localStorage.getItem('user_name') || '';
    if(!token || !window.jobId){ window.toast('请先生成视频'); return; }
    fetch(window.API + '/api/invite-code', {headers:{'Authorization':'Bearer '+token}})
    .then(function(r){ return r.json(); })
    .then(function(d){
      var inviteCode = d.invite_code || '';
      return fetch(window.API + '/api/push-wechat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          job_id: window.jobId,
          invite_code: inviteCode,
          user_name: name
        })
      });
    }).then(function(r){ return r.json(); })
    .then(function(d){
      if(d.success){
        window.toast('已加入推送队列，打开微信客户端自动发送到群');
      } else {
        window.toast(d.message || d.error || '推送失败');
      }
    }).catch(function(){ window.toast('推送失败，请重试'); });
  };

  // ===== 登录/注册 Tab 切换 =====
  window.switchLoginTab = function(tab){
    document.querySelectorAll('.login-tab').forEach(function(t){ t.classList.toggle('active', t.dataset.tab===tab); });
    document.getElementById('loginForm').style.display = tab==='login' ? '' : 'none';
    document.getElementById('registerForm').style.display = tab==='register' ? '' : 'none';
    document.getElementById('loginError').classList.remove('show');
    document.getElementById('regError').classList.remove('show');
    var hint = document.getElementById('loginHint');
    hint.textContent = tab==='login' ? '输入手机号和密码即可登录' : '注册后即可免费使用';
  };

  // ===== 登录 =====
  document.addEventListener('DOMContentLoaded', function(){
    var loginBtn = document.getElementById('loginBtn');
    if(loginBtn){
      loginBtn.addEventListener('click', function(){
        var phone = document.getElementById('loginPhone').value.trim();
        var password = document.getElementById('loginPassword').value;
        var errEl = document.getElementById('loginError');
        errEl.classList.remove('show');
        if(!phone){ errEl.textContent='请输入手机号'; errEl.classList.add('show'); return; }
        var btn = this;
        btn.disabled = true;
        btn.textContent = '登录中...';
        fetch(window.API + '/api/login', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({phone: phone, password: password, ref: window.getUrlParam('ref')})
        }).then(function(r){ return r.json(); })
        .then(function(d){
          if(d.token){
            window.user = d;
            localStorage.setItem('user_token', d.token);
            localStorage.setItem('g_token', d.token);
            localStorage.setItem('user_name', d.name);
            document.getElementById('userInfo').innerHTML = '&#128075; <strong>' + d.name + '</strong>';
            window.showScreen('Tpl');
            window.toast('欢迎回来，' + d.name);
          } else {
            errEl.textContent = d.error || '登录失败';
            errEl.classList.add('show');
          }
          btn.disabled = false;
          btn.textContent = '&#128640; 登录';
        }).catch(function(){
          errEl.textContent = '网络错误，请重试';
          errEl.classList.add('show');
          btn.disabled = false;
          btn.textContent = '&#128640; 登录';
        });
      });
    }

    // ===== 注册 =====
    var regBtn = document.getElementById('regBtn');
    if(regBtn){
      regBtn.addEventListener('click', function(){
        var name = document.getElementById('regName').value.trim();
        var phone = document.getElementById('regPhone').value.trim();
        var password = document.getElementById('regPassword').value;
        var errEl = document.getElementById('regError');
        errEl.classList.remove('show');
        if(!name){ errEl.textContent='请输入姓名'; errEl.classList.add('show'); return; }
        if(!phone){ errEl.textContent='请输入手机号'; errEl.classList.add('show'); return; }
        if(!password || password.length < 6){ errEl.textContent='密码至少6位'; errEl.classList.add('show'); return; }
        var btn = this;
        btn.disabled = true;
        btn.textContent = '注册中...';
        fetch(window.API + '/api/register', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({name: name, phone: phone, password: password, ref: window.getUrlParam('ref')})
        }).then(function(r){ return r.json(); })
        .then(function(d){
          if(d.token){
            window.user = d;
            localStorage.setItem('user_token', d.token);
            localStorage.setItem('g_token', d.token);
            localStorage.setItem('user_name', d.name);
            document.getElementById('userInfo').innerHTML = '&#128075; <strong>' + d.name + '</strong>';
            window.showScreen('Tpl');
            window.toast('注册成功，欢迎 ' + d.name);
          } else {
            errEl.textContent = d.error || '注册失败';
            errEl.classList.add('show');
          }
          btn.disabled = false;
          btn.textContent = '&#10022; 注册';
        }).catch(function(){
          errEl.textContent = '网络错误，请重试';
          errEl.classList.add('show');
          btn.disabled = false;
          btn.textContent = '&#10022; 注册';
        });
      });
    }
  });

  window.autoLogin = function(){
    var token = localStorage.getItem('user_token');
    if(!token) return;
    fetch(window.API + '/api/me', {headers:{'Authorization':'Bearer '+token}})
    .then(function(r){
      if(r.ok) return r.json();
      throw new Error('no');
    }).then(function(d){
      window.user = {name: d.name, token: token};
      document.getElementById('userInfo').innerHTML = '&#128075; <strong>' + d.name + '</strong>';
      window.showScreen('Tpl');
    }).catch(function(){
      localStorage.removeItem('user_token');
    });
  };

})();
