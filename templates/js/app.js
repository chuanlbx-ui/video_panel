(function(){
  'use strict';

// ===== 全局变量 =====
const API = '/video-panel';
let user = null;
let template = null;
let templates = [];
let jobId = null;
let pollTimer = null;
let variants = [];
let variantIdx = 0;

// ===== 统一API请求（带错误处理和缓存） =====
window.apiFetch = function apiFetch(url, options){
  options = options || {};
  // 自动加 token
  var token = localStorage.getItem('user_token');
  if(token){
    options.headers = options.headers || {};
    options.headers['Authorization'] = 'Bearer ' + token;
  }
  // 超时控制（15秒）
  var controller = new AbortController();
  options.signal = controller.signal;
  var timer = setTimeout(function(){ controller.abort(); }, 15000);

  return fetch(API + url, options).then(function(r){
    clearTimeout(timer);
    return r.json().then(function(d){
      if(!r.ok){
        var err = new Error(d.error || d.message || '请求失败 ('+r.status+')');
        err.status = r.status;
        err.data = d;
        throw err;
      }
      return d;
    });
  }).catch(function(e){
    clearTimeout(timer);
    if(e.name === 'AbortError'){
      throw new Error('请求超时，请检查网络后重试');
    }
    throw e;
  });
}

// ===== Toast =====
window.toast = function toast(msg){
  var t = document.getElementById('toast');
  if(!t) return;
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(function(){ t.classList.remove('show'); }, 2500);
}

// ===== 错误边界 =====
window.showError = function showError(containerId, retryFn){
  var el = document.getElementById(containerId);
  if(!el) return;
  el.style.display = 'block';
  el.innerHTML =
    '<div class="eb-icon">😕</div>' +
    '<div class="eb-title">加载失败</div>' +
    '<div class="eb-desc">网络连接异常，请检查后重试</div>' +
    '<button class="error-retry-btn" onclick="(' + retryFn.toString() + ')()">🔄 重新加载</button>';
}

window.hideError = function hideError(containerId){
  var el = document.getElementById(containerId);
  if(el) el.style.display = 'none';
}

// ===== 分享裂变 =====
window.getUrlParam = function getUrlParam(name){
  var match = location.search.match(new RegExp('[?&]' + name + '=([^&]*)'));
  return match ? decodeURIComponent(match[1]) : '';
}

window.inviteFriend = function inviteFriend(){
  var token = localStorage.getItem('user_token');
  if(!token){ toast('请先登录'); return; }
  apiFetch('/api/invite-code').then(function(d){
    if(d.invite_url){
      var text = '用滇边AI做视频，超简单！点这里试试 → ' + d.invite_url;
      if(navigator.clipboard){
        navigator.clipboard.writeText(text).then(function(){ toast('邀请链接已复制，快去分享给好友！'); });
      } else {
        prompt('复制以下邀请链接分享给好友：', text);
      }
    }
  }).catch(function(){ toast('获取邀请码失败'); });
}

window.pushToWechat = function pushToWechat(){
  var token = localStorage.getItem('user_token');
  var name = localStorage.getItem('user_name') || '';
  if(!token || !jobId){ toast('请先生成视频'); return; }
  apiFetch('/api/invite-code').then(function(d){
    var inviteCode = d.invite_code || '';
    return apiFetch('/api/push-wechat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        job_id: jobId,
        invite_code: inviteCode,
        user_name: name
      })
    });
  }).then(function(d){
    if(d.success){
      toast('已加入推送队列，打开微信客户端自动发送到群');
    } else {
      toast(d.message || d.error || '推送失败');
    }
  }).catch(function(){ toast('推送失败，请重试'); });
}

// ===== 页面切换 =====
var screenNames = ['Login','Tpl','Form','Progress','Finish','Settings','History'];

window.showScreen = function showScreen(name){
  screenNames.forEach(function(s){
    var el = document.getElementById('screen'+s);
    if(el) el.classList.remove('active');
  });
  var el = document.getElementById('screen'+name);
  if(el) el.classList.add('active');
  var bar = document.getElementById('stepsBar');
  var stepMap = {Tpl:0, Form:1, Progress:2, Finish:2};
  var si = stepMap[name];
  if(si !== undefined){
    bar.classList.add('show');
    var dots = bar.querySelectorAll('.step-dot');
    for(var i=0; i<dots.length; i++){
      dots[i].classList.toggle('active', i===si);
      dots[i].classList.toggle('done', i<si);
    }
  } else {
    bar.classList.remove('show');
  }
}

