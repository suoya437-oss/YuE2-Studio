# -*- coding: utf-8 -*-
"""
YuE2 音乐生成工作台（Gradio 网页版 v10 —— 创作 + 翻唱 + 声音克隆全链路）
功能：表单化创作（语言/人声/曲风/乐器/速度/服从度）+ ABC 乐谱编辑重渲染
     + 上传原曲自动转录翻唱（SheetSage2）+ RVC 声音克隆变声（demucs 分离 + rvc-python）
用法：
    /root/miniconda3/envs/yue2/bin/python -u /root/autodl-tmp/yue2_webui.py
"""
import os
import re
import json
import time
import shutil
import base64
import mimetypes
import threading
import subprocess
from pathlib import Path

import gradio as gr

print(f"[yue2-webui] gradio 版本: {gr.__version__}")

BASE_DIR = Path("/root/autodl-tmp")
REPO = BASE_DIR / "YuE"
OUTROOT = BASE_DIR / "output_web"

PYGEN = "/root/miniconda3/bin/python"
if not Path(PYGEN).exists():
    import shutil
    PYGEN = shutil.which("python") or "python"

TUNA = "https://pypi.tuna.tsinghua.edu.cn/simple"
ALIYUN = "https://mirrors.aliyun.com/pypi/simple/"
TENCENT = "https://mirrors.cloud.tencent.com/pypi/simple"
PIP_MIRROR = TENCENT  # 实测该容器对腾讯源最快（10MB/s+），清华/阿里均拥堵

# SheetSage2 转录相关（独立环境，按官方要求与 YuE2 环境隔离）
SS2_VENV = REPO / ".venv-sheetsage2"
SS2_PY = SS2_VENV / "bin" / "python"
SS2_MODEL = REPO / "models" / "SheetSage2"

# RVC 变声相关（独立环境：demucs 分离 + rvc-python 变声）
RVC_VENV = REPO / ".venv-rvc"
RVC_PY = RVC_VENV / "bin" / "python"
RVC_SCRIPT = BASE_DIR / "rvc_convert.py"

# Seed-VC 零样本变声相关（独立环境 + 仓库；参考音频即可，无需训练）
SVC_VENV = REPO / ".venv-seedvc"
SVC_PY = SVC_VENV / "bin" / "python"
SVC_DIR = BASE_DIR / "seed-vc"
SVC_SCRIPT = BASE_DIR / "seedvc_convert.py"

DEFAULT_STYLE = "warm folk pop, acoustic guitar and piano, mid-tempo 90 BPM"
DEFAULT_LYRICS = """[Verse]
晚风吹过旧街口
路灯把影子拉得很长
你说要去远方
把夏天的故事留在原地

[Chorus]
月亮升起来的时候
我会想起你的笑容
就算走散在人海
也谢谢你路过我的星空"""

COT_MAP = {
    "智能创作（推荐，可编辑旋律与和弦）": "full",
    "翻唱改编（锁定旋律，自由重新编曲）": "melody",
    "快速直出（跳过乐谱规划）": "off",
}

VOCAL_MAP = {
    "男声 · 低沉磁性": "deep male baritone vocals",
    "男声 · 清亮": "bright male tenor vocals",
    "女声 · 温暖": "warm expressive female vocals",
    "女声 · 清澈": "clear clean female vocals",
    "男女对唱": "male and female duet vocals",
    "纯音乐（无人声）": "instrumental, no vocals",
    "自定义（在风格框里写）": "",
}

# 歌词语言 -> 英文标签
LANG_MAP = {
    "中文": "Chinese lyrics",
    "英语": "English lyrics",
    "粤语": "Cantonese lyrics",
    "日语": "Japanese lyrics",
    "韩语": "Korean lyrics",
    "自定义（写在补充风格里）": "",
}

# 曲风 -> 英文标签
GENRE_MAP = {
    "流行": "pop",
    "民谣": "folk",
    "城市流行（复古都市感）": "city pop",
    "摇滚": "rock",
    "嘻哈说唱": "hip-hop rap",
    "R&B": "rhythm and blues",
    "电子合成器流行": "synth-pop",
    "爵士": "jazz",
    "蓝调": "blues",
    "乡村": "country",
    "金属": "heavy metal",
    "古风（国风）": "chinese ancient style, traditional arrangement",
    "梦幻流行": "dream pop",
    "抒情慢歌": "emotional ballad",
    "轻音乐（伴奏为主）": "easy listening instrumental",
    "自定义（写在补充风格里）": "",
}

# 乐器 -> 英文标签（可多选）
INSTRUMENT_MAP = {
    "木吉他": "acoustic guitar",
    "电吉他": "electric guitar",
    "钢琴": "piano",
    "合成器": "synthesizer",
    "贝斯": "bass",
    "鼓 / 鼓机": "drums",
    "弦乐": "strings",
    "小提琴": "violin",
    "萨克斯": "saxophone",
    "小号": "trumpet",
    "口琴": "harmonica",
    "古筝": "guzheng",
    "琵琶": "pipa",
    "二胡": "erhu",
    "笛子": "bamboo flute",
    "电子节拍": "electronic beats",
}

