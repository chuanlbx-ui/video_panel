     1|(function(){
     2|  'use strict';
     3|
     4|// ===== 全局变量 =====
const API = '/video-panel';
window.API = API;
let user = null;
     7|let template = null;
     8|let templates = [];
     9|let jobId = null;
    10|let pollTimer = null;
    11|let variants = [];
    12|let variantIdx = 0;
    13|
    14|// ===== 统一API请求（带错误处理和缓存） =====
    15|window.apiFetch = function apiFetch(url, options){
    16|  options = options || {};
    17|  // 自动加 token
    18|  var token = localStorage.getItem('user_token');
    19|  if(token){
    20|    options.headers = options.headers || {};
    21|    options.headers['Authorization'] = 'Bearer ' + token;
    22|  }
    23|  // 超时控制（15秒）
    24|  var controller = new AbortController();
    25|  options.signal = controller.signal;
    26|  var timer = setTimeout(function(){ controller.abort(); }, 15000);
    27|
    28|  return fetch(API + url, options).then(function(r){
    29|    clearTimeout(timer);
    30|    return r.json().then(function(d){
    31|      if(!r.ok){
    32|        var err = new Error(d.error || d.message || '请求失败 ('+r.status+')');
    33|        err.status = r.status;
    34|        err.data = d;
    35|        throw err;
    36|      }
    37|      return d;
    38|    });
    39|  }).catch(function(e){
    40|    clearTimeout(timer);
    41|    if(e.name === 'AbortError'){
    42|      throw new Error('请求超时，请检查网络后重试');
    43|    }
    44|    throw e;
    45|  });
    46|}
    47|
    48|// ===== Toast =====
    49|window.toast = function toast(msg){
    50|  var t = document.getElementById('toast');
    51|  if(!t) return;
    52|  t.textContent = msg;
    53|  t.classList.add('show');
    54|  setTimeout(function(){ t.classList.remove('show'); }, 2500);
    55|}
    56|
    57|// ===== 错误边界 =====
    58|window.showError = function showError(containerId, retryFn){
    59|  var el = document.getElementById(containerId);
    60|  if(!el) return;
    61|  el.style.display = 'block';
    62|  el.innerHTML =
    63|    '<div class="eb-icon">😕</div>' +
    64|    '<div class="eb-title">加载失败</div>' +
    65|    '<div class="eb-desc">网络连接异常，请检查后重试</div>' +
    66|    '<button class="error-retry-btn" onclick="(' + retryFn.toString() + ')()">🔄 重新加载</button>';
    67|}
    68|
    69|window.hideError = function hideError(containerId){
    70|  var el = document.getElementById(containerId);
    71|  if(el) el.style.display = 'none';
    72|}
    73|
    74|// ===== 分享裂变 =====
    75|window.getUrlParam = function getUrlParam(name){
    76|  var match = location.search.match(new RegExp('[?&]' + name + '=([^&]*)'));
    77|  return match ? decodeURIComponent(match[1]) : '';
    78|}
    79|
    80|window.inviteFriend = function inviteFriend(){
    81|  var token = localStorage.getItem('user_token');
    82|  if(!token){ toast('请先登录'); return; }
    83|  apiFetch('/api/invite-code').then(function(d){
    84|    if(d.invite_url){
    85|      var text = '用滇边AI做视频，超简单！点这里试试 → ' + d.invite_url;
    86|      if(navigator.clipboard){
    87|        navigator.clipboard.writeText(text).then(function(){ toast('邀请链接已复制，快去分享给好友！'); });
    88|      } else {
    89|        prompt('复制以下邀请链接分享给好友：', text);
    90|      }
    91|    }
    92|  }).catch(function(){ toast('获取邀请码失败'); });
    93|}
    94|
    95|window.pushToWechat = function pushToWechat(){
    96|  var token = localStorage.getItem('user_token');
    97|  var name = localStorage.getItem('user_name') || '';
    98|  if(!token || !jobId){ toast('请先生成视频'); return; }
    99|  apiFetch('/api/invite-code').then(function(d){
   100|    var inviteCode = d.invite_code || '';
   101|    return apiFetch('/api/push-wechat', {
   102|      method: 'POST',
   103|      headers: {'Content-Type': 'application/json'},
   104|      body: JSON.stringify({
   105|        job_id: jobId,
   106|        invite_code: inviteCode,
   107|        user_name: name
   108|      })
   109|    });
   110|  }).then(function(d){
   111|    if(d.success){
   112|      toast('已加入推送队列，打开微信客户端自动发送到群');
   113|    } else {
   114|      toast(d.message || d.error || '推送失败');
   115|    }
   116|  }).catch(function(){ toast('推送失败，请重试'); });
   117|}
   118|
// ===== 页面切换（兼容新旧布局） =====
var screenNames = ['Login','Tpl','Form','Progress','Finish','Settings','History'];

window.showScreen = function showScreen(name){
  screenNames.forEach(function(s){
    var el = document.getElementById('screen'+s);
    if(el) el.classList.remove('active');
  });
  var el = document.getElementById('screen'+name);
  if(el) el.classList.add('active');

  // 登录页显示/隐藏三明治结构
  var sandwich = document.getElementById('sandwich');
  var loginScreen = document.getElementById('screenLogin');
  if(name === 'Login'){
    if(loginScreen) loginScreen.style.display = '';
    loginScreen.classList.add('active');
    if(sandwich) sandwich.style.display = 'none';
    return;
  } else {
    if(sandwich) sandwich.style.display = 'flex';
    if(loginScreen) loginScreen.style.display = 'none';
    loginScreen.classList.remove('active');
  }

  // 步骤指示器
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

// 底部导航高亮
  updateNavTab(name);
}

// ===== 底部Tab切换（V4.0三明治） =====
window.switchTab = function switchTab(tab){
  var map = {home:'Tpl', history:'History', mine:'Settings'};
  var screen = map[tab];
  if(screen){
    if(screen === 'History') loadHistory();
    if(screen === 'Settings') loadSettings();
    showScreen(screen);
  }
  var items = document.querySelectorAll('.nav-item');
  items.forEach(function(it){ it.classList.toggle('active', it.dataset.tab === tab); });
}

window.updateNavTab = function updateNavTab(name){
  var map = {Tpl:'home', History:'history', Settings:'mine'};
  var tab = map[name];
  if(!tab) return;
  var items = document.querySelectorAll('.nav-item');
  items.forEach(function(it){ it.classList.toggle('active', it.dataset.tab === tab); });
}

window.goStep = function goStep(name){
   145|  if(name==='tpl') showScreen('Tpl');
   146|}
   147|
   148|window.goHome = function goHome(){
   149|  showScreen('Tpl');
   150|  if(pollTimer) clearInterval(pollTimer);
   151|}
   152|
   153|// ===== 模板缓存 =====
   154|window.getCachedTemplates = function getCachedTemplates(){
   155|  try {
   156|    var cached = localStorage.getItem('tpl_cache');
   157|    var ts = localStorage.getItem('tpl_cache_ts');
   158|    if(cached && ts){
   159|      var age = Date.now() - parseInt(ts);
   160|      if(age < 300000) return JSON.parse(cached); // 5分钟缓存
   161|    }
   162|  } catch(e){}
   163|  return null;
   164|}
   165|
   166|window.setCachedTemplates = function setCachedTemplates(data){
   167|  try {
   168|    localStorage.setItem('tpl_cache', JSON.stringify(data));
   169|    localStorage.setItem('tpl_cache_ts', String(Date.now()));
   170|  } catch(e){}
   171|}
   172|
   173|// ===== 初始化 =====
   174|window.init = function init(){
   175|  var ref = getUrlParam('ref');
   176|  if(ref){
   177|    localStorage.setItem('invite_ref', ref);
   178|    document.getElementById('loginHint').textContent = '🎁 好友邀请你来玩！';
   179|  }
   180|  autoLogin();
   181|
   182|  // 先尝试从缓存加载模板
   183|  var cached = getCachedTemplates();
   184|  if(cached && cached.length){
   185|    templates = cached;
   186|    renderTplGrid();
   187|  }
   188|
   189|  // 再从服务器拉取最新
   190|  apiFetch('/api/templates').then(function(d){
   191|    var list = d.templates || [];
   192|    if(list.length){
   193|      templates = list;
   194|      renderTplGrid();
   195|      setCachedTemplates(list);
   196|    }
   197|  }).catch(function(){
   198|    // 如果缓存有就用缓存，没有则显示错误
   199|    if(!templates.length){
   200|      showError('tplError', function(){ init(); });
   201|    }
   202|  });
   203|}
   204|
   205|// ===== 设置页 =====
   206|window.loadSettings = function loadSettings(){
   207|  var skeleton = document.getElementById('settingsSkeleton');
   208|  var content = document.getElementById('settingsContent');
   209|  var errEl = document.getElementById('settingsError');
   210|  hideError('settingsError');
   211|  if(skeleton) skeleton.style.display = 'flex';
   212|  if(content) content.style.display = 'none';
   213|
   214|  var token = localStorage.getItem('user_token');
   215|  if(!token){ toast('请先登录'); return; }
   216|  apiFetch('/api/me').then(function(d){
   217|    if(skeleton) skeleton.style.display = 'none';
   218|    if(content){ content.style.display = 'block'; }
   219|    document.getElementById('setPhone').textContent = d.phone || '--';
   220|    document.getElementById('setName').textContent = d.name || '--';
   221|    document.getElementById('setRole').textContent = d.role || '--';
   222|    document.getElementById('setApiKey').textContent = d.api_key || '--';
   223|  }).catch(function(){
   224|    if(skeleton) skeleton.style.display = 'none';
   225|    showError('settingsError', function(){ loadSettings(); });
   226|  });
   227|}
   228|
   229|// ===== 历史页 =====
   230|var _historyPage = 0;
   231|var _historyPageSize = 20;
   232|var _historyHasMore = true;
   233|
   234|window.loadHistory = function loadHistory(){
   235|  var skeleton = document.getElementById('historySkeleton');
   236|  var list = document.getElementById('historyList');
   237|  var errEl = document.getElementById('historyError');
   238|  hideError('historyError');
   239|  _historyPage = 0;
   240|  _historyHasMore = true;
   241|  if(skeleton) skeleton.style.display = 'block';
   242|  if(list) list.innerHTML = '';
   243|  var token = localStorage.getItem('user_token');
   244|  if(!token){ toast('请先登录'); return; }
   245|  fetchHistoryPage();
   246|}
   247|
   248|window.fetchHistoryPage = function fetchHistoryPage(){
   249|  var skeleton = document.getElementById('historySkeleton');
   250|  var list = document.getElementById('historyList');
   251|  var loadMore = document.getElementById('historyLoadMore');
   252|  if(loadMore) loadMore.querySelector('button').disabled = true;
   253|  _historyPage += 1;
   254|  var token = localStorage.getItem('user_token');
   255|  if(!token){ toast('请先登录'); return; }
   256|  apiFetch('/api/history?page=' + _historyPage + '&size=' + _historyPageSize).then(function(d){
   257|    if(skeleton) skeleton.style.display = 'none';
   258|    if(!list) return;
   259|    var items = d.history || [];
   260|    var totalCount = d.total || items.length;
   261|    // 第一次加载且无数据
   262|    if(!items.length && _historyPage === 1){
   263|      list.innerHTML = '<div style="text-align:center;padding:40px 20px;color:rgba(255,255,255,.2);font-size:14px;">还没有生成过视频<br><span style="font-size:12px;">去选个模板试试吧</span></div>';
   264|      list.style.display = 'flex';
   265|      if(loadMore) loadMore.style.display = 'none';
   266|      return;
   267|    }
   268|    var html = '';
   269|    for(var i=0; i<items.length; i++){
   270|      var h = items[i];
   271|      html += '<div class="history-item">';
   272|      html += '<div class="hi-icon">🎬</div>';
   273|      html += '<div class="hi-info"><div class="hi-title">' + (h.title || h.brand || '未命名视频') + '</div>' + (h.created_at || '') + '</div>';
   274|      html += '<div class="hi-action" onclick="event.stopPropagation();window.open(\''+API+'/api/download/'+h.job_id+'\')">⬇</div>';
   275|      html += '</div>';
   276|    }
   277|    // 如果是第一页直接覆盖，否则追加
   278|    if(_historyPage === 1){
   279|      list.innerHTML = html;
   280|    } else {
   281|      list.innerHTML += html;
   282|    }
   283|    list.style.display = 'flex';
   284|    _historyHasMore = items.length >= _historyPageSize;
   285|    if(!loadMore){
   286|      var div = document.createElement('div');
   287|      div.id = 'historyLoadMore';
   288|      div.className = 'history-load-more';
   289|      div.innerHTML = '<button onclick="fetchHistoryPage()">📋 加载更多</button>';
   290|      list.parentNode.appendChild(div);
   291|      loadMore = div;
   292|    }
   293|    var btn = loadMore.querySelector('button');
   294|    if(_historyHasMore){
   295|      loadMore.style.display = 'block';
   296|      btn.disabled = false;
   297|      btn.textContent = '📋 加载更多';
   298|    } else {
   299|      loadMore.style.display = 'block';
   300|      btn.disabled = true;
   301|      btn.textContent = '— 已加载全部 —';
   302|    }
   303|  }).catch(function(){
   304|    if(skeleton) skeleton.style.display = 'none';
   305|    showError('historyError', function(){ loadHistory(); });
   306|  });
   307|}
   308|
   309|})();
   310|