(function(){
  'use strict';

  // ===== 模板网格 =====

  // ===== 搜索/筛选功能 =====
  window._allTemplates = [];

  window.filterTemplates = function(){
    var kw = (document.getElementById('tplSearchInput').value || '').trim().toLowerCase();
    var activeTag = document.querySelector('.tpl-tag.active');
    var tagFilter = activeTag ? activeTag.getAttribute('data-tag') || '' : '';

    var filtered = window._allTemplates;
    if(kw){
      filtered = filtered.filter(function(t){
        var name = (t.name || '').toLowerCase();
        var desc = (t.description || '').toLowerCase();
        var badge = (window.BADGE_MAP[t.id] || '').toLowerCase();
        return name.indexOf(kw) !== -1 || desc.indexOf(kw) !== -1 || badge.indexOf(kw) !== -1;
      });
    }
    if(tagFilter){
      filtered = filtered.filter(function(t){
        var badge = (window.BADGE_MAP[t.id] || '').toLowerCase();
        return badge.indexOf(tagFilter.toLowerCase()) !== -1;
      });
    }
    window.renderFilteredTplGrid(filtered);
  };

  window.renderFilteredTplGrid = function(items){
    var grid = document.getElementById('tplGrid');
    if(!items || !items.length){
      grid.innerHTML = '<div style="text-align:center;padding:40px 20px;color:rgba(255,255,255,.2);font-size:14px;">😕 没有找到匹配的模板</div>';
      return;
    }
    var html = '';
    for(var i=0; i<items.length; i++){
      var t = items[i];
      var emoji = window.EMOJI_MAP[t.id] || '&#127916;';
      var badge = window.BADGE_MAP[t.id] || '通用';
      var desc = t.description || '';
      html += '<div class="tpl-card" onclick="selectTemplate(\''+t.id+'\')" data-id="'+t.id+'">';
      html += '<div class="tpl-row"><div class="tpl-emoji">'+emoji+'</div>';
      html += '<div class="tpl-info"><div class="tpl-name">'+t.name+'</div>';
      html += '<div class="tpl-desc">'+desc+'</div>';
      html += '<span class="tpl-badge">'+badge+'</span></div></div></div>';
    }
    grid.innerHTML = html;
  };

  window.renderTplTags = function(templates){
    var tagSet = {};
    for(var i=0; i<templates.length; i++){
      var badge = window.BADGE_MAP[templates[i].id] || '通用';
      var cat = badge.split('\u00b7')[0] || badge;
      tagSet[cat] = true;
    }
    var tags = Object.keys(tagSet).sort();
    var el = document.getElementById('tplTags');
    var html = '';
    for(var i=0; i<tags.length; i++){
      html += '<span class="tpl-tag" data-tag="'+tags[i]+'" onclick="filterByTag(this)">'+tags[i]+'</span>';
    }
    el.innerHTML = html;
  };

  window.filterByTag = function(el){
    var isActive = el.classList.contains('active');
    document.querySelectorAll('.tpl-tag').forEach(function(t){ t.classList.remove('active'); });
    if(!isActive) el.classList.add('active');
    window.filterTemplates();
  };

  window.renderTplGrid = function(){
    window._allTemplates = window.templates.slice();
    window.renderFilteredTplGrid(window._allTemplates);
    window.renderTplTags(window._allTemplates);
  };

  window.selectTemplate = function(tid){
    for(var i=0; i<window.templates.length; i++){
      if(window.templates[i].id === tid){
        window.template = window.templates[i];
        break;
      }
    }
    if(!window.template) return;
    var cards = document.querySelectorAll('.tpl-card');
    for(var i=0; i<cards.length; i++) cards[i].classList.remove('selected');
    var card = document.querySelector('.tpl-card[data-id="'+tid+'"]');
    if(card) card.classList.add('selected');
    document.getElementById('formTitle').textContent = window.template.name + ' — 填信息';
    document.getElementById('f_brand').value = '';
    document.getElementById('f_desc').value = '';
    document.getElementById('f_phone').value = '';
    window.showScreen('Form');
  };

  // ===== AI生成3版文案 =====
  document.addEventListener('DOMContentLoaded', function(){
    var aiCopyBtn = document.getElementById('aiCopyBtn');
    if(aiCopyBtn){
      aiCopyBtn.addEventListener('click', function(){
        var brand = document.getElementById('f_brand').value.trim();
        if(!brand){ window.toast('请先填写品牌名/店名'); return; }
        var btn = this;
        btn.disabled = true;
        btn.textContent = 'AI生成中...';
        fetch(window.API + '/api/generate-variants', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({
            template_id: window.template.id,
            brand: brand,
            description: document.getElementById('f_desc').value,
            phone: document.getElementById('f_phone').value,
            address: '', value: '', price: ''
          })
        }).then(function(r){ return r.json(); })
        .then(function(d){
          window.variants = d.variants || [];
          window.showVariants(window.variants);
          btn.disabled = false;
          btn.textContent = '&#10024; AI生成3版文案';
        }).catch(function(){
          window.toast('AI生成失败');
          btn.disabled = false;
          btn.textContent = '&#10024; AI生成3版文案';
        });
      });
    }
  });

  // ===== 文案变体弹窗 =====
  window.showVariants = function(vs){
    window.variantIdx = 0;
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
  };

  window.selectVariant = function(idx){
    window.variantIdx = idx;
    var cards = document.querySelectorAll('.variant-card');
    for(var i=0; i<cards.length; i++){
      cards[i].style.borderColor = 'rgba(255,255,255,.06)';
      cards[i].style.background = 'rgba(255,255,255,.03)';
    }
    var card = document.querySelector('.variant-card[data-idx="'+idx+'"]');
    if(card){ card.style.borderColor = '#ffd54f'; card.style.background = 'rgba(255,213,79,.08)'; }
  };

  window.closeVariant = function(){
    document.getElementById('variantOverlay').style.display = 'none';
  };

  document.addEventListener('DOMContentLoaded', function(){
    var variantConfirmBtn = document.getElementById('variantConfirmBtn');
    if(variantConfirmBtn){
      variantConfirmBtn.addEventListener('click', function(){
        var v = window.variants[window.variantIdx];
        if(!v) return;
        var texts = [];
        for(var i=0; i<v.scenes.length; i++) texts.push(v.scenes[i].text);
        document.getElementById('f_desc').value = texts.join('\n');
        window.toast('已选择「'+v.style+'」文案，可在文本框继续编辑');
        window.closeVariant();
      });
    }
  });

  // ===== V5.0: AI智能生成 =====
  window.fillAiExample = function(text){
    document.getElementById('aiInput').value = text;
    document.getElementById('aiInput').focus();
  };

  window.aiOneShot = function(){
    var text = document.getElementById('aiInput').value.trim();
    if(!text){ window.toast('请先输入一句话描述你想要的内容'); return; }
    var btn = document.getElementById('aiGoBtn');
    btn.disabled = true;
    btn.textContent = '⏳ AI分析中...';
    var custom = window.getCustomSettings();
    fetch(window.API + '/api/one-shot-preview', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        text: text, phone:'', address:'',
        user_bg: custom.user_bg,
        user_color_scheme: custom.user_color_scheme,
        user_brand_watermark: custom.user_brand_watermark,
        user_bg_scenes: custom.user_bg_scenes
      })
    }).then(function(r){ return r.json(); })
    .then(function(d){
      btn.disabled = false;
      btn.textContent = '🚀 智能生成';
      if(d.error){
        window.toast(d.error);
        return;
      }
      window._aiPreviewData = d;
      window.showAiModal(d);
      window.saveAiHistory(text, d.job_id || '', d.brand);
    }).catch(function(){
      btn.disabled = false;
      btn.textContent = '🚀 智能生成';
      window.toast('AI分析失败，请重试');
    });
  };

  // V5.1: 展示文案预览弹窗
  window.showAiModal = function(data){
    var cp = data.copy_preview || {};
    var scenes = cp.scenes || {};
    var sceneList = cp.scene_list || [];
    var voiceover = cp.voiceover || '';

    document.getElementById('aiModalTpl').textContent = '📌 匹配模板：' + (data.matched_template?.name || '');

    var scenesHtml = '';
    var sceneKeys = Object.keys(scenes);
    sceneKeys.forEach(function(k, i){
      var v = scenes[k];
      var line1 = (typeof v === 'object') ? (v.line1 || '') : String(v);
      var line2 = (typeof v === 'object') ? (v.line2 || '') : '';
      scenesHtml += '<div class="ai-modal-section">';
      scenesHtml += '<div class="ai-modal-label">🎬 场景' + (i+1) + '</div>';
      scenesHtml += '<textarea class="ai-modal-textarea scene-line" data-scene="' + k + '" data-line="line1" rows="2">' + window.escapeHtml(line1) + '</textarea>';
      if(line2){
        scenesHtml += '<textarea class="ai-modal-textarea scene-line" data-scene="' + k + '" data-line="line2" rows="2" style="margin-top:4px;">' + window.escapeHtml(line2) + '</textarea>';
      }
      scenesHtml += '</div>';
    });
    document.getElementById('aiModalScenes').innerHTML = scenesHtml;
    document.getElementById('aiModalVoiceover').value = voiceover;

    document.getElementById('aiModalOverlay').classList.add('show');
  };

  window.aiModalCancel = function(){
    document.getElementById('aiModalOverlay').classList.remove('show');
  };

  window.aiModalApply = function(){
    var btn = document.getElementById('aiModalApplyBtn');
    btn.disabled = true;
    btn.textContent = '⏳ 提交中...';

    var data = window._aiPreviewData;
    if(!data){
      window.toast('预览数据丢失，请重新生成');
      btn.disabled = false;
      btn.textContent = '✅ 确认生成';
      return;
    }

    var sceneTextareas = document.querySelectorAll('.scene-line');
    var scenesData = {};
    sceneTextareas.forEach(function(ta){
      var scene = ta.getAttribute('data-scene');
      var line = ta.getAttribute('data-line');
      if(!scenesData[scene]) scenesData[scene] = {};
      scenesData[scene][line] = ta.value;
    });

    var voiceoverText = document.getElementById('aiModalVoiceover').value;

    document.getElementById('aiModalOverlay').classList.remove('show');

    var text = document.getElementById('aiInput').value.trim();
    var custom = window.getCustomSettings();

    fetch(window.API + '/api/one-shot-apply', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        text: text,
        phone: '',
        address: '',
        quality: 'standard',
        scenes_text: scenesData,
        voiceover_text: voiceoverText,
        user_bg: custom.user_bg,
        user_color_scheme: custom.user_color_scheme,
        user_brand_watermark: custom.user_brand_watermark,
        user_bg_scenes: custom.user_bg_scenes
      })
    }).then(function(r){ return r.json(); })
    .then(function(d){
      btn.disabled = false;
      btn.textContent = '✅ 确认生成';
      if(d.error){
        window.toast(d.error);
        return;
      }
      window.jobId_global = d.job_id;
      window.showScreen('Progress');
      window.startProgress();
      window.pollStatus(d.job_id);
      var hist = JSON.parse(localStorage.getItem('ai_history') || '[]');
      for(var i=0; i<hist.length; i++){
        if(hist[i].job_id === d.job_id){ hist[i].status = 'rendering'; break; }
      }
      localStorage.setItem('ai_history', JSON.stringify(hist));
    }).catch(function(){
      btn.disabled = false;
      btn.textContent = '✅ 确认生成';
      window.toast('提交失败，请重试');
    });
  };

  window.saveAiHistory = function(text, jobId, brand){
    var hist = JSON.parse(localStorage.getItem('ai_history') || '[]');
    hist.unshift({text: text, job_id: jobId, brand: brand, time: Date.now(), status: 'preview'});
    if(hist.length > 3) hist = hist.slice(0, 3);
    localStorage.setItem('ai_history', JSON.stringify(hist));
    window.renderAiHistory();
  };

  window.renderAiHistory = function(){
    var hist = JSON.parse(localStorage.getItem('ai_history') || '[]');
    var el = document.getElementById('aiHistory');
    if(!hist.length){ el.innerHTML = ''; return; }
    var html = '<div class="ai-history-title">📋 最近生成</div>';
    for(var i=0; i<hist.length; i++){
      var h = hist[i];
      var brand = h.brand || h.text.slice(0,12);
      var redoBtn = h.status === 'preview'
        ? '<span class="redo" onclick="redoAiHistory('+i+')">重新生成</span>'
        : '<span class="redo">查看</span>';
      html += '<div class="ai-history-item" onclick="redoAiHistory('+i+')">' + brand + redoBtn + '</div>';
    }
    el.innerHTML = html;
  };

  window.redoAiHistory = function(idx){
    var hist = JSON.parse(localStorage.getItem('ai_history') || '[]');
    if(!hist[idx]) return;
    document.getElementById('aiInput').value = hist[idx].text;
    window.aiOneShot();
  };

  // ===== 表单文案编辑增强 =====
  document.addEventListener('DOMContentLoaded', function(){
    var formScreen = document.getElementById('screenForm');
    if(formScreen){
      var descGroup = formScreen.querySelector('.form-group:first-child');
      var descArea = document.getElementById('f_desc');
      if(descArea && descArea.parentNode){
        var regenBtn = document.createElement('div');
        regenBtn.style.cssText = 'display:flex;gap:6px;margin-top:6px;';
        regenBtn.innerHTML = '<button onclick="regenerateCopy()" style="flex:1;padding:8px;border-radius:8px;border:1px solid rgba(255,213,79,.15);background:linear-gradient(135deg,rgba(255,213,79,.08),rgba(255,213,79,.03));color:#ffd54f;font-size:12px;font-weight:600;cursor:pointer;">🔄 重新生成</button>';
        regenBtn.innerHTML += '<button onclick="clearDesc()" style="padding:8px 12px;border-radius:8px;border:1px solid rgba(255,255,255,.06);background:rgba(255,255,255,.03);color:rgba(255,255,255,.4);font-size:12px;cursor:pointer;">清空</button>';
        descArea.parentNode.insertBefore(regenBtn, descArea.nextSibling);
      }
    }
  });

  window.regenerateCopy = function(){
    document.getElementById('aiCopyBtn').click();
  };

  window.clearDesc = function(){
    document.getElementById('f_desc').value = '';
    window.toast('已清空文案');
  };

  // ===== 搜索框事件绑定 =====
  document.addEventListener('DOMContentLoaded', function(){
    var searchInput = document.getElementById('tplSearchInput');
    if(searchInput){
      searchInput.addEventListener('input', function(){
        window.filterTemplates();
      });
    }
  });

})();