STATE = {"proc": None, "outdir": None, "logfile": None}
SS2 = {"running": False, "logfile": None, "abc": None, "applied": True, "run_dir": None, "t0": None}
RVC = {"running": False, "logfile": None, "t0": None, "result": None, "applied": True}


def _rvc_elapsed():
    if not RVC.get("t0"):
        return ""
    sec = int(time.time() - RVC["t0"])
    return f"{sec // 60:02d}:{sec % 60:02d}"


def _song_choices():
    """列出 output_web 里所有含音频的目录，供变声下拉框选择。"""
    if not OUTROOT.exists():
        return []
    out = []
    for d in sorted([p for p in OUTROOT.iterdir() if p.is_dir()], reverse=True):
        a = _find_audio(d)
        if a:
            out.append(f"{d.name} | {a}")
        if len(out) >= 20:
            break
    return out


def _ss2_elapsed():
    if not SS2.get("t0"):
        return ""
    sec = int(time.time() - SS2["t0"])
    return f"{sec // 60:02d}:{sec % 60:02d}"


def _ss2_stage():
    """根据日志尾部的关键词猜测当前阶段。"""
    lf = SS2.get("logfile")
    if not lf or not Path(lf).exists():
        return "准备中"
    try:
        raw = Path(lf).read_text(errors="ignore")[-4000:]
    except OSError:
        return "准备中"
    if "✅ 转录完成" in raw:
        return "已完成"
    if "Downloading" in raw or "Fetching" in raw:
        return "下载模型组件（首次一次性）"
    if "Migrating" in raw:
        return "缓存迁移（一次性）"
    if re.search(r"\d{1,3}%", raw.split("$")[-1]):
        pct = re.findall(r"(\d{1,3})%", raw)[-1]
        return f"转录处理中 ~{pct}%"
    return "模型加载 / 处理中（此阶段日志安静属正常）"


# ---------- 通用工具 ----------

def _find_audio(outdir: Path):
    if outdir is None or not outdir.exists():
        return None
    for pat in ("*.mp3", "*.wav", "*.flac"):
        hits = sorted(outdir.rglob(pat), key=lambda p: p.stat().st_mtime)
        if hits:
            return hits[-1]
    return None


def _to_mp3(audio):
    if audio is None or audio.suffix.lower() == ".mp3":
        return audio
    import shutil as _sh
    if not _sh.which("ffmpeg"):
        return audio
    target = audio.with_suffix(".mp3")
    if target.exists() and target.stat().st_size > 0:
        return target
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(audio), "-codec:a", "libmp3lame", "-q:a", "2", str(target)],
            capture_output=True, timeout=600,
        )
        if target.exists() and target.stat().st_size > 0:
            return target
    except Exception:
        pass
    return audio


def _audio_html(path):
    if not path:
        return ""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return ""
    b64 = base64.b64encode(raw).decode()
    mime = mimetypes.guess_type(str(path))[0] or "audio/mpeg"
    name = Path(path).name
    size_kb = len(raw) // 1024
    return (
        f'<audio controls style="width:100%" src="data:{mime};base64,{b64}"></audio>'
        f'<p style="margin-top:8px">'
        f'<a download="{name}" href="data:{mime};base64,{b64}" '
        f'style="font-size:1.05em">⬇️ 点击下载 {name}（{size_kb} KB）</a></p>'
    )


def _latest_run_with_audio():
    if not OUTROOT.exists():
        return None, None
    for d in sorted([p for p in OUTROOT.iterdir() if p.is_dir()], reverse=True):
        a = _find_audio(d)
        if a:
            return d, a
    return None, None


def _log_tail(logfile, n=25):
    if not logfile or not Path(logfile).exists():
        return ""
    try:
        raw = Path(logfile).read_text(errors="ignore")
    except OSError:
        return ""
    lines = [l.rstrip() for l in raw.replace("\r", "\n").splitlines() if l.strip()]
    return "\n".join(lines[-n:])


def _percent():
    lf = STATE.get("logfile")
    if not lf or not Path(lf).exists():
        return None
    try:
        raw = Path(lf).read_text(errors="ignore")[-8000:]
    except OSError:
        return None
    hits = re.findall(r"(\d{1,3})%", raw)
    return hits[-1] + "%" if hits else None


def _read_abc(outdir):
    if outdir is None:
        return ""
    abcs = sorted(Path(outdir).rglob("*.abc"))
    if not abcs:
        return ""
    try:
        return abcs[-1].read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


# ---------- 生成 ----------

