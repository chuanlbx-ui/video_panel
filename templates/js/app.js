(function(){
  'use strict';

const API = '/video-panel';
let user = null;
let template = null;
let templates = [];
let jobId = null;
let pollTimer = null;
let variants = [];
let variantIdx = 0;

window.toast = function toast(msg){
  const t = document.getElementById('toast');
  if(!t) return;
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(function(){ t.classList.remove('show'); }, 2500);
}

// ===== 分享裂变 =====

window.getUrlParam = function getUrlParam(name){
  var match = location.search.match(new RegExp('[?&]' + name + '=([^&]*)'));
  return match ? decodeURIComponent(match[1]) : '';
}

  var token = localStorage.getItem('user_token');
  if(!token){ toast('请先登录'); return; }
  fetch(API + '/api/invite-code', {headers:{'Authorization':'Bearer '+token}})
  .then(function(r){ return r.json(); })
  .then(function(d){
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

  var token = localStorage.getItem('user_token');
  var name = localStorage.getItem('user_name') || '';
  if(!token || !jobId){ toast('请先生成视频'); return; }
  fetch(API + '/api/invite-code', {headers:{'Authorization':'Bearer '+token}})
  .then(function(r){ return r.json(); })
  .then(function(d){
    var inviteCode = d.invite_code || '';
    return fetch(API + '/api/push-wechat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        job_id: jobId,
        invite_code: inviteCode,
        user_name: name
      })
    });
  }).then(function(r){ return r.json(); })
  .then(function(d){
    if(d.success){
      toast('已加入推送队列，打开微信客户端自动发送到群');
    } else {
      toast(d.message || d.error || '推送失败');
    }
  }).catch(function(){ toast('推送失败，请重试'); });
}

// ===== 登录/注册 Tab 切换 =====
  document.querySelectorAll('.login-tab').forEach(function(t){ t.classList.toggle('active', t.dataset.tab===tab); });
  document.getElementById('loginForm').style.display = tab==='login' ? '' : 'none';
  document.getElementById('registerForm').style.display = tab==='register' ? '' : 'none';
  document.getElementById('loginError').classList.remove('show');
  document.getElementById('regError').classList.remove('show');
  var hint = document.getElementById('loginHint');
  hint.textContent = tab==='login' ? '输入手机号和密码即可登录' : '注册后即可免费使用';
}

