#!/bin/bash
set -e

OUTDIR="/home/agentuser/hyperframes_projects/assets/bg_loops"
FPS=30
DUR=5

generate() {
    local W=$1 H=$2 SUFFIX=$3
    local OUTFILE="${OUTDIR}/bg_loop_${SUFFIX}.mp4"
    
    echo "=== Generating ${SUFFIX} ${W}x${H} ==="
    
    ffmpeg -y \
        -f lavfi -i "gradients=s=${W}x${H}:r=${FPS}:d=${DUR}:c0=#050518:c1=#0a1628:c2=#0d1b3e:c3=#061a3a:nb_colors=4" \
        -f lavfi -i "life=s=$((W/4))x$((H/4)):r=15:random_fill_ratio=0.03:random_seed=42:rule=B3/S23:stitch=1,scale=${W}x${H}:flags=neighbor,colorchannelmixer=rr=0.3:rg=0.5:rb=0.9,eq=brightness=0.2:contrast=2.0,tblend=all_mode=average,gblur=sigma=1.5" \
        -f lavfi -i "nullsrc=s=${W}x${H}:d=${DUR}:r=${FPS}" \
        -f lavfi -i "nullsrc=s=${W}x${H}:d=${DUR}:r=${FPS}" \
        -filter_complex "\
[2]noise=alls=20:allf=t+u,geq=lum=255*gt(random(1)\,0.985):cr=128:cb=128[stars_raw];\
[stars_raw]format=rgba,gblur=sigma=2.5[stars];\
[3]geq=lum=if(lt(mod(Y+T*60\,80)\,3)\,180\,0):cr=128:cb=128,format=rgba,gblur=sigma=4[scanline];\
[0]format=rgba[base];\
[1]format=rgba,colorize=hue=215:saturation=0.7:lightness=0.15[particles];\
[base][particles]overlay=format=auto:alpha=0.65[layer1];\
[layer1][stars]overlay=format=auto:alpha=0.95[layer2];\
[layer2][scanline]overlay=format=auto:alpha=0.15[out]" \
        -map "[out]" -t ${DUR} -c:v libx264 -preset ultrafast -crf 22 -pix_fmt yuv420p \
        "$OUTFILE"
    
    echo "Done: $(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUTFILE")s"
}

generate 1920 1080 "landscape"
generate 1080 1920 "portrait"

echo ""
echo "=== Files ==="
ls -lh "${OUTDIR}/"*.mp4
for f in "${OUTDIR}/"*.mp4; do
    echo "--- $f ---"
    ffprobe -v error -show_entries stream=width,height,codec_name,duration -of default=noprint_wrappers=1 "$f"
done