def start_generate(song_name, lang, vocal, genre, instruments, tempo_bpm, extra_style, cfg_scale,
                   lyrics, cot_label, seed, use_abc, abc_input):
    proc = STATE.get("proc")
    if proc is not None and proc.poll() is None:
        return "⚠️ 已有一首正在生成，请等它完成（右侧会自动刷新进度）"

    lyrics = (lyrics or "").strip() or DEFAULT_LYRICS
    name = (song_name or "").strip() or time.strftime("song_%H%M%S")
    cot = COT_MAP.get(cot_label, "full")

    use_abc = bool(use_abc and (abc_input or "").strip())
    if use_abc and cot == "off":
        return "❌ 使用自定义乐谱时不能选「快速直出」模式，请改用智能创作或翻唱改编"

    # 组装风格串：语言 > 人声 > 曲风 > 乐器 > 速度 > 补充（越靠前权重越高）
    parts = []
    lang_tag = LANG_MAP.get(lang, "")
    if lang_tag:
        parts.append(lang_tag)
    vocal_tag = VOCAL_MAP.get(vocal, "")
    if vocal_tag:
        parts.append(vocal_tag)
        if "male" in vocal_tag and "female" not in vocal_tag:
            parts.append("male voice")
        elif "female" in vocal_tag and "male" not in vocal_tag:
            parts.append("female voice")
    genre_tag = GENRE_MAP.get(genre, "")
    if genre_tag:
        parts.append(genre_tag)
    inst_tags = [INSTRUMENT_MAP[i] for i in (instruments or []) if i in INSTRUMENT_MAP]
    if inst_tags:
        parts.append(", ".join(inst_tags))
    try:
        parts.append(f"{int(tempo_bpm)} BPM")
    except (TypeError, ValueError):
        pass
    extra = (extra_style or "").strip()
    if extra:
        parts.append(extra)
    style = ", ".join(parts) or "pop"

    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", name)
    safe_id = re.sub(r"_+", "_", safe_id).strip("_") or time.strftime("song_%H%M%S")

    req = {"id": safe_id, "style": style, "lyrics": lyrics, "cot": cot}
    if str(seed).strip():
        try:
            req["seed"] = int(seed)
        except ValueError:
            return "❌ 随机种子必须是纯数字（或留空）"
    try:
        req["cfg_scale"] = float(cfg_scale)
    except (TypeError, ValueError):
        pass

    run_id = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
    outdir = OUTROOT / run_id
    OUTROOT.mkdir(parents=True, exist_ok=True)
    reqfile = OUTROOT / f"{run_id}.json"
    reqfile.write_text(json.dumps(req, ensure_ascii=False), encoding="utf-8")
    logfile = OUTROOT / f"{run_id}.log"

    cmd = [
        PYGEN, "examples/generate.py",
        "--request", str(reqfile),
        "--cot", cot,
        "--output", str(outdir),
    ]
    if use_abc:
        abcfile = OUTROOT / f"{run_id}.abc"
        abcfile.write_text(abc_input.strip() + "\n", encoding="utf-8")
        cmd += ["--abc-file", str(abcfile)]
    if "seed" in req:
        cmd += ["--seed", str(req["seed"])]

    env = dict(os.environ)
    env["HF_ENDPOINT"] = "https://hf-mirror.com"

    def worker():
        with open(logfile, "w", encoding="utf-8") as f:
            f.write(f"[preflight] 解释器: {PYGEN}\n")
            pre = subprocess.run(
                [PYGEN, "-c", "import torch, yue2; print('[preflight] torch', torch.__version__, '| yue2 OK')"],
                capture_output=True, text=True, env=env, cwd=str(REPO),
            )
            f.write((pre.stdout or "") + (pre.stderr or ""))
            if pre.returncode != 0:
                f.write("[preflight] 自检失败，已取消本次生成。请把本日志发给助手。\n")
                STATE["proc"] = None
                return
            p = subprocess.Popen(
                cmd, stdout=f, stderr=subprocess.STDOUT,
                cwd=str(REPO), env=env,
            )
            STATE["proc"] = p
            p.wait()

    STATE.update({"outdir": outdir, "logfile": str(logfile), "proc": None})
    threading.Thread(target=worker, daemon=True).start()
    time.sleep(2)
    return f"🚀 已开始生成《{name}》！右侧自动刷新进度（全程约 2–10 分钟）"


# ---------- SheetSage2 转录（翻唱链路） ----------

def _ss2_run(f, cmd, env):
    f.write("\n$ " + " ".join(map(str, cmd)) + "\n")
    f.flush()
    subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=str(REPO), env=env)


