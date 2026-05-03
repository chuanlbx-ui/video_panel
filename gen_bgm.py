#!/usr/bin/env python3
"""生成BGM音频文件"""
import struct, math, os

SAMPLE_RATE = 44100
def write_wav(path, samples):
    max_amp = 32767
    num_samples = len(samples)
    with open(path, 'wb') as f:
        # RIFF header
        f.write(b'RIFF')
        f.write(struct.pack('<I', 36 + num_samples * 2))
        f.write(b'WAVE')
        # fmt chunk
        f.write(b'fmt ')
        f.write(struct.pack('<I', 16))  # chunk size
        f.write(struct.pack('<H', 1))   # PCM
        f.write(struct.pack('<H', 1))   # mono
        f.write(struct.pack('<I', SAMPLE_RATE))
        f.write(struct.pack('<I', SAMPLE_RATE * 2))  # byte rate
        f.write(struct.pack('<H', 2))   # block align
        f.write(struct.pack('<H', 16))  # bits per sample
        # data chunk
        f.write(b'data')
        f.write(struct.pack('<I', num_samples * 2))
        for s in samples:
            f.write(struct.pack('<h', int(s * max_amp)))

def gen_sine(freq, duration, amp=0.3):
    n = int(SAMPLE_RATE * duration)
    return [amp * math.sin(2 * math.pi * freq * i / SAMPLE_RATE) for i in range(n)]

def gen_bass(duration, amp=0.4):
    n = int(SAMPLE_RATE * duration)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        s = amp * (math.sin(2 * math.pi * 55 * t) + 0.5 * math.sin(2 * math.pi * 110 * t))
        samples.append(s * 0.5)
    return samples

out_dir = '/home/agentuser/hyperframes_projects/assets/bgm'
os.makedirs(out_dir, exist_ok=True)

# 1) tech_pulse - 科技脉冲（低频+电子鼓点节奏）
n = int(SAMPLE_RATE * 30)
tech = []
for i in range(n):
    t = i / SAMPLE_RATE
    kick = 0.4 * math.exp(-(t % 0.5) * 8) * (1 if (int(t * 2) % 2 == 0) else 0.7)
    bass = 0.15 * math.sin(2 * math.pi * 60 * t)
    hi = 0.05 * (1 if (int(t * 0.5) != int(t * 0.5 + 0.01)) else 0)
    s = kick + bass + hi + 0.08 * math.sin(2 * math.pi * 440 * t) * (1 if int(t * 4) % 4 == 0 else 0)
    tech.append(min(0.9, max(-0.9, s)))
write_wav(os.path.join(out_dir, 'tech_pulse.wav'), tech)
print(f'tech_pulse: {os.path.getsize(os.path.join(out_dir, "tech_pulse.wav"))} bytes')

# 2) uplifting - 励志昂扬（大调和弦+上升音）
uplift = []
for i in range(n):
    t = i / SAMPLE_RATE
    chord = (math.sin(2*math.pi*262*t) + math.sin(2*math.pi*330*t) + math.sin(2*math.pi*392*t)) * 0.1
    rise = t / 30 * 0.3  # 渐强
    kick = 0.3 * math.exp(-(t % 1.0) * 6) * (1 if int(t) % 2 == 0 else 0.6)
    s = chord * rise + kick + 0.06 * math.sin(2*math.pi*523*t) * 0.5
    uplift.append(min(0.9, max(-0.9, s)))
write_wav(os.path.join(out_dir, 'uplifting.wav'), uplift)
print(f'uplifting: {os.path.getsize(os.path.join(out_dir, "uplifting.wav"))} bytes')

# 3) ambient - 空灵氛围（长音+泛音）
amb = []
for i in range(n):
    t = i / SAMPLE_RATE
    pad = 0.08 * (math.sin(2*math.pi*220*t) + math.sin(2*math.pi*330*t)*0.7 + math.sin(2*math.pi*440*t)*0.4)
    shimmer = 0.03 * math.sin(2*math.pi*880*t) * (0.5 + 0.5 * math.sin(2*math.pi*0.1*t))
    s = pad + shimmer
    amb.append(min(0.5, max(-0.5, s)))
write_wav(os.path.join(out_dir, 'ambient.wav'), amb)
print(f'ambient: {os.path.getsize(os.path.join(out_dir, "ambient.wav"))} bytes')

# 4) xinxue_zen - 心学禅意（古风+钟声）
zen_n = int(SAMPLE_RATE * 30)
zen = []
for i in range(zen_n):
    t = i / SAMPLE_RATE
    # 古筝模拟（泛音丰富）
    guzheng = 0.05 * (math.sin(2*math.pi*260*t) + 0.3*math.sin(2*math.pi*520*t) + 0.15*math.sin(2*math.pi*780*t))
    # 钟声（每5秒一次）
    bell_t = t % 5.0
    bell = 0.12 * math.exp(-bell_t * 1.5) * math.sin(2*math.pi*174 * t) if bell_t < 1.5 else 0
    # 低频pad
    pad = 0.06 * math.sin(2*math.pi*130*t)
    s = guzheng + bell + pad
    zen.append(min(0.5, max(-0.5, s)))
write_wav(os.path.join(out_dir, 'xinxue_zen.wav'), zen)
print(f'xinxue_zen: {os.path.getsize(os.path.join(out_dir, "xinxue_zen.wav"))} bytes')

# 5) wenshan_folk - 文山民族风（芦笙风格）
folk = []
for i in range(n):
    t = i / SAMPLE_RATE
    melody = 0.08 * (math.sin(2*math.pi*196*t) + 0.5*math.sin(2*math.pi*392*t))
    rhythm = 0.15 * math.exp(-(t % 0.75) * 5) * (1 if int(t*1.33) % 2 == 0 else 0.5)
    drone = 0.04 * math.sin(2*math.pi*98*t)  # 持续低音
    s = melody + rhythm + drone
    folk.append(min(0.5, max(-0.5, s)))
write_wav(os.path.join(out_dir, 'wenshan_folk.wav'), folk)
print(f'wenshan_folk: {os.path.getsize(os.path.join(out_dir, "wenshan_folk.wav"))} bytes')

print("\n全部BGM生成完毕!")
