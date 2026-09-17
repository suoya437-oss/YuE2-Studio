# -*- coding: utf-8 -*-
"""
Seed-VC 零样本变声流水线（在 .venv-seedvc 环境中运行）
输入：一首完整的歌 + 目标音色参考音频（5–30 秒即可，无需训练）
流程：demucs 分离人声/伴奏 -> Seed-VC 零样本变声（保留旋律 F0）-> ffmpeg 混回伴奏 -> 输出 mp3
用法：
    python seedvc_convert.py --input song.mp3 --reference ref.mp3 [--pitch 0] [--steps 40] --outdir out
"""
import os
import sys
import argparse
import subprocess
from pathlib import Path

SEEDVC_DIR = Path(os.environ.get("YUE2_BASE", "/root/autodl-tmp")) / "seed-vc"


def sh(cmd, cwd=None):
    print("$ " + " ".join(map(str, cmd)), flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if r.stdout:
        print(r.stdout[-3000:], flush=True)
    if r.stderr:
        print(r.stderr[-3000:], flush=True)
    return r.returncode


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="要变声的歌曲（完整混合音频）")
    p.add_argument("--reference", required=True, help="目标音色参考音频（5–30 秒干净人声最佳）")
    p.add_argument("--pitch", type=int, default=0, help="半音偏移（偏高 +，偏低 -）")
    p.add_argument("--steps", type=int, default=40, help="扩散步数 30–50，越大质量越好越慢")
    p.add_argument("--outdir", required=True)
    args = p.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    src = Path(args.input)

    # 1) 人声分离
    print("[SeedVC] 步骤 1/4：分离人声与伴奏……", flush=True)
    rc = sh([sys.executable, "-m", "demucs", "--two-stems", "vocals", "-n", "htdemucs",
             "-o", str(outdir / "stems"), str(src)])
    vocals = outdir / "stems" / "htdemucs" / src.stem / "vocals.wav"
    no_vocals = outdir / "stems" / "htdemucs" / src.stem / "no_vocals.wav"
    if rc != 0 or not vocals.exists():
        sys.exit("[SeedVC] ❌ 人声分离失败（demucs）")

    # 参考音频若是 mp3 等格式，先转 wav（seed-vc 需要 wav）
    ref = Path(args.reference)
    ref_wav = outdir / "reference.wav"
    if ref.suffix.lower() != ".wav":
        rc = sh(["ffmpeg", "-y", "-i", str(ref), "-ar", "44100", "-ac", "1", str(ref_wav)])
        if rc != 0:
            sys.exit("[SeedVC] ❌ 参考音频转换失败")
    else:
        ref_wav = ref

    # 2) Seed-VC 零样本变声（唱歌模式：f0-condition 保旋律）
    print("[SeedVC] 步骤 2/4：零样本变声（首次会自动下载模型）……", flush=True)
    svc_out = outdir / "svc"
    svc_out.mkdir(exist_ok=True)
    rc = sh([
        sys.executable, "inference.py",
        "--source", str(vocals),
        "--target", str(ref_wav),
        "--output", str(svc_out),
        "--diffusion-steps", str(args.steps),
        "--length-adjust", "1.0",
        "--inference-cfg-rate", "0.7",
        "--f0-condition", "True",
        "--auto-f0-adjust", "False",
        "--semi-tone-shift", str(args.pitch),
        "--fp16", "True",
    ], cwd=str(SEEDVC_DIR))
    if rc != 0:
        sys.exit("[SeedVC] ❌ Seed-VC 推理失败")

    wavs = sorted(svc_out.glob("*.wav"), key=lambda x: x.stat().st_mtime)
    if not wavs:
        sys.exit("[SeedVC] ❌ Seed-VC 未产出音频")
    converted = wavs[-1]
    print(f"[SeedVC] 变声完成: {converted}", flush=True)

    # 3) 混回伴奏
    print("[SeedVC] 步骤 3/4：混回伴奏……", flush=True)
    final_wav = outdir / "final.wav"
    rc = sh(["ffmpeg", "-y", "-i", str(no_vocals), "-i", str(converted),
             "-filter_complex", "amix=inputs=2:duration=longest:dropout_transition=0",
             str(final_wav)])
    if rc != 0:
        sys.exit("[SeedVC] ❌ 混音失败")

    # 4) 输出 mp3
    print("[SeedVC] 步骤 4/4：输出 mp3……", flush=True)
    out_mp3 = outdir / "audio_vc.mp3"
    rc = sh(["ffmpeg", "-y", "-i", str(final_wav), "-codec:a", "libmp3lame", "-q:a", "2", str(out_mp3)])
    if rc != 0 or not out_mp3.exists():
        sys.exit("[SeedVC] ❌ mp3 输出失败")

    print(f"SEEDVC_OK {out_mp3}", flush=True)


if __name__ == "__main__":
    main()