def _ss2_worker(audio_path, logfile):
    env = dict(os.environ)
    env["HF_ENDPOINT"] = "https://hf-mirror.com"
    with open(logfile, "w", encoding="utf-8") as f:
        try:
            # 1) 独立 venv（官方要求与 YuE2 环境隔离，Python 3.10/3.11）
            if not SS2_PY.exists():
                f.write("[SheetSage2] 首次运行：创建独立环境（只需一次，约 15–30 分钟）\n")
                _ss2_run(f, ["python3", "-m", "venv", ".venv-sheetsage2"], env)
                if not SS2_PY.exists():
                    f.write("[SheetSage2] venv 创建失败，安装 python3.10-venv 后重试\n")
                    _ss2_run(f, ["bash", "-lc", "apt-get update -qq && apt-get install -y -qq python3.10-venv"], env)
                    _ss2_run(f, ["python3", "-m", "venv", ".venv-sheetsage2"], env)

            if not SS2_MODEL.exists():
                # 2) 基础工具 + 模型下载（走国内镜像）
                _ss2_run(f, [str(SS2_PY), "-m", "pip", "install", "-U", "pip", "-i", PIP_MIRROR], env)
                _ss2_run(f, [str(SS2_PY), "-m", "pip", "install", "huggingface-hub==0.36.0", "-i", PIP_MIRROR], env)
                hf_cli = str(SS2_VENV / "bin" / "huggingface-cli")
                _ss2_run(f, [hf_cli, "download", "m-a-p/SheetSage2", "--local-dir", "models/SheetSage2"], env)

            # 3) torch 独立检测（避免上次中断后重复下载模型或漏装 torch）
            probe = subprocess.run(
                [str(SS2_PY), "-c", "import torch, torchaudio"],
                capture_output=True, cwd=str(REPO), env=env,
            )
            if probe.returncode != 0:
                _ss2_run(f, [str(SS2_PY), "-m", "pip", "install", "torch==2.8.0", "torchaudio==2.8.0", "-i", PIP_MIRROR], env)

            # 4) requirements 独立检测：抽查一个依赖装没装
            probe_req = subprocess.run(
                [str(SS2_PY), "-c", "import transformers"],
                capture_output=True, cwd=str(REPO), env=env,
            )
            if probe_req.returncode != 0 and (SS2_MODEL / "requirements.txt").exists():
                _ss2_run(f, [str(SS2_PY), "-m", "pip", "install", "-r", "models/SheetSage2/requirements.txt", "-i", PIP_MIRROR], env)

            # 4) 转录：音频 -> ABC 旋律谱
            run_id = time.strftime("transcribe_%Y%m%d-%H%M%S")
            ss2_out = OUTROOT / run_id
            f.write(f"\n[SheetSage2] 开始转录：{audio_path}\n")
            _ss2_run(f, [str(SS2_PY), "models/SheetSage2/infer.py", str(audio_path),
                         "--output", str(ss2_out), "--melody-only"], env)

            abcs = sorted(ss2_out.rglob("*.abc")) if ss2_out.exists() else []
            if not abcs:
                SS2["abc"] = None
                f.write("[SheetSage2] ❌ 没有产出乐谱文件，请把本日志发给助手\n")
                return
            SS2["abc"] = abcs[-1].read_text(encoding="utf-8", errors="ignore")
            SS2["run_dir"] = str(ss2_out)
            SS2["applied"] = False
            f.write(f"[SheetSage2] ✅ 转录完成：{abcs[-1]}\n")
        except Exception as e:
            f.write(f"[SheetSage2] ❌ 异常：{e}\n")


def start_transcribe(audio_up):
    if SS2.get("running"):
        return "⏳ 转录已在进行中，请等待（下方会显示进度）"
    if not audio_up:
        return "❌ 请先上传音频文件（mp3 / wav）"

    run_id = time.strftime("ss2_%Y%m%d-%H%M%S")
    logfile = OUTROOT / f"{run_id}.log"
    SS2.update({"logfile": str(logfile), "abc": None, "applied": True, "running": True, "t0": time.time()})

    def boot():
        try:
            _ss2_worker(audio_up, str(logfile))
        finally:
            SS2["running"] = False
    threading.Thread(target=boot, daemon=True).start()
    return "🎹 转录任务已启动！首次运行会自动安装环境（15–30 分钟），之后每次约 1–2 分钟。进度见下方状态。"


# ---------- RVC 声音克隆（变声链路） ----------

def _rvc_worker(song_path, model_path, index_path, pitch, logfile):
    env = dict(os.environ)
    env["HF_ENDPOINT"] = "https://hf-mirror.com"

    def run(cmd):
        with open(logfile, "a", encoding="utf-8") as f:
            f.write("\n$ " + " ".join(map(str, cmd)) + "\n")
            f.flush()
            subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=str(REPO), env=env)

    try:
        with open(logfile, "w", encoding="utf-8") as f:
            f.write("[RVC] 变声任务启动\n")

        # 1) 独立环境（Python 3.10 系统 python，首次约 5–15 分钟）
        if not RVC_PY.exists():
            with open(logfile, "a", encoding="utf-8") as f:
                f.write("[RVC] 首次运行：创建变声环境（一次性，约 5–15 分钟）\n")
            run(["bash", "-lc", "apt-get update -qq && apt-get install -y -qq python3.10-venv"])
            run(["/usr/bin/python3", "-m", "venv", str(RVC_VENV)])
            run([str(RVC_PY), "-m", "pip", "install", "-U", "pip", "-i", PIP_MIRROR])
            run([str(RVC_PY), "-m", "pip", "install", "rvc-python", "demucs", "-i", PIP_MIRROR])

        probe = subprocess.run(
            [str(RVC_PY), "-c", "import rvc_python, demucs"],
            capture_output=True, cwd=str(REPO), env=env,
        )
        if probe.returncode != 0:
            run([str(RVC_PY), "-m", "pip", "install", "rvc-python", "demucs", "-i", PIP_MIRROR])

        # 2) 跑变声流水线
        outdir = OUTROOT / time.strftime("rvc_%Y%m%d-%H%M%S")
        cmd = [
            str(RVC_PY), str(RVC_SCRIPT),
            "--input", str(song_path),
            "--model", str(model_path),
            "--index", str(index_path or ""),
            "--pitch", str(int(pitch or 0)),
            "--outdir", str(outdir),
        ]
        run(cmd)

        mp3 = outdir / "audio_rvc.mp3"
        RVC["result"] = str(mp3) if mp3.exists() else None
        with open(logfile, "a", encoding="utf-8") as f:
            f.write(f"[RVC] {'✅ 完成：' + str(mp3) if mp3.exists() else '❌ 未产出 audio_rvc.mp3，请看上方日志'}\n")
            if mp3.exists():
                RVC["applied"] = False
    except Exception as e:
        with open(logfile, "a", encoding="utf-8") as f:
            f.write(f"[RVC] ❌ 异常：{e}\n")


