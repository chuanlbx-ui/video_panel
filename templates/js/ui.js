(function(){
  'use strict';

  window.toast = function(msg){
    var t = document.getElementById('toast');
    if(!t) return;
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(function(){ t.classList.remove('show'); }, 2500);
  };

  window.getUrlParam = function(name){
    var match = location.search.match(new RegExp('[?&]' + name + '=([^&]*)'));
    return match ? decodeURIComponent(match[1]) : '';
  };

  // showScreen 在 app.js 中定义（含三明治布局切换），此处不再重复
  // 保留旧版兼容引用
  window.oldShowScreen = window.showScreen;

  window.goStep = function(name){
    if(name==='tpl') window.showScreen('Tpl');
  };

  window.goHome = function(){
    window.showScreen('Tpl');
    if(window.pollTimer) clearInterval(window.pollTimer);
  };

  window.EMOJI_MAP = {
    'food_promo':'&#127832;','event_invite':'&#127914;','personal_ip':'&#128100;','personal_ip_v1':'&#128100;',
    'product_seed':'&#128230;','product_seed_v1':'&#128230;','sanqi_industry':'&#127807;',
    'association_invite':'&#129309;','store_promo':'&#127978;','store_promo_v1':'&#127978;',
    'farm_promo':'&#127794;','farm_promo_v1':'&#127794;','lixia_poster_v5':'&#128218;',
    'hengban_promo':'&#127916;','xinxue_course':'&#129504;','xiaohongshu_style':'&#128241;',
    'ai_daily_promo':'&#128250;'
  };
  window.BADGE_MAP = {
    'food_promo':'餐饮&#183;促销','event_invite':'活动&#183;邀约','personal_ip':'个人IP','personal_ip_v1':'个人IP',
    'product_seed':'产品&#183;种草','product_seed_v1':'产品&#183;种草','sanqi_industry':'三七&#183;产业',
    'association_invite':'协会&#183;邀请','store_promo':'实体&#183;推广','store_promo_v1':'实体&#183;推广',
    'farm_promo':'农产品','farm_promo_v1':'农产品','lixia_poster_v5':'培训&#183;课程',
    'hengban_promo':'横屏&#183;宣传','xinxue_course':'心学&#183;课程','xiaohongshu_style':'小红书',
    'ai_daily_promo':'AI日报'
  };

  window.escapeHtml = function(text){
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
  };

  window.formatTime = function(isoStr){
    if(!isoStr) return '';
    try {
      var d = new Date(isoStr);
      var month = (d.getMonth()+1).toString().padStart(2,'0');
      var day = d.getDate().toString().padStart(2,'0');
      var hour = d.getHours().toString().padStart(2,'0');
      var min = d.getMinutes().toString().padStart(2,'0');
      return month+'月'+day+'日 '+hour+':'+min;
    } catch(e){ return isoStr; }
  };

  window.formatFileSize = function(bytes){
    if(!bytes || bytes === 0) return '未知大小';
    if(bytes < 1024) return bytes + 'B';
    if(bytes < 1024*1024) return (bytes/1024).toFixed(1) + 'KB';
    return (bytes/(1024*1024)).toFixed(1) + 'MB';
  };

})();
