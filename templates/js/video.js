(function(){
  'use strict';

    window.generateVideo = function generateVideo(){
      if(!template){ toast('请先选择模板'); return; }
      var brand = document.getElementById('f_brand').value.trim();
      if(!brand){ toast('请填写品牌名/店名'); return; }
      showScreen('Progress');
      startProgress();
      fetch(API + '/api/v4/generate', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          template_id: template.id,
          brand: brand,
          desc: document.getElementById('f_desc').value,
          phone: document.getElementById('f_phone').value,
          variant: window.selectedIndustryVariant || null
        })
      }).then(function(r){ return r.json(); })
      .then(function(d){
        if(d.job_id){
          jobId = d.job_id;
          pollStatus(d.job_id);
        } else {
          setFail(d.error || '生成失败');
        }
      }).catch(function(){ setFail('网络错误'); });
    }
    
    window.startProgress = function startProgress(){
      document.getElementById('progressText').textContent = '正在生成视频...';
      document.getElementById('progressHint').textContent = 'AI写文案 + 配音 + 合成中';
      updateProgress(10);
    }
    
    window.updateProgress = function updateProgress(pct){
      document.getElementById('progressPct').textContent = pct + '%';
      var circle = document.getElementById('progressCircle');
      var c = 2 * Math.PI * 41;
      circle.style.strokeDashoffset = c - (pct/100) * c;
    }
    
    window.setFail = function setFail(msg){
      document.getElementById('progressText').textContent = '&#10060; ' + msg;
      document.getElementById('progressHint').textContent = '点"再做一条"重试';
    }
    
    window.pollStatus = function pollStatus(id){
      if(pollTimer) clearInterval(pollTimer);
      var t = 0;
      pollTimer = setInterval(function(){
        t += 3;
        fetch(API + '/api/jobs/' + id).then(function(r){ return r.json(); })
        .then(function(d){
          if(d.status === 'completed'){
            clearInterval(pollTimer);
            updateProgress(100);
            document.getElementById('progressText').textContent = '&#9989; 完成！';
            if(window._aiJobDone) window._aiJobDone(id);
            setTimeout(function(){ showFinish(id); }, 500);
          } else if(d.status === 'failed'){
            clearInterval(pollTimer);
            setFail(d.error || '生成失败');
          } else {
            // 优先使用后端真实progress字段
            var p = d.progress ? parseInt(d.progress) : 0;
            if(p <= 0) p = Math.min(15 + t * 3, 95);
            updateProgress(p);
            // 进度提示随真实进度变化
            if(p < 30) document.getElementById('progressHint').textContent = '正在制作画面...';
            else if(p < 60) document.getElementById('progressHint').textContent = '配音+BGM合成中...';
            else if(p < 90) document.getElementById('progressHint').textContent = '最终渲染中...';
            else document.getElementById('progressHint').textContent = '马上就好...';
          }
        }).catch(function(){});
      }, 3000);
    }
    
    window.showFinish = function showFinish(id){
      showScreen('Finish');
      var video = document.getElementById('finishVideo');
      video.src = API + '/api/download/' + id;
      video.load();
      document.getElementById('saveBtn').onclick = function(){
        var a = document.createElement('a');
        a.href = video.src;
        a.download = 'video_'+id+'.mp4';
        a.click();
      };
      document.getElementById('shareBtn').onclick = function(){
        if(navigator.share){
          navigator.share({title:'我的视频', text:'看我用AI做的视频！', url: video.src});
        } else {
          navigator.clipboard.writeText(video.src).then(function(){ toast('链接已复制'); });
        }
      };
      // 后台生成完成，移除badge
      var badge = document.getElementById('genBadge');
      if(badge){ badge.style.display = 'none'; }
      toast('&#9989; 视频生成完成！');
    }
    
    window.minimizeProgress = function minimizeProgress(){
      showScreen('Tpl');
      toast('⏳ 后台生成中，完成后通知你');
      var badge = document.getElementById('genBadge');
      if(!badge){
        badge = document.createElement('div');
        badge.id = 'genBadge';
        badge.innerHTML = '⏳ 生成中...';
        badge.style.cssText = 'position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:999;padding:6px 16px;border-radius:20px;background:rgba(255,213,79,0.15);border:1px solid rgba(255,213,79,0.2);color:#ffd54f;font-size:12px;cursor:pointer;';
        badge.onclick = function(){ showScreen('Progress'); };
        document.body.appendChild(badge);
      }
      badge.style.display = 'block';
    }
    
    document.addEventListener('DOMContentLoaded', init);
    
    // ===== V5.0: AI智能生成 =====
    window.fillAiExample = function fillAiExample(text){
      document.getElementById('aiInput').value = text;
      document.getElementById('aiInput').focus();
    }
    
    window.aiOneShot = function aiOneShot(){
      var text = document.getElementById('aiInput').value.trim();
      if(!text){ toast('请先输入一句话描述你想要的内容'); return; }
      var btn = document.getElementById('aiGoBtn');
      btn.disabled = true;
      btn.textContent = '⏳ AI分析中...';
      var custom = getCustomSettings();
      // V5.1: 改为调用预览接口
      fetch(API + '/api/one-shot-preview', {
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
        btn.textContent = '🚀';
        if(d.error){
          toast(d.error);
          return;
        }
        // V5.1: 保存预览数据并弹出编辑弹窗
        window._aiPreviewData = d;
        showAiModal(d);
        // 存到历史记录
        saveAiHistory(text, d.job_id || '', d.brand);
      }).catch(function(){
        btn.disabled = false;
        btn.textContent = '🚀';
        toast('AI分析失败，请重试');
      });
    }
    
    // V5.1: 展示文案预览弹窗
    window.showAiModal = function showAiModal(data){
      var cp = data.copy_preview || {};
      var scenes = cp.scenes || {};
      var sceneList = cp.scene_list || [];
      var voiceover = cp.voiceover || '';
    
      document.getElementById('aiModalTpl').textContent = '📌 匹配模板：' + (data.matched_template?.name || '');
    
      // 构建场景编辑区
      var scenesHtml = '';
      var sceneKeys = Object.keys(scenes);
      sceneKeys.forEach(function(k, i){
        var v = scenes[k];
        var line1 = (typeof v === 'object') ? (v.line1 || '') : String(v);
        var line2 = (typeof v === 'object') ? (v.line2 || '') : '';
        scenesHtml += '<div class="ai-modal-section">';
        scenesHtml += '<div class="ai-modal-label">🎬 场景' + (i+1) + '</div>';
        scenesHtml += '<textarea class="ai-modal-textarea scene-line" data-scene="' + k + '" data-line="line1" rows="2">' + escapeHtml(line1) + '</textarea>';
        if(line2){
          scenesHtml += '<textarea class="ai-modal-textarea scene-line" data-scene="' + k + '" data-line="line2" rows="2" style="margin-top:4px;">' + escapeHtml(line2) + '</textarea>';
        }
        scenesHtml += '</div>';
      });
      document.getElementById('aiModalScenes').innerHTML = scenesHtml;
      document.getElementById('aiModalVoiceover').value = voiceover;
    
      // 显示弹窗
      document.getElementById('aiModalOverlay').classList.add('show');
    }
    
    window.aiModalCancel = function aiModalCancel(){
      document.getElementById('aiModalOverlay').classList.remove('show');
    }
    
    window.aiModalApply = function aiModalApply(){
      var btn = document.getElementById('aiModalApplyBtn');
      btn.disabled = true;
      btn.textContent = '⏳ 提交中...';
    
      var data = window._aiPreviewData;
      if(!data){
        toast('预览数据丢失，请重新生成');
        btn.disabled = false;
        btn.textContent = '✅ 确认生成';
        return;
      }
    
      // 收集用户修改后的场景文案
      var sceneTextareas = document.querySelectorAll('.scene-line');
      var scenesData = {};
      sceneTextareas.forEach(function(ta){
        var scene = ta.getAttribute('data-scene');
        var line = ta.getAttribute('data-line');
        if(!scenesData[scene]) scenesData[scene] = {};
        scenesData[scene][line] = ta.value;
      });
    
      var voiceoverText = document.getElementById('aiModalVoiceover').value;
    
      // 关弹窗
      document.getElementById('aiModalOverlay').classList.remove('show');
    
      var text = document.getElementById('aiInput').value.trim();
      var custom = getCustomSettings();
    
      fetch(API + '/api/one-shot-apply', {
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
          toast(d.error);
          return;
        }
        // 切换到进度页面开始轮询
        jobId_global = d.job_id;
        showScreen('Progress');
        startProgress();
        pollStatus(d.job_id);
        // 更新历史记录
        var hist = JSON.parse(localStorage.getItem('ai_history') || '[]');
        for(var i=0; i<hist.length; i++){
          if(hist[i].job_id === d.job_id){ hist[i].status = 'rendering'; break; }
        }
        localStorage.setItem('ai_history', JSON.stringify(hist));
      }).catch(function(){
        btn.disabled = false;
        btn.textContent = '✅ 确认生成';
        toast('提交失败，请重试');
      });
    }
    
    window.saveAiHistory = function saveAiHistory(text, jobId, brand){
      var hist = JSON.parse(localStorage.getItem('ai_history') || '[]');
      hist.unshift({text: text, job_id: jobId, brand: brand, time: Date.now(), status: 'preview'});
      if(hist.length > 3) hist = hist.slice(0, 3);
      localStorage.setItem('ai_history', JSON.stringify(hist));
      renderAiHistory();
    }
    
    window.renderAiHistory = function renderAiHistory(){
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
    }
    
    window.redoAiHistory = function redoAiHistory(idx){
      var hist = JSON.parse(localStorage.getItem('ai_history') || '[]');
      if(!hist[idx]) return;
      document.getElementById('aiInput').value = hist[idx].text;
      aiOneShot();
    }
    
    var jobId_global = null;
    
    // 重写 pollStatus 以支持 aiOneShot 的 jobId
    var _origPollStatus = pollStatus;
    pollStatus = function(id){
      jobId_global = id;
      _origPollStatus(id);
      // 修改完成回调来更新历史记录
    };
    
    // ===== Canvas预览功能 =====
    var previewData = null;
    var previewIdx = 0;
    
    document.getElementById('previewBtn').addEventListener('click', function(){
      var brand = document.getElementById('f_brand').value.trim();
      if(!brand){ toast('请先填写品牌名/店名'); return; }
      if(!template){ toast('请先选择模板'); return; }
      var btn = this;
      btn.disabled = true;
      btn.textContent = '⏳ 加载预览...';
      // 重置编辑缓存
      previewTexts = {};
      fetch('/api/preview-canvas', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          template_id: template.id,
          brand: brand,
          desc: document.getElementById('f_desc').value,
          phone: document.getElementById('f_phone').value,
          scenes_text: null,  // 预览用AI生成文案
          variant: window.selectedIndustryVariant || null
        })
      }).then(function(r){ return r.json(); })
      .then(function(d){
        btn.disabled = false;
        btn.textContent = '👁 预览效果';
        if(d.error){ toast(d.error); return; }
        previewData = d.preview_data;
        if(!previewData || !previewData.scenes || !previewData.scenes.length){
          // 检查是否 fallback
          if(previewData && previewData.fallback){
            toast(previewData.message || '该模板暂不支持Canvas预览，请直接生成视频查看效果');
          } else {
            toast('该模板暂无预览数据');
          }
          return;
        }
        previewIdx = 0;
        document.getElementById('previewOverlay').style.display = 'flex';
        renderPreviewThumbs();
        drawPreviewScene(0);
      }).catch(function(){
        btn.disabled = false;
        btn.textContent = '👁 预览效果';
        toast('加载预览失败');
      });
    });
    
    window.closePreview = function closePreview(){
      document.getElementById('previewOverlay').style.display = 'none';
    }
    
    window.previewPrev = function previewPrev(){
      if(!previewData) return;
      previewIdx = (previewIdx - 1 + previewData.scenes.length) % previewData.scenes.length;
      drawPreviewScene(previewIdx);
    }
    
    window.previewNext = function previewNext(){
      if(!previewData) return;
      previewIdx = (previewIdx + 1) % previewData.scenes.length;
      drawPreviewScene(previewIdx);
    }
    
    window.renderPreviewThumbs = function renderPreviewThumbs(){
      var container = document.getElementById('previewThumbs');
      if(!previewData || !previewData.scenes) return;
      var html = '';
      for(var i=0; i<previewData.scenes.length; i++){
        var scene = previewData.scenes[i];
        var firstText = '';
        if(scene.elements && scene.elements.length){
          firstText = scene.elements[0].text || '';
        }
        html += '<div onclick="drawPreviewScene('+i+')" data-tidx="'+i+'" style="width:36px;height:64px;border-radius:6px;overflow:hidden;background:linear-gradient(180deg,'+(previewData.colors.bg_top||'#0a1628')+','+(previewData.colors.bg_bottom||'#060e1e')+');border:2px solid '+(i===previewIdx?'#ffd54f':'rgba(255,255,255,.06)')+';flex-shrink:0;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:7px;color:'+(previewData.colors.gold_text||'#ffd54f')+';text-align:center;padding:2px;line-height:1.2;transition:border-color .2s;">'+firstText.slice(0,8)+'</div>';
      }
      container.innerHTML = html;
    }
    
    // ===== 免费图库功能 =====
    var currentBgTab = 'upload';
    
    window.switchBgTab = function switchBgTab(tab){
      currentBgTab = tab;
      var upBtn = document.getElementById('bgTabUpload');
      var stBtn = document.getElementById('bgTabStock');
      var upArea = document.getElementById('uploadArea');
      var stArea = document.getElementById('stockArea');
      var grid = document.getElementById('bgImageGrid');
      if(tab === 'upload'){
        upBtn.style.borderColor = 'rgba(255,213,79,.3)';
        upBtn.style.background = 'linear-gradient(135deg,rgba(255,213,79,.08),rgba(255,213,79,.03))';
        upBtn.style.color = '#ffd54f';
        stBtn.style.borderColor = 'rgba(255,255,255,.06)';
        stBtn.style.background = 'rgba(255,255,255,.03)';
        stBtn.style.color = 'rgba(255,255,255,.5)';
        upArea.style.display = 'block';
        stArea.style.display = 'none';
        grid.style.display = 'grid';
      } else {
        stBtn.style.borderColor = 'rgba(255,213,79,.3)';
        stBtn.style.background = 'linear-gradient(135deg,rgba(255,213,79,.08),rgba(255,213,79,.03))';
        stBtn.style.color = '#ffd54f';
        upBtn.style.borderColor = 'rgba(255,255,255,.06)';
        upBtn.style.background = 'rgba(255,255,255,.03)';
        upBtn.style.color = 'rgba(255,255,255,.5)';
        upArea.style.display = 'none';
        stArea.style.display = 'block';
        grid.style.display = 'none';
        // 加载分类
        loadStockCategories();
      }
    }
    
    window.loadStockCategories = function loadStockCategories(){
      fetch(API + '/api/bg/stock-search', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({keyword:'', count:0})
      }).then(function(r){ return r.json(); })
      .then(function(d){
        var cats = d.categories || [];
        var html = '';
        cats.forEach(function(c){
          html += '<span onclick="searchStockByCategory(\''+c+'\')" style="padding:4px 10px;border-radius:12px;border:1px solid rgba(255,255,255,.06);background:rgba(255,255,255,.03);color:rgba(255,255,255,.45);font-size:11px;cursor:pointer;white-space:nowrap;">'+c+'</span>';
        });
        document.getElementById('stockCategories').innerHTML = html;
      }).catch(function(){});
    }
    
    window.searchStockByCategory = function searchStockByCategory(cat){
      document.getElementById('stockKeyword').value = cat;
      searchStockImages();
    }
    
    window.searchStockImages = function searchStockImages(){
      var kw = document.getElementById('stockKeyword').value.trim();
      if(!kw){ toast('请输入关键词'); return; }
      var resultsDiv = document.getElementById('stockResults');
      resultsDiv.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:20px;color:rgba(255,255,255,.2);font-size:13px;">⏳ 搜索中...</div>';
      fetch(API + '/api/bg/stock-search', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({keyword:kw, count:12})
      }).then(function(r){ return r.json(); })
      .then(function(d){
        var images = d.images || [];
        if(!images.length){
          resultsDiv.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:30px;color:rgba(255,255,255,.2);font-size:13px;">😕 未找到相关图片，试试其他关键词</div>';
          return;
        }
        var html = '';
        images.forEach(function(img, idx){
          html += '<div onclick="selectStockImage('+idx+')" class="stock-img-card" data-sidx="'+idx+'" style="border-radius:10px;overflow:hidden;border:2px solid rgba(255,255,255,.06);cursor:pointer;position:relative;aspect-ratio:16/9;background:#0a1628;transition:border-color .2s;">';
          html += '<img src="'+img.thumb_url+'" alt="'+img.description+'" style="width:100%;height:100%;object-fit:cover;display:block;" loading="lazy">';
          html += '<div style="position:absolute;bottom:0;left:0;right:0;padding:4px 6px;background:rgba(0,0,0,.5);font-size:9px;color:rgba(255,255,255,.5);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'+img.description+'</div>';
          html += '</div>';
        });
        resultsDiv.innerHTML = html;
        // 存储图片数据以供选择
        window._stockResults = images;
      }).catch(function(){
        resultsDiv.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:30px;color:rgba(255,255,255,.2);font-size:13px;">❌ 搜索失败，请重试</div>';
      });
    }
    
    // 回车键触发搜索
    document.addEventListener('DOMContentLoaded', function(){
      var kwInput = document.getElementById('stockKeyword');
      if(kwInput){
        kwInput.addEventListener('keyup', function(e){
          if(e.key === 'Enter') searchStockImages();
        });
      }
    });
    
    window.selectStockImage = function selectStockImage(idx){
      var images = window._stockResults || [];
      var img = images[idx];
      if(!img) return;
      // 高亮选中
      var cards = document.querySelectorAll('.stock-img-card');
      cards.forEach(function(c){ c.style.borderColor = 'rgba(255,255,255,.06)'; });
      var card = document.querySelector('.stock-img-card[data-sidx="'+idx+'"]');
      if(card) card.style.borderColor = '#ffd54f';
      // 添加到已选背景列表
      var item = {url: img.url, thumb_url: img.thumb_url, description: img.description, source: img.source || 'stock', duration: 4};
      var selectedList = JSON.parse(localStorage.getItem('bg_selected_list') || '[]');
      selectedList.push(item);
      localStorage.setItem('bg_selected_list', JSON.stringify(selectedList));
      refreshSelectedBg();
      toast('已添加到背景组合');
    }
    
    // ===== 预览文案编辑功能 =====
    var previewTexts = {};  // scene_id -> text (after editing)
    
    window.drawPreviewScene = function drawPreviewScene(idx){
      if(!previewData || !previewData.scenes || !previewData.scenes[idx]) return;
      previewIdx = idx;
      var scene = previewData.scenes[idx];
      var canvas = document.getElementById('previewCanvas');
      var container = canvas.parentElement;
      var W = 360;
      var H = 640;
      var dpr = window.devicePixelRatio || 1;
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      var ctx = canvas.getContext('2d');
      ctx.scale(dpr, dpr);
    
      var colors = previewData.colors;
    
      // 1) 绘制渐变背景
      var grad = ctx.createLinearGradient(0, 0, 0, H);
      grad.addColorStop(0, colors.bg_top || '#0a1628');
      grad.addColorStop(0.5, colors.bg_top || '#0a1628');
      grad.addColorStop(1, colors.bg_bottom || '#060e1e');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, W, H);
    
      // 装饰性粒子效果
      ctx.globalAlpha = 0.03;
      for(var p=0; p<20; p++){
        ctx.beginPath();
        ctx.arc(Math.random()*W, Math.random()*H, Math.random()*3+1, 0, Math.PI*2);
        ctx.fillStyle = colors.gold_text || '#ffd54f';
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    
      // 2) 绘制场景元素
      if(scene.elements){
        for(var e=0; e<scene.elements.length; e++){
          var el = scene.elements[e];
          if(!el.text) continue;
          // 如果用户编辑过文案，使用编辑后的
          var displayText = el.text;
          if(previewTexts[scene.scene_index] && previewTexts[scene.scene_index][el.key]){
            displayText = previewTexts[scene.scene_index][el.key];
          }
          if(!displayText) continue;
          var fontSize = el.font_size || 32;
          var x = (el.position.x !== undefined ? el.position.x : 0.1) * W;
          var y = (el.position.y !== undefined ? el.position.y : 0.4) * H;
          var color = el.color || colors.white_text || '#ffffff';
    
          var fontFamily = "'Noto Sans SC', 'PingFang SC', sans-serif";
          if(el.style && (el.style.indexOf('gold') >= 0 || el.style.indexOf('price') >= 0)){
            fontFamily = "'Noto Serif SC', 'Noto Sans SC', serif";
          }
    
          if(el.style && (el.style.indexOf('gold') >= 0 || el.style.indexOf('price') >= 0)){
            ctx.shadowColor = 'rgba(255,213,79,0.3)';
            ctx.shadowBlur = 20;
          } else {
            ctx.shadowColor = 'transparent';
            ctx.shadowBlur = 0;
          }
    
          ctx.font = 'bold ' + Math.round(fontSize) + 'px ' + fontFamily;
          ctx.textAlign = 'left';
          ctx.textBaseline = 'middle';
    
          if(el.style && el.style.indexOf('subtitle') >= 0){
            ctx.globalAlpha = 0.5;
          } else {
            ctx.globalAlpha = 1;
          }
    
          ctx.fillStyle = color;
          var lines = displayText.split('\\n');
          var lineHeight = fontSize * 1.3;
          for(var li=0; li<lines.length; li++){
            ctx.fillText(lines[li], x, y + li * lineHeight);
          }
        }
      }
    
      // reset
      ctx.shadowColor = 'transparent';
      ctx.shadowBlur = 0;
      ctx.globalAlpha = 1;
    
      // 3) 更新导航
      document.getElementById('previewSceneBadge').textContent = '场景 ' + (idx+1) + '/' + previewData.scenes.length;
      document.getElementById('previewSceneName').textContent = scene.scene_name || '';
      document.getElementById('previewCounter').textContent = (idx+1) + ' / ' + previewData.scenes.length;
    
      // 4) 更新缩略图选中状态
      var thumbs = document.querySelectorAll('#previewThumbs > div');
      for(var t=0; t<thumbs.length; t++){
        thumbs[t].style.borderColor = (t===idx) ? '#ffd54f' : 'rgba(255,255,255,.06)';
      }
    
      // 5) 更新文案编辑器
      updatePreviewTextEditor(scene);
    }
    
    window.updatePreviewTextEditor = function updatePreviewTextEditor(scene){
      if(!scene || !scene.elements || !scene.elements.length){
        document.getElementById('previewTextEditor').style.display = 'none';
        return;
      }
      document.getElementById('previewTextEditor').style.display = 'block';
      // 取第一个文本元素作为可编辑内容
      var firstEl = scene.elements[0];
      var text = firstEl.text || '';
      // 如果已编辑，使用编辑版
      if(previewTexts[scene.scene_index] && previewTexts[scene.scene_index][firstEl.key]){
        text = previewTexts[scene.scene_index][firstEl.key];
      }
      document.getElementById('previewSceneText').value = text;
    }
    
    window.applyPreviewTextEdit = function applyPreviewTextEdit(){
      var newText = document.getElementById('previewSceneText').value;
      var scene = previewData.scenes[previewIdx];
      if(!scene) return;
      if(!previewTexts[scene.scene_index]) previewTexts[scene.scene_index] = {};
      var firstEl = scene.elements[0];
      if(firstEl){
        previewTexts[scene.scene_index][firstEl.key] = newText;
      }
      drawPreviewScene(previewIdx);
      toast('预览已更新');
    }
    
    window.savePreviewTextToForm = function savePreviewTextToForm(){
      // 把所有编辑过的文案同步到表单的 f_desc
      var lines = [];
      for(var i=0; i<previewData.scenes.length; i++){
        var scene = previewData.scenes[i];
        if(!scene || !scene.elements || !scene.elements.length) continue;
        var firstEl = scene.elements[0];
        var text = firstEl.text || '';
        if(previewTexts[scene.scene_index] && previewTexts[scene.scene_index][firstEl.key]){
          text = previewTexts[scene.scene_index][firstEl.key];
        }
        lines.push(text);
      }
      document.getElementById('f_desc').value = lines.join('\n');
      toast('文案已同步到表单');
    }
    
    // ===== 表单文案编辑增强 =====
    // 修改确认文案时：选中文案后填入f_desc并可继续编辑
    document.addEventListener('DOMContentLoaded', function(){
      // 为AI生成3版文案按钮旁边增加"重新生成"按钮
      var formScreen = document.getElementById('screenForm');
      if(formScreen){
        var descGroup = formScreen.querySelector('.form-group:first-child');
        // 在f_desc下方添加"重新生成"按钮（在f_desc textarea后面）
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
    
    window.regenerateCopy = function regenerateCopy(){
      // 触发AI重新生成文案
      document.getElementById('aiCopyBtn').click();
    }
    
    window.clearDesc = function clearDesc(){
      document.getElementById('f_desc').value = '';
      toast('已清空文案');
    }
    
    // 修改variant确认：选择文案后填入f_desc（可继续编辑），同时增加"重新生成"提示
    document.getElementById('variantConfirmBtn').addEventListener('click', function(){
      if(!variants.length) return;
      var v = variants[variantIdx];
      if(!v) return;
      var texts = [];
      for(var i=0; i<v.scenes.length; i++) texts.push(v.scenes[i].text);
      document.getElementById('f_desc').value = texts.join('\n');
      toast('已选择「'+v.style+'」文案，可在文本框继续编辑');
      closeVariant();
    });
    
    // ===== 生成视频时传递自定义文案 =====
    var _origGenerateVideo = generateVideo;
    window.generateVideo = function generateVideo(){
      if(!template){ toast('请先选择模板'); return; }
      var brand = document.getElementById('f_brand').value.trim();
      if(!brand){ toast('请填写品牌名/店名'); return; }
    
      // 解析f_desc中的文案为scenes_text（按行分割）
      var descText = document.getElementById('f_desc').value.trim();
      var scenesText = null;
      if(descText){
        // 按行分割，每行作为一个场景文案
        var lines = descText.split('\n').filter(function(l){ return l.trim(); });
        if(lines.length > 0){
          scenesText = lines;
        }
      }
    
      showScreen('Progress');
      startProgress();
      fetch(API + '/api/v4/generate', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          template_id: template.id,
          brand: brand,
          desc: descText,
          phone: document.getElementById('f_phone').value,
          scenes_text: scenesText
        })
      }).then(function(r){ return r.json(); })
      .then(function(d){
        if(d.job_id){
          jobId = d.job_id;
          pollStatus(d.job_id);
        } else {
          setFail(d.error || '生成失败');
        }
      }).catch(function(){ setFail('网络错误'); });
    }
    
    // ===== 文案预览功能（V5.2） =====
    var _previewCopyData = null;
    
    window.previewCopy = function previewCopy(){
      if(!template){ toast('请先选择模板'); return; }
      var brand = document.getElementById('f_brand').value.trim();
      if(!brand){ toast('请填写品牌名/店名'); return; }
      var btn = document.getElementById('previewCopyBtn');
      btn.disabled = true;
      btn.textContent = '⏳ 生成文案中...';
    
      var descText = document.getElementById('f_desc').value.trim();
    
      fetch(API + '/api/preview-copy', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          template_id: template.id,
          brand: brand,
          desc: descText,
          phone: document.getElementById('f_phone').value,
          value: document.getElementById('f_value') ? document.getElementById('f_value').value : '',
          price: document.getElementById('f_price') ? document.getElementById('f_price').value : '',
          variant: window.selectedIndustryVariant ? window.selectedIndustryVariant.key : ''
        })
      }).then(function(r){ return r.json(); })
      .then(function(d){
        btn.disabled = false;
        btn.textContent = '📝 预览文案';
        if(d.error){ toast(d.error); return; }
        _previewCopyData = d;
        showPreviewCopyModal(d);
      }).catch(function(){
        btn.disabled = false;
        btn.textContent = '📝 预览文案';
        toast('文案生成失败');
      });
    }
    
    window.showPreviewCopyModal = function showPreviewCopyModal(data){
      var cp = data.copy_preview || {};
      var scenes = cp.scenes || {};
      var sceneList = cp.scene_list || [];
      var voiceover = cp.voiceover || '';
      var brand = data.brand || '';
    
      document.getElementById('previewCopyTpl').textContent = '📌 品牌：' + brand + ' | 模板：' + (template ? template.name : '');
    
      var scenesHtml = '';
      // 使用场景列表或从scenes对象构建
      if(sceneList.length > 0){
        sceneList.forEach(function(s, i){
          scenesHtml += '<div style="margin-bottom:10px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:10px;">';
          scenesHtml += '<div style="font-size:11px;color:rgba(255,255,255,.25);margin-bottom:4px;">🎬 场景' + (i+1) + '</div>';
          var fields = ['line1','line2','line3','line4','sub','price','info','limit','address','phone_str'];
          var fieldLabels = {'line1':'标题1','line2':'标题2','line3':'标题3','line4':'标题4','sub':'副标题','price':'价格','info':'详情','limit':'限制','address':'地址','phone_str':'电话'};
          fields.forEach(function(f){
            if(s[f]){
              scenesHtml += '<textarea class="preview-copy-line" data-scene="' + s.id + '" data-field="' + f + '" style="width:100%;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:6px 8px;color:#fff;font-size:12px;line-height:1.5;resize:vertical;outline:none;box-sizing:border-box;margin-bottom:4px;" rows="1">' + escapeHtml(s[f]) + '</textarea>';
            }
          });
          scenesHtml += '</div>';
        });
      } else {
        // 回退：从scenes对象构建
        var sceneKeys = Object.keys(scenes);
        sceneKeys.forEach(function(k, i){
          var v = scenes[k];
          var line1 = (typeof v === 'object') ? (v.line1 || '') : String(v);
          var line2 = (typeof v === 'object') ? (v.line2 || '') : '';
          scenesHtml += '<div style="margin-bottom:10px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:10px;">';
          scenesHtml += '<div style="font-size:11px;color:rgba(255,255,255,.25);margin-bottom:4px;">🎬 场景' + (i+1) + '</div>';
          scenesHtml += '<textarea class="preview-copy-line" data-scene="' + k + '" data-field="line1" style="width:100%;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:6px 8px;color:#fff;font-size:12px;line-height:1.5;resize:vertical;outline:none;box-sizing:border-box;margin-bottom:4px;" rows="2">' + escapeHtml(line1) + '</textarea>';
          if(line2){
            scenesHtml += '<textarea class="preview-copy-line" data-scene="' + k + '" data-field="line2" style="width:100%;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:6px 8px;color:#fff;font-size:12px;line-height:1.5;resize:vertical;outline:none;box-sizing:border-box;" rows="2">' + escapeHtml(line2) + '</textarea>';
          }
          scenesHtml += '</div>';
        });
      }
      document.getElementById('previewCopyScenes').innerHTML = scenesHtml;
      document.getElementById('previewCopyVoiceover').value = voiceover;
    
      document.getElementById('previewCopyOverlay').style.display = 'flex';
    }
    
    window.closePreviewCopy = function closePreviewCopy(){
      document.getElementById('previewCopyOverlay').style.display = 'none';
    }
    
    window.confirmPreviewCopy = function confirmPreviewCopy(){
      var data = _previewCopyData;
      if(!data){
        toast('预览数据丢失，请重新生成');
        return;
      }
    
      // 收集用户修改后的场景文案
      var textareas = document.querySelectorAll('.preview-copy-line');
      var scenesData = {};
      textareas.forEach(function(ta){
        var scene = ta.getAttribute('data-scene');
        var field = ta.getAttribute('data-field');
        if(!scenesData[scene]) scenesData[scene] = {};
        scenesData[scene][field] = ta.value;
      });
    
      var voiceoverText = document.getElementById('previewCopyVoiceover').value;
    
      // 关闭弹窗
      closePreviewCopy();
    
      var brand = document.getElementById('f_brand').value.trim();
      var descText = document.getElementById('f_desc').value.trim();
    
      showScreen('Progress');
      startProgress();
    
      fetch(API + '/api/v4/generate', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          template_id: template.id,
          brand: brand,
          desc: descText,
          phone: document.getElementById('f_phone').value,
          scenes_text: scenesData,
          voiceover_text: voiceoverText
        })
      }).then(function(r){ return r.json(); })
      .then(function(d){
        if(d.job_id){
          jobId = d.job_id;
          pollStatus(d.job_id);
        } else {
          setFail(d.error || '生成失败');
        }
      }).catch(function(){ setFail('网络错误'); });
    }
    
    window.genXiaohongshuCopy = function genXiaohongshuCopy(){
      var btn = document.getElementById('copyBtn');
      btn.disabled = true;
      btn.textContent = '⏳ 生成中...';
      fetch(API + '/api/generate-xiaohongshu-copy', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({job_id: jobId || jobId_global})
      }).then(function(r){ return r.json(); })
      .then(function(d){
        document.getElementById('copyText').textContent = d.copy || '生成失败，请重试';
        document.getElementById('copyDisplay').style.display = 'block';
        btn.disabled = false;
        btn.textContent = '📝 生成小红书文案';
      }).catch(function(){
        toast('生成文案失败');
        btn.disabled = false;
        btn.textContent = '📝 生成小红书文案';
      });
    }
    
    window.copyXiaohongshu = function copyXiaohongshu(){
      var text = document.getElementById('copyText').textContent;
      if(navigator.clipboard){
        navigator.clipboard.writeText(text).then(function(){ toast('✅ 文案已复制'); });
      } else {
        var ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        toast('✅ 文案已复制');
      }
    }
    
    // ===== 历史视频 =====
    window.showHistory = function showHistory(){
      var token = localStorage.getItem('user_token');
      if(!token){ toast('请先登录'); return; }
      showScreen('History');
      loadUserVideos();
    }
    
    window.closeHistory = function closeHistory(){
      showScreen('Tpl');
    }
    
    async function loadUserVideos(){
      var token = localStorage.getItem('user_token');
      var loadingEl = document.getElementById('historyLoading');
      var emptyEl = document.getElementById('historyEmpty');
      var listEl = document.getElementById('historyList');
      loadingEl.style.display = 'block';
      emptyEl.style.display = 'none';
      try {
        var resp = await fetch(API + '/api/user/videos', {headers:{'Authorization':'Bearer '+token}});
        var data = await resp.json();
        loadingEl.style.display = 'none';
        if(!data.videos || !data.videos.length){
          emptyEl.style.display = 'block';
          return;
        }
        var html = '';
        for(var i=0; i<data.videos.length; i++){
          var v = data.videos[i];
          // 获取模板 emoji
          var tplEmoji = EMOJI_MAP[v.template_id] || '🎬';
          var tplBadge = BADGE_MAP[v.template_id] || '通用';
          var brand = v.brand || '未命名';
          var timeStr = formatTime(v.created_at);
          var sizeStr = formatFileSize(v.file_size);
          var downloadUrl = v.download_url || (API + '/api/download/' + v.job_id);
          html += '<div style="background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:14px;padding:14px 16px;">';
          html += '<div style="display:flex;gap:12px;align-items:flex-start;">';
          html += '<div style="font-size:36px;width:44px;text-align:center;flex-shrink:0;line-height:1;">'+tplEmoji+'</div>';
          html += '<div style="flex:1;min-width:0;">';
          html += '<div style="font-size:15px;font-weight:700;color:#fff;margin-bottom:3px;">' + escapeHtml(brand) + '</div>';
          html += '<div style="font-size:12px;color:rgba(255,255,255,.3);margin-bottom:2px;">' + tplBadge + ' · ' + timeStr + '</div>';
          html += '<div style="font-size:11px;color:rgba(255,255,255,.2);">' + sizeStr + '</div>';
          html += '</div>';
          html += '</div>';
          html += '<div style="display:flex;gap:8px;margin-top:10px;">';
          html += '<a href="'+downloadUrl+'" target="_blank" style="flex:1;padding:9px 0;border-radius:8px;border:none;background:linear-gradient(135deg,#ffd54f,#e6b800);color:#1a1200;font-size:13px;font-weight:700;cursor:pointer;text-align:center;text-decoration:none;display:block;">▶ 预览</a>';
          html += '<button onclick="redoHistoryVideo(\''+v.template_id+'\')" style="flex:1;padding:9px 0;border-radius:8px;border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.03);color:rgba(255,255,255,.5);font-size:13px;font-weight:600;cursor:pointer;">🔄 重新生成</button>';
          html += '<button onclick="deleteVideo(\''+v.job_id+'\')" style="flex:0;padding:9px 12px;border-radius:8px;border:1px solid rgba(255,255,255,.06);background:rgba(255,255,255,.02);color:rgba(255,255,255,.25);font-size:13px;cursor:pointer;">🗑</button>';
          html += '</div></div>';
        }
        // 替换加载/空状态
        loadingEl.style.display = 'none';
        emptyEl.style.display = 'none';
        // 保留加载和空元素，追加卡片
        // 移除之前渲染的卡片（保留loading和empty）
        var cards = listEl.querySelectorAll('.history-card');
        for(var c=0; c<cards.length; c++){ cards[c].remove(); }
        // 插入卡片
        var tempDiv = document.createElement('div');
        tempDiv.innerHTML = html;
        while(tempDiv.firstChild){
          tempDiv.firstChild.classList.add('history-card');
          listEl.appendChild(tempDiv.firstChild);
        }
      } catch(e){
        loadingEl.style.display = 'none';
        toast('加载失败，请重试');
      }
    }
    
    window.redoHistoryVideo = function redoHistoryVideo(templateId){
      // 跳转到该模板的填写页
      for(var i=0; i<templates.length; i++){
        if(templates[i].id === templateId){
          template = templates[i];
          var cards = document.querySelectorAll('.tpl-card');
          for(var j=0; j<cards.length; j++) cards[j].classList.remove('selected');
          var card = document.querySelector('.tpl-card[data-id="'+templateId+'"]');
          if(card) card.classList.add('selected');
          document.getElementById('formTitle').textContent = template.name + ' — 填信息';
          document.getElementById('f_brand').value = '';
          document.getElementById('f_desc').value = '';
          document.getElementById('f_phone').value = '';
          showScreen('Form');
          return;
        }
      }
      toast('模板未找到');
    }
    
    async function deleteVideo(jobId){
      if(!confirm('确定删除这个视频？')) return;
      var token = localStorage.getItem('user_token');
      try {
        var resp = await fetch(API + '/api/user/video/delete', {
          method:'POST',
          headers:{'Content-Type':'application/json', 'Authorization':'Bearer '+token},
          body: JSON.stringify({job_id: jobId})
        });
        var data = await resp.json();
        if(data.status === 'ok'){
          toast('✅ 视频已删除');
          loadUserVideos();
        } else {
          toast(data.error || '删除失败');
        }
      } catch(e){
        toast('删除失败，请重试');
      }
    }
    
    window.formatTime = function formatTime(isoStr){
      if(!isoStr) return '';
      try {
        var d = new Date(isoStr);
        var month = (d.getMonth()+1).toString().padStart(2,'0');
        var day = d.getDate().toString().padStart(2,'0');
        var hour = d.getHours().toString().padStart(2,'0');
        var min = d.getMinutes().toString().padStart(2,'0');
        return month+'月'+day+'日 '+hour+':'+min;
      } catch(e){ return isoStr; }
    }
    
    window.formatFileSize = function formatFileSize(bytes){
      if(!bytes || bytes === 0) return '未知大小';
      if(bytes < 1024) return bytes + 'B';
      if(bytes < 1024*1024) return (bytes/1024).toFixed(1) + 'KB';
      return (bytes/(1024*1024)).toFixed(1) + 'MB';
    }
    
    window.escapeHtml = function escapeHtml(text){
      var div = document.createElement('div');
      div.appendChild(document.createTextNode(text));
      return div.innerHTML;
    }
    
    // ===== 个性化设置 - 背景图分类管理系统 =====
    var COLOR_SCHEMES = [
      {id:'tech_blue', name:'深蓝科技', colors:['#0a2a5e','#0a1628','#ffd700','#00d4ff']},
      {id:'warm_dark', name:'暖棕暗金', colors:['#1a1200','#2d1f0a','#ffd54f','#c9a000']},
      {id:'green_fresh', name:'清新绿意', colors:['#0a2e1a','#061e12','#7ecf5c','#00e676']},
      {id:'purple_dream', name:'紫色梦幻', colors:['#2a0a3e','#1a0a28','#e040fb','#bb86fc']},
      {id:'red_vibrant', name:'红色活力', colors:['#3e0a0a','#2a0606','#ff5252','#ff8a80']}
    ];
    
    // 当前选中状态
    var _bgCurrentCategoryId = null;
    var _bgCategories = [];
    var _bgImages = [];
    var _bgSelected = []; // [{id, url, thumbnail_url, duration, sort_order}, ...]
    
    // 初始化设置
    window.initSettings = function initSettings(){
      renderColorSchemes();
      loadSavedSettings();
      loadBgCategories();
    }
    
    // 加载已保存的设置
    window.loadSavedSettings = function loadSavedSettings(){
      var bgUrl = localStorage.getItem('user_bg_url');
      // We keep backward compat - show status if user_bg_url exists
      if(bgUrl){
        document.getElementById('bgStatus').textContent = '✅ 已设置自定义背景（旧版兼容）';
      }
      var savedScheme = localStorage.getItem('user_color_scheme');
    }

})();