def _seedvc_worker(song_path, ref_path, pitch, logfile):
    env = dict(os.environ)
    env["HF_ENDPOINT"] = "https://hf-mirror.com"
    env["HF_HOME"] = "/root/autodl-tmp/hf-seedvc"

    def run(cmd, cwd=None):
        with open(logfile, "a", encoding="utf-8") as f:
            f.write("\n$ " + " ".join(map(str, cmd)) + "\n")
            f.flush()
            subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=cwd or str(REPO), env=env)

    try:
        with open(logfile, "w", encoding="utf-8") as f:
            f.write("[SeedVC] 零样本变声任务启动\n")

        # 1) 仓库 + 独立环境（Python 3.10，首次约 10–20 分钟）
        if not SVC_PY.exists():
            with open(logfile, "a", encoding="utf-8") as f:
                f.write("[SeedVC] 首次运行：安装环境（一次性，约 10–20 分钟）\n")
            run(["bash", "-lc",
                 "source /etc/network_turbo 2>/dev/null; "
                 f"[ -d {SVC_DIR} ] || git clone https://github.com/Plachtaa/seed-vc.git {SVC_DIR}; "
                 "unset http_proxy https_proxy; "
                 "apt-get update -qq && apt-get install -y -qq python3.10-venv; "
                 f"/usr/bin/python3 -m venv {SVC_VENV}"])
            run([str(SVC_PY), "-m", "pip", "install", "-U", "pip", "-i", PIP_MIRROR])
            run([str(SVC_PY), "-m", "pip", "install", "torch", "torchaudio", "-i", PIP_MIRROR])
            run([str(SVC_PY), "-m", "pip", "install", "demucs", "-i", PIP_MIRROR])
            run([str(SVC_PY), "-m", "pip", "install", "-r", str(SVC_DIR / "requirements.txt"), "-i", PIP_MIRROR])

        probe = subprocess.run(
            [str(SVC_PY), "-c", "import demucs"], capture_output=True, env=env,
        )
        if probe.returncode != 0:
            run([str(SVC_PY), "-m", "pip", "install", "demucs", "-i", PIP_MIRROR])

        # 2) 跑零样本变声流水线
        outdir = OUTROOT / time.strftime("seedvc_%Y%m%d-%H%M%S")
        cmd = [
            str(SVC_PY), str(SVC_SCRIPT),
            "--input", str(song_path),
            "--reference", str(ref_path),
            "--pitch", str(int(pitch or 0)),
            "--steps", "40",
            "--outdir", str(outdir),
        ]
        run(cmd, cwd=str(SVC_DIR))

        mp3 = outdir / "audio_vc.mp3"
        RVC["result"] = str(mp3) if mp3.exists() else None
        with open(logfile, "a", encoding="utf-8") as f:
            f.write(f"[SeedVC] {'✅ 完成：' + str(mp3) if mp3.exists() else '❌ 未产出 audio_vc.mp3，请看上方日志'}\n")
            if mp3.exists():
                RVC["applied"] = False
    except Exception as e:
        with open(logfile, "a", encoding="utf-8") as f:
            f.write(f"[SeedVC] ❌ 异常：{e}\n")


