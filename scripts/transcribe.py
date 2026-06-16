#!/usr/bin/env python3
"""
音视频转写工具 — 使用 faster-whisper 将视频/音频文件或在线视频转写为文字稿。
支持 CUDA GPU 加速、本地文件转写、以及哔哩哔哩等在线视频下载后转写。

用法：
    # 本地文件
    python3 transcribe.py --input video.mp4 --language zh --model base
    # 在线视频（哔哩哔哩等 yt-dlp 支持的站点）
    python3 transcribe.py --url "https://www.bilibili.com/video/BV1xx411c7XX" --language zh --model base
"""

import argparse
import atexit
import os
import re
import subprocess
import sys
import tempfile


# Video and audio file extensions
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma"}


def is_video_file(filepath: str) -> bool:
    """Check if a file is a video based on its extension."""
    ext = os.path.splitext(filepath)[1].lower()
    return ext in VIDEO_EXTENSIONS


def is_audio_file(filepath: str) -> bool:
    """Check if a file is an audio file based on its extension."""
    ext = os.path.splitext(filepath)[1].lower()
    return ext in AUDIO_EXTENSIONS


def is_16khz_mono_wav(filepath: str) -> bool:
    """Check if a WAV file is already 16kHz mono PCM."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext != ".wav":
        return False
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=sample_rate,channels,codec_name",
                "-of", "default=noprint_wrappers=1:nokey=1",
                filepath,
            ],
            capture_output=True, text=True, timeout=30,
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 3:
            sample_rate = lines[0].strip()
            channels = lines[1].strip()
            codec = lines[2].strip()
            return sample_rate == "16000" and channels == "1" and codec == "pcm_s16le"
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    return False


def extract_audio(input_path: str, output_path: str) -> None:
    """
    Extract 16kHz mono PCM WAV audio from a video or audio file using ffmpeg.
    If the input is already a 16kHz mono WAV, skip conversion.
    """
    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v"}
    ext = os.path.splitext(input_path)[1].lower()

    if ext in video_exts:
        print("正在从视频中提取音频...", file=sys.stderr)
    else:
        print("正在处理音频文件...", file=sys.stderr)

    try:
        subprocess.run(
            [
                "ffmpeg", "-i", input_path,
                "-vn", "-acodec", "pcm_s16le",
                "-ar", "16000", "-ac", "1",
                output_path,
                "-y", "-loglevel", "error",
            ],
            check=True, timeout=600,
        )
    except FileNotFoundError:
        print("错误：未找到 ffmpeg，请先安装 ffmpeg。", file=sys.stderr)
        print("macOS: brew install ffmpeg", file=sys.stderr)
        print("Ubuntu/Debian: sudo apt install ffmpeg", file=sys.stderr)
        print("Windows: 从 https://ffmpeg.org/download.html 下载", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"错误：ffmpeg 处理失败：{e}", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("错误：ffmpeg 处理超时（文件可能过大或损坏）", file=sys.stderr)
        sys.exit(1)


def detect_device(requested: str) -> tuple:
    """Determine device and compute_type. Returns (device, compute_type)."""
    if requested == "cpu":
        print("使用设备: cpu (int8)", file=sys.stderr)
        return "cpu", "int8"

    if requested == "cuda":
        # Try to import torch and check CUDA
        try:
            import torch
            if torch.cuda.is_available():
                print("使用设备: cuda (float16)", file=sys.stderr)
                return "cuda", "float16"
            else:
                print("警告：指定了 cuda 但未检测到 CUDA，回退到 CPU。", file=sys.stderr)
                print("使用设备: cpu (int8)", file=sys.stderr)
                return "cpu", "int8"
        except ImportError:
            print("警告：指定了 cuda 但未安装 torch，回退到 CPU。", file=sys.stderr)
            print("使用设备: cpu (int8)", file=sys.stderr)
            return "cpu", "int8"

    # auto: try CUDA first, then fall back to CPU
    try:
        import torch
        if torch.cuda.is_available():
            print("自动检测到 CUDA，使用设备: cuda (float16)", file=sys.stderr)
            return "cuda", "float16"
    except ImportError:
        pass

    print("使用设备: cpu (int8)", file=sys.stderr)
    return "cpu", "int8"


def sanitize_filename(name: str) -> str:
    """Remove characters unsafe for filenames."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()[:100]


