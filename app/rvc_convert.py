# -*- coding: utf-8 -*-
"""
RVC 变声流水线（在 .venv-rvc 环境中运行）
输入：一首完整的歌 + RVC 声音模型(.pth + 可选.index)
流程：demucs 分离人声/伴奏 -> RVC 把人声换成目标音色 -> ffmpeg 混回伴奏 -> 输出 mp3
用法：
    python rvc_convert.py --input song.mp3 --model voice.pth [--index voice.index]
                          [--pitch 0] --outdir outdir
"""
import sys
import argparse
import subprocess
from pathlib import Path


def sh(cmd):
    print("$ " + " ".join(map(str, cmd)), flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout:
        print(r.stdout[-3000:], flush=True)
    if r.stderr:
        print(r.stderr[-3000:], flush=True)
    return r.returncode


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="要变声的歌曲（完整混合音频）")
    p.add_argument("--model", required=True, help="RVC 声音模型 .pth")
    p.add_argument("--index", default="", help="RVC 检索索引 .index（可选，提升音色相似度）")
    p.add_argument("--pitch", type=int, default=0, help="变调半音数（男唱女歌 +12，女唱男歌 -12）")
    p.add_argument("--outdir", required=True)
    args = p.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    src = Path(args.input)

    # 1) 人声分离（首次运行会自动下载 htdemucs 模型约 300MB）
    print("[RVC] 步骤 1/4：分离人声与伴奏……", flush=True)
    rc = sh([sys.executable, "-m", "demucs", "--two-stems", "vocals", "-n", "htdemucs",
             "-o", str(outdir / "stems"), str(src)])
    vocals = outdir / "stems" / "htdemucs" / src.stem / "vocals.wav"
    no_vocals = outdir / "stems" / "htdemucs" / src.stem / "no_vocals.wav"
    if rc != 0 or not vocals.exists():
        sys.exit("[RVC] ❌ 人声分离失败（demucs）")
    print(f"[RVC] 人声: {vocals}\n[RVC] 伴奏: {no_vocals}", flush=True)

    # 2) RVC 变声
    print("[RVC] 步骤 2/4：RVC 变声（首次会自动下载基础模型）……", flush=True)
    try:
        from rvc_python.infer import RVCInference
    except ImportError as e:
        sys.exit(f"[RVC] ❌ rvc-python 未安装或导入失败：{e}")

    converted = outdir / "vocals_converted.wav"
    try:
        rvc = RVCInference(device="cuda:0")
        load_kw = {"model_path": str(args.model)}
        if args.index:
            load_kw["index_path"] = str(args.index)
        rvc.load_model(**load_kw)
        rvc.infer_file(str(vocals), str(converted), f0method="rmvpe", pitch=args.pitch)
    except TypeError:
        # 兼容 rvc-python 不同版本的 API 签名
        rvc = RVCInference(device="cuda:0")
        rvc.load_model(str(args.model), args.index or None)
        rvc.infer_file(str(vocals), str(converted), pitch=args.pitch)
    if not converted.exists():
        sys.exit("[RVC] ❌ 变声未产出文件")
    print(f"[RVC] 变声完成: {converted}", flush=True)

    # 3) 混回伴奏
    print("[RVC] 步骤 3/4：混回伴奏……", flush=True)
    final_wav = outdir / "final.wav"
    rc = sh(["ffmpeg", "-y", "-i", str(no_vocals), "-i", str(converted),
             "-filter_complex", "amix=inputs=2:duration=longest:dropout_transition=0",
             str(final_wav)])
    if rc != 0:
        sys.exit("[RVC] ❌ 混音失败（ffmpeg amix）")

    # 4) 输出 mp3
    print("[RVC] 步骤 4/4：输出 mp3……", flush=True)
    out_mp3 = outdir / "audio_rvc.mp3"
    rc = sh(["ffmpeg", "-y", "-i", str(final_wav), "-codec:a", "libmp3lame", "-q:a", "2", str(out_mp3)])
    if rc != 0 or not out_mp3.exists():
        sys.exit("[RVC] ❌ mp3 输出失败")

    print(f"RVC_OK {out_mp3}", flush=True)


if __name__ == "__main__":
    main()