def start_rvc(vc_mode, song_choice, model_pth, index_file, pitch, ref_audio):
    if RVC.get("running"):
        return "⏳ 已有变声任务在进行，请等待"
    if not song_choice or "|" not in str(song_choice):
        return "❌ 请先选择要转换的歌曲（点「🔄 刷新进度」可刷新歌曲列表）"

    song_path = Path(song_choice.split("|", 1)[1].strip())
    if not song_path.exists():
        return f"❌ 找不到歌曲文件：{song_path}"

    ts = time.strftime("%Y%m%d-%H%M%S")
    logfile = OUTROOT / f"vc_{ts}.log"
    RVC.update({"running": True, "t0": time.time(), "logfile": str(logfile),
                "result": None, "applied": True})

    if "零样本" in (vc_mode or ""):
        # Seed-VC：参考音频即可
        if not ref_audio:
            RVC["running"] = False
            return "❌ 零样本模式需要上传目标音色的参考音频（5–30 秒）"
        mdir = OUTROOT / f"vcref_{ts}"
        mdir.mkdir(parents=True, exist_ok=True)
        ref_path = mdir / (Path(ref_audio).name or "ref.wav")
        shutil.copy(ref_audio, ref_path)

        def boot():
            try:
                _seedvc_worker(song_path, ref_path, pitch, str(logfile))
            finally:
                RVC["running"] = False
        threading.Thread(target=boot, daemon=True).start()
        return "🗣️ 零样本变声已启动！首次会安装环境（10–20 分钟），之后每首约 3–6 分钟。"

    # RVC 模式：必须有 .pth
    if not model_pth:
        RVC["running"] = False
        return "❌ RVC 模式需要上传声音模型（.pth）；如果只有参考音频，请切换到「零样本」模式"
    mdir = OUTROOT / f"rvcmodels_{ts}"
    mdir.mkdir(parents=True, exist_ok=True)
    model_path = mdir / Path(model_pth).name
    shutil.copy(model_pth, model_path)
    index_path = ""
    if index_file:
        index_path = mdir / Path(index_file).name
        shutil.copy(index_file, index_path)

    def boot2():
        try:
            _rvc_worker(song_path, model_path, index_path, pitch, str(logfile))
        finally:
            RVC["running"] = False
    threading.Thread(target=boot2, daemon=True).start()
    return "🗣️ RVC 变声任务已启动！首次运行会先安装环境（5–15 分钟）。"


# ---------- 统一刷新 ----------

def refresh_progress(abc_input_cur, use_abc_cur, song_sel_cur):
    # RVC 变声状态
    rvc_txt = "未开始"
    rvc_html_out = gr.update()
    songs_out = gr.update(choices=_song_choices())
    if RVC.get("logfile"):
        if RVC.get("running"):
            tail = _log_tail(RVC["logfile"], 5)
            rvc_txt = f"⏳ **变声进行中** · 已运行 {_rvc_elapsed()}\n\n```\n{tail}\n```"
        elif RVC.get("result") and not RVC.get("applied"):
            rvc_html_out = _audio_html(RVC["result"])
            RVC["applied"] = True
            rvc_txt = "✅ 变声完成！试听和下载见上方「变声结果」播放器"
        elif RVC.get("result"):
            rvc_txt = "✅ 变声完成（结果已在播放器中）"
        else:
            tail = _log_tail(RVC["logfile"], 8)
            rvc_txt = f"❌ 变声未成功，日志如下（可发给助手排查）：\n```\n{tail}\n```"

    # SheetSage2 状态
    ss2_txt = "未开始"
    ss2_out_abc = gr.update()  # 默认不改动
    ss2_out_chk = gr.update()
    if SS2.get("logfile"):
        if SS2.get("running"):
            tail = _log_tail(SS2["logfile"], 8)
            ss2_txt = (
                f"⏳ **转录进行中** · 已运行 {_ss2_elapsed()} · {_ss2_stage()}\n\n"
                f"```\n{tail}\n```"
            )
        elif SS2.get("abc") and not SS2.get("applied"):
            ss2_out_abc = SS2["abc"]
            ss2_out_chk = True
            SS2["applied"] = True
            ss2_txt = "✅ 转录完成！乐谱已自动填入下方「自定义 ABC 乐谱」框，请选择「翻唱改编」模式并点「开始生成」"
        elif SS2.get("abc"):
            ss2_txt = "✅ 转录完成（乐谱已在生成表单中）"
        else:
            tail = _log_tail(SS2["logfile"], 8)
            ss2_txt = f"❌ 转录未成功，日志如下（可发给助手排查）：\n```\n{tail}\n```"

    # 生成状态
    proc = STATE.get("proc")
    ss2_prefix = ""
    if SS2.get("running"):
        ss2_prefix = f"🎙️ **转录进行中** · {_ss2_elapsed()} · {_ss2_stage()}\n\n"
    if STATE.get("logfile") is None:
        d, a = _latest_run_with_audio()
        gen = ("等待开始……", "", "", "")
        if a:
            a = _to_mp3(a)
            gen = (
                f"{ss2_prefix}📂 当前没有进行中的任务；这是最近一次的生成结果（{d.name}）",
                _audio_html(a),
                _read_abc(d),
                _log_tail(STATE.get("logfile"), 10) if STATE.get("logfile") else "",
            )
    elif proc is not None and proc.poll() is None:
        pct = _percent()
        head = f"⏳ 生成中…… {('最新阶段进度 ~' + pct) if pct else ''}"
        gen = (f"{ss2_prefix}{head}", "", "", _log_tail(STATE["logfile"]))
    else:
        audio = _to_mp3(_find_audio(STATE.get("outdir")))
        if audio:
            gen = (
                f"{ss2_prefix}✅ 完成！《{STATE['outdir'].name}》成品保存在服务器：{STATE['outdir']}",
                _audio_html(audio),
                _read_abc(STATE["outdir"]),
                _log_tail(STATE["logfile"], 10),
            )
        else:
            gen = (
                f"{ss2_prefix}❌ 进程已结束但没有生成音频，请展开日志查看并截图发给助手",
                "", "", _log_tail(STATE["logfile"]),
            )

    return (*gen, ss2_txt, ss2_out_chk, ss2_out_abc, rvc_txt, songs_out, rvc_html_out)