window.goStep = function goStep(name){
  if(name==='tpl') showScreen('Tpl');
}

window.goHome = function goHome(){
  showScreen('Tpl');
  if(pollTimer) clearInterval(pollTimer);
}

// ===== 模板缓存 =====
window.getCachedTemplates = function getCachedTemplates(){
  try {
    var cached = localStorage.getItem('tpl_cache');
    var ts = localStorage.getItem('tpl_cache_ts');
    if(cached && ts){
      var age = Date.now() - parseInt(ts);
      if(age < 300000) return JSON.parse(cached); // 5分钟缓存
    }
  } catch(e){}
  return null;
}

window.setCachedTemplates = function setCachedTemplates(data){
  try {
    localStorage.setItem('tpl_cache', JSON.stringify(data));
    localStorage.setItem('tpl_cache_ts', String(Date.now()));
  } catch(e){}
}

// ===== 初始化 =====
window.init = function init(){
  var ref = getUrlParam('ref');
  if(ref){
    localStorage.setItem('invite_ref', ref);
    document.getElementById('loginHint').textContent = '🎁 好友邀请你来玩！';
  }
  autoLogin();

  // 先尝试从缓存加载模板
  var cached = getCachedTemplates();
  if(cached && cached.length){
    templates = cached;
    renderTplGrid();
  }

  // 再从服务器拉取最新
  apiFetch('/api/templates').then(function(d){
    var list = d.templates || [];
    if(list.length){
      templates = list;
      renderTplGrid();
      setCachedTemplates(list);
    }
  }).catch(function(){
    // 如果缓存有就用缓存，没有则显示错误
    if(!templates.length){
      showError('tplError', function(){ init(); });
    }
  });
}

// ===== 设置页 =====
window.loadSettings = function loadSettings(){
  var skeleton = document.getElementById('settingsSkeleton');
  var content = document.getElementById('settingsContent');
  var errEl = document.getElementById('settingsError');
  hideError('settingsError');
  if(skeleton) skeleton.style.display = 'flex';
  if(content) content.style.display = 'none';

  var token = localStorage.getItem('user_token');
  if(!token){ toast('请先登录'); return; }
  apiFetch('/api/me').then(function(d){
    if(skeleton) skeleton.style.display = 'none';
    if(content){ content.style.display = 'block'; }
    document.getElementById('setPhone').textContent = d.phone || '--';
    document.getElementById('setName').textContent = d.name || '--';
    document.getElementById('setRole').textContent = d.role || '--';
    document.getElementById('setApiKey').textContent = d.api_key || '--';
  }).catch(function(){
    if(skeleton) skeleton.style.display = 'none';
    showError('settingsError', function(){ loadSettings(); });
  });
}

// ===== 历史页 =====
window.loadHistory = function loadHistory(){
  var skeleton = document.getElementById('historySkeleton');
  var list = document.getElementById('historyList');
  var errEl = document.getElementById('historyError');
  hideError('historyError');
  if(skeleton) skeleton.style.display = 'block';
  if(list) list.style.display = 'none';

  var token = localStorage.getItem('user_token');
  if(!token){ toast('请先登录'); return; }
  apiFetch('/api/history').then(function(d){
    if(skeleton) skeleton.style.display = 'none';
    if(!list) return;
    var items = d.history || [];
    if(!items.length){
      list.innerHTML = '<div style="text-align:center;padding:40px 20px;color:rgba(255,255,255,.2);font-size:14px;">还没有生成过视频<br><span style="font-size:12px;">去选个模板试试吧</span></div>';
    } else {
      var html = '';
      for(var i=0; i<items.length; i++){
        var h = items[i];
        html += '<div class="history-item">';
        html += '<div class="hi-icon">🎬</div>';
        html += '<div class="hi-info"><div class="hi-title">' + (h.title || h.brand || '未命名视频') + '</div>' + (h.created_at || '') + '</div>';
        html += '<div class="hi-action" onclick="event.stopPropagation();window.open(\''+API+'/api/download/'+h.job_id+'\')">⬇</div>';
        html += '</div>';
      }
      list.innerHTML = html;
    }
    list.style.display = 'flex';
  }).catch(function(){
    if(skeleton) skeleton.style.display = 'none';
    showError('historyError', function(){ loadHistory(); });
  });
}

})();
