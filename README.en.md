# 🎵 YuE2 Studio — Cloud AI Music Workstation

[简体中文](README.md) · [English](README.en.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![UI](https://img.shields.io/badge/UI-Gradio-orange.svg)
![GPU](https://img.shields.io/badge/GPU-24GB%2B%20VRAM-red.svg)
![Model](https://img.shields.io/badge/model-YuE2--3B-informational)

A cloud music-generation workstation built on the open-source
[YuE2](https://github.com/multimodal-art-projection/YuE) model:
**fill in a form to write songs, cover any existing song, and edit music at score level** —
all from the browser.

## Features

| Feature | Description |
|---------|-------------|
| 🎬 Smart composition | Fill a form (language / vocals / genre / instruments / tempo) + write lyrics → get a full song with an editable ABC score |
| 🎙️ Cover & rearrange | Upload any song → auto-transcribed to an ABC melody score by SheetSage2 → re-sing it in a new style / vocals / lyrics |
| 🎼 Score editing | Edit notes and chords in the ABC score → re-render; change exactly the two notes you dislike |
| ⚡ Fast mode | Skip score planning entirely — one click to a demo |
| 🎧 In-page preview & download | Audio is embedded as base64, so downloads bypass the AutoDL web proxy (which breaks on file transfers) |
| 📈 Live progress | Duration, stage, percentage and log tail refresh in real time |

## Architecture

```
Browser ── AutoDL "custom service" proxy (port 6006) ──> Gradio workbench (yue2_webui.py, yue2 conda env)
                                                          │
                                                          ├── Generation: base-env python + YuE repo examples/generate.py
                                                          │        (--request takes a JSON file path; --output must be a fresh dir)
                                                          ├── Transcription: YuE/.venv-sheetsage2 + SheetSage2
                                                          └── Outputs: output_web/<timestamp>/  (audio.flac → ffmpeg → mp3)
```

## Quick start (fresh AutoDL instance)

1. Rent an **RTX 4090 / 24 GB** instance (image: PyTorch 2.x + CUDA 12.x + Ubuntu 22.04)
2. Upload this repo to `/root/autodl-tmp/yue2-studio/`
3. Deploy (~20–40 min, including a 15 GB weight download):

   ```bash
   cd /root/autodl-tmp/yue2-studio && bash bin/setup.sh
   ```

4. Start the web workbench:

   ```bash
   bash bin/start.sh
   ```

5. Open the UI from the AutoDL console (“自定义服务” — custom service) and start writing songs.

> ⚠️ The AutoDL data disk does **not** survive image saves: on a new instance, re-upload the repo
> and re-run `setup.sh` (idempotent — completed steps are skipped automatically).

## Generic deployment (any Linux GPU box with ≥ 24 GB VRAM)

This project is **not tied to AutoDL** — any Ubuntu machine with an NVIDIA GPU (≥ 24 GB VRAM,
Ampere architecture or newer) works:

```bash
git clone https://github.com/suoya437-oss/YuE2-Studio.git && cd YuE2-Studio
bash bin/setup.sh            # optional: export YUE2_BASE=/data to set the workspace root (default /root/autodl-tmp)
bash bin/preinstall_envs.sh  # optional: pre-install transcription / voice-clone environments
bash bin/start.sh            # then open http://<machine-ip>:6006
```

Differences vs AutoDL, in three points: the workspace root is set with `YUE2_BASE`; the UI is
reached directly at `IP:6006` (enable login auth via `YUE2_WEBUI_USER` / `YUE2_WEBUI_PASS`
whenever the port is exposed to the public internet); on overseas machines the China pip/HF
mirrors can be replaced with official sources (usually faster).
Details in the [deploy guide](docs/deploy-guide.md) (Chinese).

## Daily use

- Boot the instance → `bash bin/start.sh` → open the UI from the console
- Page won't open → click “custom service” again in the console (the proxy URL goes stale after instance migration)
- Done for the day → shut down from the console (billed by the hour; the data disk is kept)

## Documentation (Chinese)

- [Deploy guide](docs/deploy-guide.md) — choosing GPUs and platforms, the full deployment flow
- [Three generation modes](docs/modes.md) — smart composition / cover rearrange / fast mode
- [Troubleshooting: 22 real-world pitfalls](docs/troubleshooting.md) — read this before deploying

## Hardware & cost

- Requirement: NVIDIA GPU with ≥ 24 GB VRAM and BF16 support (3090 / 4090 / L4 / A10 / A100)
- Reference: AutoDL 4090 ≈ ¥2/hour; 2–10 minutes per song

## License (important)

- **This project's code**: MIT License — free to use and modify, see [LICENSE](LICENSE).
- **The deploy scripts only guide model downloads.** Model weights (YuE2-3B, SheetSage2, …)
  belong to their respective authors; the YuE2 weights are **CC BY-NC 4.0: personal and creative
  use is fine, commercial use requires separate authorization from the model authors**.
- Please do not re-distribute the downloaded model weights.