# ---------- 界面 ----------

with gr.Blocks(title="YuE2 音乐生成工作台") as demo:
    gr.Markdown(
        "# 🎵 YuE2 音乐生成工作台\n"
        "两个页签：**音乐生成**（写歌/翻唱）与 **声音克隆**（变声）——进度都会自动刷新。"
    )
    with gr.Tabs():
        with gr.TabItem("🎵 音乐生成"):
            gr.Markdown(
                "选好语言、人声、曲风、乐器、速度 → 写下歌词 → 点「开始生成」→ 几分钟后在右侧试听、下载。\n\n"
                "💡 **歌词**用 `[Verse]`（主歌）、`[Chorus]`（副歌）分段，写得越完整歌曲越长；"
                "想加个性化的风格描述就填「补充风格」。\n\n"
                "🎲 技巧：生成满意的那首后，把它的种子数字记下来，以后可复现同款。"
            )
            with gr.Row():
                with gr.Column():
                    song_name = gr.Textbox(
                        label="📝 歌曲名称（建议用英文/数字，如 summer_breeze）",
                        placeholder="给这首歌起个名字，比如：summer_breeze",
                        value="",
                    )
                    lang = gr.Dropdown(
                        list(LANG_MAP.keys()),
                        value="中文",
                        label="🌐 歌词语言",
                    )
                    vocal = gr.Dropdown(
                        list(VOCAL_MAP.keys()),
                        value="男声 · 低沉磁性",
                        label="🎤 人声",
                    )
                    genre = gr.Dropdown(
                        list(GENRE_MAP.keys()),
                        value="流行",
                        label="🎸 曲风",
                    )
                    instruments = gr.CheckboxGroup(
                        list(INSTRUMENT_MAP.keys()),
                        value=["钢琴", "木吉他"],
                        label="🎻 乐器（可多选）",
                    )
                    tempo_bpm = gr.Slider(
                        60, 160, value=90, step=1,
                        label="🎵 速度（BPM，数值越小越抒情、越大越亢奋）",
                    )
                    cfg_scale = gr.Slider(
                        0, 20, value=1.0, step=0.5,
                        label="🎚️ 服从度（调高更严格服从风格描述，人声更稳；默认 1 = 官方默认）",
                    )
                    style = gr.Textbox(
                        label="✨ 补充风格（可选，高级玩家自由发挥）",
                        placeholder="例：80s retro, dreamy atmosphere, lush reverb / 留空也完全没问题",
                        value="",
                        lines=1,
                    )
                    lyrics = gr.Textbox(
                        label="✍️ 歌词（[Verse]=主歌 [Chorus]=副歌，段落越多歌越长）",
                        value=DEFAULT_LYRICS,
                        lines=10,
                    )
                    cot_label = gr.Radio(
                        list(COT_MAP.keys()),
                        value="智能创作（推荐，可编辑旋律与和弦）",
                        label="⚙️ 生成模式",
                    )
                    seed = gr.Textbox(
                        label="🎲 随机种子（可选，填数字可复现同一首歌）",
                        value="",
                        placeholder="留空 = 每次随机",
                    )
                    with gr.Accordion("🎼 进阶：自定义 ABC 乐谱（锁旋律重编曲）", open=False):
                        gr.Markdown(
                            "勾选后，生成将**演唱你贴入的乐谱**而不是自己谱曲。\n\n"
                            "玩法①：把上次生成结果的乐谱复制过来，改几个音符/和弦 → 重新生成；\n"
                            "玩法②：翻唱改编——用下面「翻唱」面板转录原曲，乐谱会自动填入这里；\n"
                            "（需配合「智能创作」或「翻唱改编」模式）"
                        )
                        use_abc = gr.Checkbox(label="使用下面贴入的 ABC 乐谱", value=False)
                        abc_input = gr.Textbox(
                            label="ABC 乐谱内容",
                            placeholder="X:1\nT:My Melody\nM:4/4\nL:1/8\nK:C\n...",
                            lines=8,
                            value="",
                        )
                    with gr.Accordion("🎙️ 翻唱：上传原曲自动转谱", open=False):
                        gr.Markdown(
                            "上传一首现成的歌（mp3/wav）→ 点「转录」→ 自动得到它的 ABC 旋律谱"
                            "（首次会自动安装转录环境，约 15–30 分钟；之后每次约 1–2 分钟）→ "
                            "转录完成后乐谱自动填入上方乐谱框，选「翻唱改编」模式、换上新歌词风格即可翻唱。"
                        )
                        audio_up = gr.Audio(label="上传原曲", sources=["upload"], type="filepath")
                        btn_ss2 = gr.Button("🎹 转录为 ABC 乐谱")
                        ss2_status = gr.Markdown("未开始")
                    btn = gr.Button("🎬 开始生成", variant="primary", size="lg")
                with gr.Column():
                    status = gr.Markdown("等待开始……")
                    audio_html = gr.HTML(label="🎧 成品试听与下载")
                    with gr.Accordion("🎼 结果乐谱（可复制到左侧进阶面板修改后重生成）", open=False):
                        abc_box = gr.Textbox(label="", lines=8, interactive=False, show_label=False)
                    with gr.Accordion("📜 运行日志（排查问题时展开）", open=False):
                        logbox = gr.Textbox(label="", lines=10, interactive=False, show_label=False)
                    btn_refresh = gr.Button("🔄 刷新进度")

        with gr.TabItem("🗣️ 声音克隆"):
            gr.Markdown(
                "把「音乐生成」页签里做好的歌，唱成**任意目标音色**。\n\n"
                "**零样本模式（推荐）**：上传 5–30 秒目标音色参考音频（mp3/wav，干净人声最佳），无需训练；"
                "**RVC 模式**：上传训练好的 .pth 模型（社区下载或自训）。\n\n"
                "流程全自动：分离人声与伴奏 → 人声换成目标音色 → 混回伴奏 → 输出 mp3。\n\n"
                "⚠️ 仅限自用与已授权场景，注意声音权益。"
            )
            with gr.Row():
                with gr.Column():
                    vc_mode = gr.Radio(
                        ["参考音频零样本（Seed-VC，传 mp3 即可，推荐）", "已训练模型（RVC .pth）"],
                        value="参考音频零样本（Seed-VC，传 mp3 即可，推荐）",
                        label="🔀 变声方式",
                    )
                    vc_ref = gr.Audio(
                        label="目标音色参考音频（零样本模式用，5–30 秒）",
                        sources=["upload"], type="filepath",
                    )
                    rvc_model = gr.File(label="RVC 声音模型（.pth，仅 RVC 模式需要）", file_types=[".pth"])
                    rvc_index = gr.File(label="检索索引（.index，可选，提升相似度）", file_types=[".index"])
                    song_sel = gr.Dropdown(
                        choices=_song_choices(), label="选择要变声的歌曲（点「🔄 刷新」更新列表）",
                    )
                    rvc_pitch = gr.Slider(
                        -12, 12, value=0, step=1,
                        label="🎚️ 变调（半音；音高不匹配时用：偏高 +，偏低 -）",
                    )
                    btn_rvc = gr.Button("🗣️ 开始变声", variant="primary", size="lg")
                with gr.Column():
                    rvc_result = gr.HTML(label="变声结果试听与下载")
                    rvc_status = gr.Markdown("未开始")
                    btn_refresh2 = gr.Button("🔄 刷新")

    btn.click(
        start_generate,
        inputs=[song_name, lang, vocal, genre, instruments, tempo_bpm, style, cfg_scale,
                lyrics, cot_label, seed, use_abc, abc_input],
        outputs=[status],
    )
    btn_ss2.click(start_transcribe, inputs=[audio_up], outputs=[ss2_status])
    btn_rvc.click(
        start_rvc,
        inputs=[vc_mode, song_sel, rvc_model, rvc_index, rvc_pitch, vc_ref],
        outputs=[rvc_status],
    )
    btn_refresh.click(
        refresh_progress,
        inputs=[abc_input, use_abc, song_sel],
        outputs=[status, audio_html, abc_box, logbox, ss2_status, use_abc, abc_input,
                 rvc_status, song_sel, rvc_result],
    )
    btn_refresh2.click(
        refresh_progress,
        inputs=[abc_input, use_abc, song_sel],
        outputs=[status, audio_html, abc_box, logbox, ss2_status, use_abc, abc_input,
                 rvc_status, song_sel, rvc_result],
    )
    # 自动刷新：优先 gradio 5 的 Timer 组件，退回 demo.load(every=)，再退回手动按钮
    _refresh_args = dict(
        inputs=[abc_input, use_abc, song_sel],
        outputs=[status, audio_html, abc_box, logbox, ss2_status, use_abc, abc_input,
                 rvc_status, song_sel, rvc_result],
    )
    if hasattr(gr, "Timer"):
        try:
            _timer = gr.Timer(10)
            _timer.tick(refresh_progress, **_refresh_args)
            print("[yue2-webui] 已启用 gr.Timer 自动刷新（每 10 秒）")
        except Exception as _e:
            print(f"[yue2-webui] gr.Timer 启动失败：{_e}，尝试 every 参数")
            try:
                demo.load(refresh_progress, every=10, **_refresh_args)
            except TypeError:
                print("[yue2-webui] 自动刷新不可用，请使用「刷新进度」按钮")
    else:
        try:
            demo.load(refresh_progress, every=10, **_refresh_args)
        except TypeError:
            print("[yue2-webui] 自动刷新不可用，请使用「刷新进度」按钮")

try:
    demo.queue(max_size=8, default_concurrency_limit=1)
except TypeError:
    try:
        demo.queue(concurrency_count=1)
    except TypeError:
        demo.queue()
demo.launch(server_name="0.0.0.0", server_port=6006, show_error=True)