def download_from_url(url: str, temp_dir: str) -> tuple:
    """
    Download a video from a URL using yt-dlp and return (file_path, clean_title).
    Raises ImportError if yt-dlp is not installed.
    """
    try:
        import yt_dlp
    except ImportError:
        print(
            "错误：未安装 yt-dlp，请运行：pip install yt-dlp",
            file=sys.stderr,
        )
        sys.exit(1)

    print("正在获取视频信息...", file=sys.stderr)

    # First: fetch metadata only
    opts = {"quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            print(f"错误：无法获取视频信息：{e}", file=sys.stderr)
            sys.exit(1)

    title = info.get("title", "unknown")
    duration = info.get("duration", 0)
    print(f"视频标题: {title}", file=sys.stderr)
    if duration:
        print(f"视频时长: {duration:.0f} 秒", file=sys.stderr)

    # Download to temp dir
    safe_title = sanitize_filename(title)
    outtmpl = os.path.join(temp_dir, f"{safe_title}.%(ext)s")

    print("正在下载视频...", file=sys.stderr)

    # Closure state for progress hook
    last_pct = [-1]

    def progress_hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = int(downloaded / total * 100)
                if pct >= last_pct[0] + 20:
                    print(
                        f"[下载进度] {pct}% — "
                        f"{downloaded / 1024 / 1024:.0f}MB / {total / 1024 / 1024:.0f}MB",
                        file=sys.stderr,
                        flush=True,
                    )
                    last_pct[0] = pct
        elif d["status"] == "finished":
            print("下载完成，正在处理...", file=sys.stderr)

    download_opts = {
        "outtmpl": outtmpl,
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [progress_hook],
    }

    with yt_dlp.YoutubeDL(download_opts) as ydl:
        try:
            ydl.download([url])
        except Exception as e:
            print(f"错误：下载失败：{e}", file=sys.stderr)
            sys.exit(1)

    # Find the downloaded file
    downloaded = None
    for f in os.listdir(temp_dir):
        if f.startswith(safe_title):
            candidate = os.path.join(temp_dir, f)
            if os.path.isfile(candidate):
                downloaded = candidate
                break

    if not downloaded or not os.path.isfile(downloaded):
        print("错误：下载完成但未找到输出文件", file=sys.stderr)
        sys.exit(1)

    print("视频下载完成", file=sys.stderr)
    return downloaded, safe_title



def main():
    parser = argparse.ArgumentParser(
        description="音视频转写工具 — 使用 faster-whisper 将视频/音频或在线视频转写为文字稿"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--input", "-i",
        help="输入视频/音频文件路径",
    )
    source.add_argument(
        "--url", "-u",
        help="在线视频链接（支持哔哩哔哩等 yt-dlp 兼容站点）",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="输出文本文件路径（默认：<input>.transcript.txt）",
    )
    parser.add_argument(
        "--language", "-l", default="auto",
        choices=["zh", "en", "auto"],
        help="转写语言（默认：auto）",
    )
    parser.add_argument(
        "--model", "-m", default="base",
        choices=["tiny", "base", "small", "medium", "large-v3"],
        help="Whisper 模型大小（默认：base）",
    )
    parser.add_argument(
        "--device", "-d", default="auto",
        choices=["auto", "cpu", "cuda"],
        help="计算设备（默认：auto）",
    )
    args = parser.parse_args()

    # Handle URL input: download first, then treat as local file
    if args.url:
        temp_dir = tempfile.mkdtemp(prefix="transcribe_dl_")
        atexit.register(lambda d=temp_dir: os.path.exists(d) and __import__('shutil').rmtree(d, ignore_errors=True))
        downloaded_file, safe_title = download_from_url(args.url, temp_dir)
        args.input = downloaded_file
        args._downloaded_temp = downloaded_file  # mark for cleanup
        output_path = args.output if args.output else f"{safe_title}.transcript.txt"
    elif args.input:
        # Validate input file exists
        if not os.path.isfile(args.input):
            print(f"错误：找不到文件 '{args.input}'", file=sys.stderr)
            sys.exit(1)
        input_stem = os.path.splitext(os.path.basename(args.input))[0]
        output_path = args.output if args.output else f"{input_stem}.transcript.txt"
    else:
        # Should not happen with mutually_exclusive_group(required=True)
        parser.error("必须指定 --input 或 --url")

    # Detect device
    device, compute_type = detect_device(args.device)

    # Map language: "auto" → None (let model detect)
    language = None if args.language == "auto" else args.language

    # Prepare audio for transcription
    if is_16khz_mono_wav(args.input):
        audio_path = args.input
        print("检测到 16kHz 单声道 WAV，跳过音频转换。", file=sys.stderr)
    else:
        temp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        audio_path = temp_wav.name
        temp_wav.close()
        # Register cleanup
        atexit.register(lambda: os.path.exists(audio_path) and os.unlink(audio_path))
        extract_audio(args.input, audio_path)

    try:
        # Import faster_whisper here so argparse --help works without the dependency
        from faster_whisper import WhisperModel

        # Load model (may trigger download on first run)
        print(f"正在加载/下载模型 {args.model}...", file=sys.stderr)
        model = WhisperModel(args.model, device=device, compute_type=compute_type)
        print("模型加载完成", file=sys.stderr)

        # Transcribe
        segments, info = model.transcribe(audio_path, language=language, task="transcribe")

        # Print language detection info
        print(f"检测到语言: {info.language}（概率: {info.language_probability:.2%}）", file=sys.stderr)
        print(f"音频时长: {info.duration:.2f} 秒", file=sys.stderr)

        # Collect segments, log progress at meaningful intervals
        full_text_parts = []
        segment_count = 0
        last_log_pct = -1

        for segment in segments:
            text = segment.text.strip()
            if text:
                print(text, flush=True)
                full_text_parts.append(text)
            segment_count += 1

            # Log progress at each 10% step of audio duration
            current_pct = int(segment.end / info.duration * 100) if info.duration > 0 else 100
            if current_pct >= last_log_pct + 10:
                print(
                    f"[转写进度] {min(current_pct, 100)}% — "
                    f"{segment.end:.1f}s / {info.duration:.1f}s — "
                    f"已识别 {segment_count} 个片段",
                    file=sys.stderr,
                    flush=True,
                )
                last_log_pct = current_pct

        # Write output file
        full_text = "\n".join(full_text_parts)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_text)

        print(
            f"\n转写完成！共 {segment_count} 个片段，输出文件：{output_path}",
            file=sys.stderr,
        )

    except ImportError:
        print(
            "错误：未安装 faster-whisper，请运行：pip install faster-whisper",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(f"错误：转写失败：{e}", file=sys.stderr)
        sys.exit(1)
    finally:
        # Clean up temp audio file if we created one
        if audio_path != args.input and os.path.exists(audio_path):
            try:
                os.unlink(audio_path)
            except OSError:
                pass
        # Clean up downloaded temp video (temp_dir cleanup happens via atexit)


if __name__ == "__main__":
    main()