// ===== 登录 =====
document.getElementById('loginBtn').addEventListener('click', function(){
  var phone = document.getElementById('loginPhone').value.trim();
  var password = document.getElementById('loginPassword').value;
  var errEl = document.getElementById('loginError');
  errEl.classList.remove('show');
  if(!phone){ errEl.textContent='请输入手机号'; errEl.classList.add('show'); return; }
  var btn = this;
  btn.disabled = true;
  btn.textContent = '登录中...';
  fetch(API + '/api/login', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({phone: phone, password: password, ref: getUrlParam('ref')})
  }).then(function(r){ return r.json(); })
  .then(function(d){
    if(d.token){
      user = d;
      localStorage.setItem('user_token', d.token);
      localStorage.setItem('g_token', d.token);
      localStorage.setItem('user_name', d.name);
      document.getElementById('userInfo').innerHTML = '&#128075; <strong>' + d.name + '</strong>';
      showScreen('Tpl');
      toast('欢迎回来，' + d.name);
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

// ===== 注册 =====
document.getElementById('regBtn').addEventListener('click', function(){
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
  fetch(API + '/api/register', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name: name, phone: phone, password: password, ref: getUrlParam('ref')})
  }).then(function(r){ return r.json(); })
  .then(function(d){
    if(d.token){
      user = d;
      localStorage.setItem('user_token', d.token);
      localStorage.setItem('g_token', d.token);
      localStorage.setItem('user_name', d.name);
      document.getElementById('userInfo').innerHTML = '&#128075; <strong>' + d.name + '</strong>';
      showScreen('Tpl');
      toast('注册成功，欢迎 ' + d.name);
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

  var token = localStorage.getItem('user_token');
  if(!token) return;
  fetch(API + '/api/me', {headers:{'Authorization':'Bearer '+token}})
  .then(function(r){
    if(r.ok) return r.json();
    throw new Error('no');
  }).then(function(d){
    user = {name: d.name, token: token};
    document.getElementById('userInfo').innerHTML = '&#128075; <strong>' + d.name + '</strong>';
    showScreen('Tpl');
  }).catch(function(){
    localStorage.removeItem('user_token');
  });
}

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

window.init = function init(){
  var ref = getUrlParam('ref');
  if(ref){
    localStorage.setItem('invite_ref', ref);
    document.getElementById('loginHint').textContent = '🎁 好友邀请你来玩！';
  }
  autoLogin();
  fetch(API + '/api/templates').then(function(r){ return r.json(); })
  .then(function(d){
    templates = d.templates || [];
    renderTplGrid();
  }).catch(function(){});
}

var EMOJI_MAP = {
  'food_promo':'&#127832;','event_invite':'&#127914;','personal_ip':'&#128100;','personal_ip_v1':'&#128100;',
  'product_seed':'&#128230;','product_seed_v1':'&#128230;','sanqi_industry':'&#127807;',
  'association_invite':'&#129309;','store_promo':'&#127978;','store_promo_v1':'&#127978;',
  'farm_promo':'&#127794;','farm_promo_v1':'&#127794;','lixia_poster_v5':'&#128218;',
  'hengban_promo':'&#127916;','xinxue_course':'&#129504;','xiaohongshu_style':'&#128241;',
  'ai_daily_promo':'&#128250;'
};
var BADGE_MAP = {
  'food_promo':'餐饮&#183;促销','event_invite':'活动&#183;邀约','personal_ip':'个人IP','personal_ip_v1':'个人IP',
  'product_seed':'产品&#183;种草','product_seed_v1':'产品&#183;种草','sanqi_industry':'三七&#183;产业',
  'association_invite':'协会&#183;邀请','store_promo':'实体&#183;推广','store_promo_v1':'实体&#183;推广',
  'farm_promo':'农产品','farm_promo_v1':'农产品','lixia_poster_v5':'培训&#183;课程',
  'hengban_promo':'横屏&#183;宣传','xinxue_course':'心学&#183;课程','xiaohongshu_style':'小红书',
  'ai_daily_promo':'AI日报'
};

  var grid = document.getElementById('tplGrid');
  var html = '';
  for(var i=0; i<templates.length; i++){
    var t = templates[i];
    var emoji = EMOJI_MAP[t.id] || '&#127916;';
    var badge = BADGE_MAP[t.id] || '通用';
    var desc = t.description || '';
    html += '<div class="tpl-card" onclick="selectTemplate(\''+t.id+'\')" data-id="'+t.id+'">';
    html += '<div class="tpl-row"><div class="tpl-emoji">'+emoji+'</div>';
    html += '<div class="tpl-info"><div class="tpl-name">'+t.name+'</div>';
    html += '<div class="tpl-desc">'+desc+'</div>';
    html += '<span class="tpl-badge">'+badge+'</span></div></div></div>';
  }
  grid.innerHTML = html;
}

  for(var i=0; i<templates.length; i++){
    if(templates[i].id === tid){
      template = templates[i];
      break;
    }
  }
  if(!template) return;
  var cards = document.querySelectorAll('.tpl-card');
  for(var i=0; i<cards.length; i++) cards[i].classList.remove('selected');
  var card = document.querySelector('.tpl-card[data-id="'+tid+'"]');
  if(card) card.classList.add('selected');
  document.getElementById('formTitle').textContent = template.name + ' — 填信息';
  document.getElementById('f_brand').value = '';
  document.getElementById('f_desc').value = '';
  document.getElementById('f_phone').value = '';
  showScreen('Form');
}

document.getElementById('aiCopyBtn').addEventListener('click', function(){
  var brand = document.getElementById('f_brand').value.trim();
  if(!brand){ toast('请先填写品牌名/店名'); return; }
  var btn = this;
  btn.disabled = true;
  btn.textContent = 'AI生成中...';
  fetch(API + '/api/generate-variants', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({
      template_id: template.id,
      brand: brand,
      description: document.getElementById('f_desc').value,
      phone: document.getElementById('f_phone').value,
      address: '', value: '', price: ''
    })
  }).then(function(r){ return r.json(); })
  .then(function(d){
    variants = d.variants || [];
    showVariants(variants);
    btn.disabled = false;
    btn.textContent = '&#10024; AI生成3版文案';
  }).catch(function(){
    toast('AI生成失败');
    btn.disabled = false;
    btn.textContent = '&#10024; AI生成3版文案';
  });
});

  variantIdx = 0;
  var html = '';
  for(var i=0; i<vs.length; i++){
    var v = vs[i];
    var scenesHtml = '';
    for(var j=0; j<v.scenes.length; j++){
      scenesHtml += '<div style="font-size:12px;color:rgba(255,255,255,.5);line-height:1.6;padding:3px 0;border-bottom:1px solid rgba(255,255,255,.03);">&#127916; '+v.scenes[j].text+'</div>';
    }
    html += '<div class="variant-card" onclick="selectVariant('+i+')" data-idx="'+i+'" style="background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:14px;margin-bottom:10px;cursor:pointer;">';
    html += '<div style="font-size:13px;font-weight:600;color:#ffd54f;margin-bottom:6px;">'+v.style+'</div>';
    html += scenesHtml;
    html += '<div style="font-size:11px;color:rgba(255,255,255,.3);margin-top:6px;padding-top:6px;border-top:1px solid rgba(255,255,255,.06);font-style:italic;">&#127832;&#65039; '+v.voiceover+'</div>';
    html += '</div>';
  }
  document.getElementById('variantList').innerHTML = html;
  document.getElementById('variantOverlay').style.display = 'flex';
}

  variantIdx = idx;
  var cards = document.querySelectorAll('.variant-card');
  for(var i=0; i<cards.length; i++){
    cards[i].style.borderColor = 'rgba(255,255,255,.06)';
    cards[i].style.background = 'rgba(255,255,255,.03)';
  }
  var card = document.querySelector('.variant-card[data-idx="'+idx+'"]');
  if(card){ card.style.borderColor = '#ffd54f'; card.style.background = 'rgba(255,213,79,.08)'; }
}

  document.getElementById('variantOverlay').style.display = 'none';
}

document.getElementById('variantConfirmBtn').addEventListener('click', function(){
  if(!variants.length) return;
  var v = variants[variantIdx];
  if(!v) return;
  var texts = [];
  for(var i=0; i<v.scenes.length; i++) texts.push(v.scenes[i].text);
  document.getElementById('f_desc').value = texts.join('\n');
  toast('已选择「'+v.style+'」文案');
  closeVariant();
});

document.getElementById('generateBtn').addEventListener('click', generateVideo);
document.getElementById('previewCopyBtn').addEventListener('click', previewCopy);



})();
