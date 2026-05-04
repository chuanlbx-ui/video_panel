# 立夏V5竖版视频模板 — 使用说明

> 直接把 `vertical_lixia/` 目录复制一份，改 `template_config.json` 就可以了。

## 快速上手

```
cd /path/to/你的视频目录
```

### 改文案
编辑 `template_config.json`，找到 `scenes` 数组，改每个 `elements` 里的 `text` 字段：

```json
{
  "line1": { "text": "改成你的文案", "style": "large_white" }
}
```

### 预览生成效果
```bash
python3 build_from_config.py --output index.html
# 然后用浏览器打开 index.html 查看（部分动画需用 hyperframes preview）
```

### 渲染出片
```bash
python3 build_from_config.py --render
# 或分两步：
python3 build_from_config.py --output index.html
npx hyperframes render -o output.mp4
```

## template_config.json 结构

| 字段 | 说明 |
|:-----|:-----|
| `scenes[].name` | 场景名称（影响动画风格） |
| `scenes[].start` | 开始时间（秒） |
| `scenes[].duration` | 持续时长（秒） |
| `scenes[].elements.*.text` | 要显示的文字 |
| `scenes[].elements.*.style` | 样式（见下方） |

### 可用样式

| 样式名 | 效果 |
|:-------|:-----|
| `large_white` | 大白字 130px |
| `large_gold` | 金色大字 130px |
| `large_cyan` | 青色大字 130px |
| `subtitle` | 副标题 40px 半透明 |
| `tags` | 标签 72px 金色居中 |
| `price` | 价格 110px 金色发光 |
| `info` | 信息 44px 白色多行 |
| `phone` | 电话 48px 青色 |
| `phone_small` | 小号电话 40px |
| `limit` | 限额 40px 半透明 |

## 4场景结构

| 场景 | 时长 | 内容 | 动画风格 |
|:----|:----|:-----|:---------|
| 学什么 | 7秒 | 大字报核心卖点 | 逐行从下飞入 |
| 有什么价值 | 6秒 | 学习收益 | 缩放出现 |
| 为什么是他讲 | 6秒 | 主讲人标签 | 标签飞入+缩放 |
| 怎么参加 | 9秒 | 价格+时间+电话 | 价格弹出+信息飞入 |

## 快速复制一个新视频

```bash
cp -r vertical_lixia/ 我的新视频/
cd 我的新视频/
# 编辑 template_config.json 改文案和时长
python3 build_from_config.py --output index.html
```

## 配音/背景音乐

渲染出片后单独混音：
```bash
# 配音（用edge-tts）
python3 -c "
import asyncio, edge_tts
asyncio.run(edge_tts.Communicate('文案内容', 'zh-CN-XiaoxiaoNeural', rate='+10%').save('voiceover.mp3'))
"

# 混音（配音+BGM）
ffmpeg -y -i output.mp4 -i voiceover.mp3 -filter_complex "[1:a]volume=1.0[a]" -map 0:v:0 -map "[a]" -c:v copy -c:a aac -shortest final.mp4
```
