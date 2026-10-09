import os
import sys
import subprocess
import threading
import importlib.util
import math
import traceback
import random
import builtins
import shutil
import tempfile
import concurrent.futures
import gc
import re
import queue
import multiprocessing
multiprocessing.freeze_support()

# Khi chạy dạng .exe: luôn làm việc ngay trong thư mục chứa file .exe
# (để thư mục Render_Workspace/Output nằm cạnh app, không phụ thuộc nơi bấm mở)
if getattr(sys, 'frozen', False):
    try: os.chdir(os.path.dirname(sys.executable))
    except Exception: pass

# =========================================================================
# 1. KÍCH HOẠT GHOST MODE (TÀNG HÌNH TASKBAR VÀ MÀN HÌNH ĐEN)
# =========================================================================
if os.name == 'nt' and sys.executable.lower().endswith('python.exe'):
    pythonw_path = sys.executable[:-10] + "pythonw.exe"
    if os.path.exists(pythonw_path):
        subprocess.Popen([pythonw_path] + sys.argv, creationflags=0x08000000)
        sys.exit()

class DummyOutput:
    def write(self, *args, **kwargs): pass
    def flush(self, *args, **kwargs): pass
    def isatty(self): return False

if sys.stdout is None: sys.stdout = DummyOutput()
if sys.stderr is None: sys.stderr = DummyOutput()

# =========================================================================
# 1.5 CHẾ ĐỘ "WORKER" MỞ HỘP THOẠI CHỌN FILE/THƯ MỤC TRONG TIẾN TRÌNH RIÊNG
#     Được chính app tự gọi lại (dùng sys.executable + cờ --pick-dialog) để
#     mở hộp thoại tkinter độc lập, không đụng main-thread của NiceGUI/webview.
#     QUAN TRỌNG: khối này phải nằm TRƯỚC phần auto-installer & import
#     moviepy/nicegui bên dưới, và phải sys.exit() ngay sau khi xong — nếu
#     không, khi đã đóng gói thành .exe, lệnh gọi lại chính mình sẽ chạy
#     tiếp xuống dưới và mở luôn 1 bản NiceGUI thứ hai (tranh cổng 8080),
#     khiến hộp thoại không bao giờ hiện ra (bị treo chờ tiến trình con).
# =========================================================================
if len(sys.argv) >= 2 and sys.argv[1] == "--pick-dialog":
    try:
        import tkinter as tk
        from tkinter import filedialog
        out_path = sys.argv[2]
        is_dir = sys.argv[3] == "1"
        multiple = sys.argv[4] == "1"
        title = sys.argv[5]
        ext_clean = sys.argv[6] if len(sys.argv) > 6 else "*.*"

        root = tk.Tk()
        root.withdraw()
        root.lift()
        root.attributes('-topmost', True)
        root.focus_force()
        try:
            if is_dir:
                res = filedialog.askdirectory(title=title)
                out = res if res else ""
            elif multiple:
                res = filedialog.askopenfilenames(title=title, filetypes=[("Media Files", ext_clean), ("All Files", "*.*")])
                out = "|||".join(res) if res else ""
            else:
                res = filedialog.askopenfilename(title=title, filetypes=[("Media Files", ext_clean), ("All Files", "*.*")])
                out = res if res else ""
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(out)
        finally:
            root.destroy()
    except Exception:
        sys.stderr.write(traceback.format_exc())
        sys.exit(1)
    sys.exit(0)

# =========================================================================
# 2. HỆ THỐNG BÙA CHỐNG LỖI METADATA
# =========================================================================
if getattr(sys, 'frozen', False):
    import importlib.metadata
    _orig_version = importlib.metadata.version
    def _patch_version(name):
        try: return _orig_version(name)
        except Exception: return "9.9.9"
    importlib.metadata.version = _patch_version
    
    _orig_dist = importlib.metadata.distribution
    class _DummyDist:
        version = "9.9.9"
        metadata = {"Name": "dummy"}
    def _patch_dist(name):
        try: return _orig_dist(name)
        except Exception: return _DummyDist()
    importlib.metadata.distribution = _patch_dist

# =========================================================================
# 3. HỆ THỐNG SMART AUTO-INSTALLER LÕI MỚI
# =========================================================================
REQUIRED_PACKAGES = {
    "moviepy": "moviepy",
    "nicegui": "nicegui",
    "imageio-ffmpeg": "imageio_ffmpeg",
    "selenium": "selenium",
    "pywebview": "webview" 
}

def get_missing_packages():
    missing = []
    for pip_name, module_name in REQUIRED_PACKAGES.items():
        if importlib.util.find_spec(module_name) is None:
            missing.append(pip_name)
    return missing

missing_packages = [] if getattr(sys, 'frozen', False) else get_missing_packages()

if missing_packages:
    import tkinter as tk
    from tkinter import ttk
    import time

    def install_and_restart():
        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            cmd = [sys.executable, "-m", "pip", "install"] + missing_packages
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags, check=True)
            lbl_status.config(text="Cài đặt hoàn tất. Đang khởi động...", fg="#38bdf8")
            root.update()
            time.sleep(1)
            root.destroy()
            subprocess.Popen([sys.executable] + sys.argv, creationflags=flags)
            sys.exit()
        except Exception as e:
            lbl_status.config(text="Lỗi mạng: Không thể tải thư viện.", fg="#ef4444")
            pb.stop()

    root = tk.Tk()
    root.title("System Setup")
    width, height = 400, 150
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')
    root.overrideredirect(True) 
    root.configure(bg="#0f172a")
    
    tk.Label(root, text="RENDER STUDIO PRO", font=("Segoe UI", 14, "bold"), bg="#0f172a", fg="#f8fafc").pack(pady=(20, 5))
    lbl_status = tk.Label(root, text=f"Đang thiết lập {len(missing_packages)} thư viện. Vui lòng chờ...", font=("Segoe UI", 9), bg="#0f172a", fg="#94a3b8")
    lbl_status.pack(pady=(0, 15))
    
    style = ttk.Style()
    style.theme_use('clam')
    style.configure("Horizontal.TProgressbar", troughcolor='#1e293b', background='#38bdf8', bordercolor='#0f172a', lightcolor='#38bdf8', darkcolor='#38bdf8')
    pb = ttk.Progressbar(root, style="Horizontal.TProgressbar", mode="indeterminate", length=300)
    pb.pack()
    pb.start(15)

    threading.Thread(target=install_and_restart, daemon=True).start()
    root.mainloop()
    sys.exit()

# =========================================================================
# 4. LÕI PHẦN MỀM CHÍNH 
# =========================================================================
try:
    from moviepy import VideoFileClip, AudioFileClip, concatenate_audioclips, concatenate_videoclips
    from moviepy.video.fx import CrossFadeIn, FadeIn, FadeOut, MultiplySpeed
    IS_V2 = True
except ImportError:
    from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_audioclips, concatenate_videoclips
    import moviepy.video.fx.all as vfx
    IS_V2 = False

try:
    from imageio_ffmpeg import get_ffmpeg_exe
    FFMPEG_EXE = get_ffmpeg_exe()
except:
    FFMPEG_EXE = "ffmpeg"

from nicegui import ui, run

WORKSPACE_DIR = "Render_Workspace"
TEMP_DIR = os.path.join(WORKSPACE_DIR, "Temp")
os.makedirs(TEMP_DIR, exist_ok=True)

def xoa_am_thanh(clip):
    if IS_V2: return clip.without_audio()
    return clip.set_audio(None)

# =========================================================================
# PIPELINE XỬ LÝ VIDEO BẰNG FFMPEG NATIVE (THAY MOVIEPY -> ÍT RAM HƠN, ĐẨY GPU KHI XUẤT)
# =========================================================================
def _run_ffmpeg(cmd, flags):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)

def _run_ffmpeg_with_progress(cmd, flags, total_duration=0, on_percent=None):
    """Chạy ffmpeg với '-progress pipe:1' để đọc tiến độ % theo thời gian thực.
    Trả về (returncode, stderr_bytes) tương thích với _run_ffmpeg."""
    full_cmd = cmd + ["-progress", "pipe:1", "-nostats"]
    try:
        proc = subprocess.Popen(full_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 creationflags=flags, universal_newlines=True, bufsize=1,
                                 encoding='utf-8', errors='ignore')
    except Exception:
        # Fallback nếu Popen lỗi vì lý do nào đó -> chạy kiểu cũ không có %
        result = _run_ffmpeg(cmd, flags)
        return result.returncode, result.stderr

    stderr_chunks = []
    def _read_stderr():
        try:
            for line in proc.stderr:
                stderr_chunks.append(line)
        except Exception:
            pass

    t_err = threading.Thread(target=_read_stderr, daemon=True)
    t_err.start()

    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            if line.startswith("out_time=") and total_duration and total_duration > 0 and on_percent:
                m = re.match(r"(\d+):(\d+):(\d+(?:\.\d+)?)", line.split("=", 1)[1])
                if m:
                    h, mi, s = m.groups()
                    secs = int(h) * 3600 + int(mi) * 60 + float(s)
                    pct = (secs / total_duration) * 100.0
                    on_percent(min(99.0, max(0.0, pct)))
            elif line.startswith("progress=") and "end" in line and on_percent:
                on_percent(100.0)
    except Exception:
        pass

    proc.wait()
    t_err.join(timeout=2)
    return proc.returncode, "".join(stderr_chunks).encode("utf-8", errors="ignore")

def get_video_duration(path):
    """Lấy thời lượng video bằng ffmpeg -i (không cần ffprobe riêng)."""
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    try:
        result = subprocess.run([FFMPEG_EXE, "-i", path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)
        stderr_txt = result.stderr.decode(errors='ignore')
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", stderr_txt)
        if m:
            h, mi, s = m.groups()
            return int(h) * 3600 + int(mi) * 60 + float(s)
    except Exception:
        pass
    return 0.0

def run_ffmpeg_gpu_first(inputs, filter_complex, map_label, output_path, fps, chat_luong, update_status_func=None, index=0, total_duration=0, ten_hien_thi=""):
    """Chạy ffmpeg xuất video, ưu tiên GPU (h264_nvenc), tự rớt về CPU (libx264) nếu GPU lỗi.
    total_duration: thời lượng ước tính (giây) của đoạn đang xuất, dùng để tính % tiến độ."""
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    base_cmd = [FFMPEG_EXE, "-y", "-nostdin"]
    for inp in inputs:
        if isinstance(inp, (tuple, list)):
            base_cmd += list(inp[1]) + ["-i", inp[0]]
        else:
            base_cmd += ["-i", inp]
    filt = ["-filter_complex", filter_complex] if filter_complex else []
    map_args = ["-map", map_label] if map_label else []
    common_tail = ["-an", "-pix_fmt", "yuv420p", "-r", str(fps)]

    def _on_pct_gpu(pct):
        if update_status_func: update_status_func(index, "Đang dựng bằng GPU (NVENC)", "blue-400", pct)

    cmd_nvenc = base_cmd + filt + map_args + common_tail + ["-c:v", "h264_nvenc", "-preset", "p4", "-rc:v", "vbr", "-b:v", chat_luong, output_path]
    if update_status_func: update_status_func(index, "Đang dựng bằng GPU (NVENC)", "blue-400", 0)
    returncode, stderr_bytes = _run_ffmpeg_with_progress(cmd_nvenc, flags, total_duration, _on_pct_gpu)
    if returncode == 0 and os.path.exists(output_path):
        if update_status_func: update_status_func(index, "Đang dựng bằng GPU (NVENC)", "blue-400", 100)
        print(f"✅ [DỰ ÁN {ten_hien_thi}] Dựng xong '{os.path.basename(output_path)}' bằng GPU (NVENC)")
        return

    print(f"⚠️ [GPU LỖI -> {os.path.basename(output_path)}] {stderr_bytes.decode(errors='ignore')[-500:]}\nChuyển sang CPU (libx264).")
    if update_status_func: update_status_func(index, "GPU lỗi, chạy tạm CPU", "orange-400", 0)

    def _on_pct_cpu(pct):
        if update_status_func: update_status_func(index, "Đang dựng bằng CPU (libx264)", "orange-400", pct)

    cmd_x264 = base_cmd + filt + map_args + common_tail + ["-c:v", "libx264", "-preset", "superfast", "-b:v", chat_luong, output_path]
    returncode2, stderr_bytes2 = _run_ffmpeg_with_progress(cmd_x264, flags, total_duration, _on_pct_cpu)
    if returncode2 != 0 or not os.path.exists(output_path):
        raise Exception(f"FFmpeg lỗi khi xuất {os.path.basename(output_path)}")
    if update_status_func: update_status_func(index, "Đang dựng bằng CPU (libx264)", "orange-400", 100)
    print(f"✅ [DỰ ÁN {ten_hien_thi}] Dựng xong '{os.path.basename(output_path)}' bằng CPU (libx264)")

def build_audio_track(song_paths, output_path):
    """Nối nhiều file nhạc (mp3/wav/m4a...) thành 1 track duy nhất bằng ffmpeg concat filter.
    Nhanh hơn nhiều so với MoviePy vì chỉ 1 lần decode+encode cho cả danh sách, thay vì
    mở từng AudioFileClip rồi ghép tuần tự. Xuất ra WAV (pcm) để tránh nén-giải nén 2 lần
    (bước ghép cuối với video sẽ encode AAC 1 lần duy nhất)."""
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    n = len(song_paths)

    if n == 1:
        cmd = [FFMPEG_EXE, "-y", "-nostdin", "-i", song_paths[0],
               "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", output_path]
        result = _run_ffmpeg(cmd, flags)
        if result.returncode != 0 or not os.path.exists(output_path):
            raise Exception("FFmpeg lỗi khi chuẩn hoá audio.")
        return

    base_cmd = [FFMPEG_EXE, "-y", "-nostdin"]
    for p in song_paths:
        base_cmd += ["-i", p]

    filter_lines, labels = [], []
    for i in range(n):
        filter_lines.append(f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo[a{i}]")
        labels.append(f"[a{i}]")
    filter_lines.append(f"{''.join(labels)}concat=n={n}:v=0:a=1[outa]")
    filter_complex = ";".join(filter_lines)

    cmd = base_cmd + ["-filter_complex", filter_complex, "-map", "[outa]", "-c:a", "pcm_s16le", output_path]
    result = _run_ffmpeg(cmd, flags)
    if result.returncode != 0 or not os.path.exists(output_path):
        raise Exception("FFmpeg lỗi khi nối audio.")

def _frame_filter(idx, w, h, in_label, out_label):
    """Phóng khung PNG cho khớp khung hình rồi đè lên video, làm CHUNG 1 lần trong filter_complex
    (không cần thêm lượt render riêng -> không tốn thêm thời gian)."""
    return f"[{idx}:v]scale={w}:{h},format=rgba[frm];[{in_label}][frm]overlay=0:0:shortest=1[{out_label}]"

def build_normalized_clip(input_path, target_size, fps, v_speed, output_path, chat_luong, update_status_func=None, index=0, ten_hien_thi="", file_khung=""):
    """Chuẩn hoá 1 clip đơn lẻ (dùng cho intro/outro): resize + fps + tốc độ, không hiệu ứng."""
    w, h = target_size
    parts = []
    if v_speed != 1.0:
        parts.append(f"setpts={1/v_speed:.6f}*PTS")
    parts.append(f"scale={w}:{h}:force_original_aspect_ratio=disable,setsar=1,fps={fps}")
    inputs = [input_path]
    if file_khung:
        filter_complex = "[0:v]" + ",".join(parts) + "[vn];" + _frame_filter(1, w, h, "vn", "outv")
        inputs.append((file_khung, ["-loop", "1"]))
    else:
        filter_complex = "[0:v]" + ",".join(parts) + "[outv]"
    goc_dur = get_video_duration(input_path)
    total_dur = (goc_dur / v_speed) if v_speed else goc_dur
    run_ffmpeg_gpu_first(inputs, filter_complex, "[outv]", output_path, fps, chat_luong, update_status_func, index, total_dur, ten_hien_thi)

def build_phoi_video(segments, target_size, fps, v_speed, hieu_ung, T, output_path, chat_luong, update_status_func=None, index=0, ten_hien_thi="", file_khung=""):
    """
    Nối nhiều clip lại (segments) kèm hiệu ứng chuyển cảnh, toàn bộ bằng filter native của ffmpeg
    (scale/xfade/fade/concat) thay vì MoviePy -> ram nhẹ hơn hẳn. Bước encode cuối ưu tiên GPU (NVENC).
    segments: list các dict {"path": str, "trim": (start, end) hoặc None}
    """
    w, h = target_size
    inputs = [seg['path'] for seg in segments]
    n = len(segments)
    filter_lines = []
    durations = []

    for i, seg in enumerate(segments):
        parts = []
        if seg.get('trim'):
            s, e = seg['trim']
            parts.append(f"trim=start={s}:end={e},setpts=PTS-STARTPTS")
            base_dur = e - s
        else:
            base_dur = get_video_duration(seg['path'])
        if v_speed != 1.0:
            parts.append(f"setpts={1/v_speed:.6f}*PTS")
        parts.append(f"scale={w}:{h}:force_original_aspect_ratio=disable,setsar=1,fps={fps}")
        durations.append(base_dur / v_speed)
        filter_lines.append(f"[{i}:v]{','.join(parts)}[v{i}]")

    if hieu_ung == 'Mờ êm ái':
        cur_label, cur_dur = "v0", durations[0]
        for i in range(1, n):
            out_label = f"x{i}"
            offset = max(0.0, cur_dur - T)
            filter_lines.append(f"[{cur_label}][v{i}]xfade=transition=fade:duration={T:.3f}:offset={offset:.3f}[{out_label}]")
            cur_dur = cur_dur + durations[i] - T
            cur_label = out_label
        final_label = cur_label
        total_dur_est = cur_dur

    elif hieu_ung in ('Tối thui', 'Chớp sáng'):
        color = "black" if hieu_ung == 'Tối thui' else "white"
        faded_labels = []
        for i in range(n):
            dur_i = durations[i]
            fade_parts = []
            if i == 0:
                fade_parts.append(f"fade=t=out:st={max(0.0, dur_i - T):.3f}:d={T:.3f}:color={color}")
            elif i == n - 1:
                fade_parts.append(f"fade=t=in:st=0:d={T:.3f}:color={color}")
            else:
                fade_parts.append(f"fade=t=in:st=0:d={T:.3f}:color={color}")
                fade_parts.append(f"fade=t=out:st={max(0.0, dur_i - T):.3f}:d={T:.3f}:color={color}")
            filter_lines.append(f"[v{i}]{','.join(fade_parts)}[f{i}]")
            faded_labels.append(f"[f{i}]")
        filter_lines.append(f"{''.join(faded_labels)}concat=n={n}:v=1:a=0[outv]")
        final_label = "outv"
        total_dur_est = sum(durations)

    else:
        raw_labels = "".join([f"[v{i}]" for i in range(n)])
        filter_lines.append(f"{raw_labels}concat=n={n}:v=1:a=0[outv]")
        final_label = "outv"
        total_dur_est = sum(durations)

    # Đè khung PNG ngay trong cùng 1 lượt ffmpeg (sau chuyển cảnh nên khung đứng yên xuyên suốt)
    if file_khung:
        filter_lines.append(_frame_filter(n, w, h, final_label, "outk"))
        inputs.append((file_khung, ["-loop", "1"]))
        final_label = "outk"

    filter_complex = ";".join(filter_lines)
    run_ffmpeg_gpu_first(inputs, filter_complex, f"[{final_label}]", output_path, fps, chat_luong, update_status_func, index, total_dur_est, ten_hien_thi)
    return get_video_duration(output_path)

def _stage_status(base_func, start_pct, end_pct):
    """Bọc update_status_func để chuyển % cục bộ (0-100 của 1 bước ffmpeg) thành % tổng thể
    của cả dự án (nằm trong khoảng start_pct -> end_pct)."""
    def _inner(i, text, color, percent=None):
        if percent is None:
            real_pct = start_pct
        else:
            real_pct = start_pct + (max(0.0, min(100.0, percent)) / 100.0) * (end_pct - start_pct)
        if base_func: base_func(i, text, color, real_pct)
    return _inner

def render_du_an_cach_ly(ten_file_xuat, ds_video, ds_nhac_hay, ds_nhac_thuong, ds_nhac_suno, file_intro, file_outro, target_seconds, output_dir, hieu_ung, tg_hieu_ung, v_speed, che_do_nhac, chat_luong, update_status_func=None, index=0, file_khung="", che_do_video="gop"):
    project_temp = None
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        safe_name = "".join([c for c in ten_file_xuat if c.isalpha() or c.isdigit() or c==' ' or c=='_']).rstrip()
        if not safe_name: safe_name = f"Video_Render_{index}"

        print(f"🚀 [DỰ ÁN {safe_name}] Bắt đầu xử lý (luồng #{index+1})...")

        project_temp = os.path.join(TEMP_DIR, f"temp_{safe_name}_{index}")
        os.makedirs(project_temp, exist_ok=True)

        F_PHOI      = os.path.join(project_temp, "phoi.mp4")
        F_INTRO_TAM = os.path.join(project_temp, "intro.mp4")
        F_OUTRO_TAM = os.path.join(project_temp, "outro.mp4")
        F_NHAC_TAM  = os.path.join(project_temp, "audio.wav")
        F_LOOP      = os.path.join(project_temp, "loop.txt")

        if update_status_func: update_status_func(index, "Đang ghép Audio", "blue-400", 0)

        if not ds_video or (not ds_nhac_hay and not ds_nhac_thuong and not ds_nhac_suno):
            raise Exception("Thiếu Video Nền hoặc Nhạc!")

        # -------------- XỬ LÝ ÂM THANH --------------
        ds_audio_chon = []
        tong_thoi_gian_nhac = 0
        ds_nhac_hay_goc = ds_nhac_hay.copy() if ds_nhac_hay else []
        ds_nhac_thuong_goc = ds_nhac_thuong.copy() if ds_nhac_thuong else []
        ds_nhac_suno_goc = ds_nhac_suno.copy() if ds_nhac_suno else []
        loi_nhac = []

        if ds_nhac_hay_goc: random.shuffle(ds_nhac_hay_goc)
        if ds_nhac_thuong_goc: random.shuffle(ds_nhac_thuong_goc)
        danh_sach_tong = ds_nhac_hay_goc + ds_nhac_thuong_goc

        def try_add_audio(song_path):
            nonlocal tong_thoi_gian_nhac
            if not os.path.exists(song_path):
                return False
            dur = get_video_duration(song_path)
            if dur <= 0:
                return False
            ds_audio_chon.append(song_path)
            tong_thoi_gian_nhac += dur
            return True

        if target_seconds > 0:
            if 'Không lặp' in che_do_nhac:
                # 1. Chạy hết nhạc Hay và nhạc Thường
                for song_path in danh_sach_tong:
                    if not try_add_audio(song_path): loi_nhac.append(os.path.basename(song_path))
                    if tong_thoi_gian_nhac >= target_seconds: break

                # 2. Nếu vẫn thiếu thời lượng, đắp bù bằng Nhạc Suno
                if tong_thoi_gian_nhac < target_seconds and ds_nhac_suno_goc:
                    random.shuffle(ds_nhac_suno_goc)
                    for song_path in ds_nhac_suno_goc:
                        if not try_add_audio(song_path): loi_nhac.append(os.path.basename(song_path))
                        if tong_thoi_gian_nhac >= target_seconds: break
            else:
                # Chế độ Lặp Vô Tận (Chỉ lặp Nhạc Hay + Nhạc Thường)
                while tong_thoi_gian_nhac < target_seconds:
                    added_any = False
                    for song_path in danh_sach_tong:
                        if try_add_audio(song_path):
                            added_any = True
                            if tong_thoi_gian_nhac >= target_seconds: break
                        else:
                            if not ds_audio_chon and not added_any:
                                loi_nhac.append(os.path.basename(song_path))
                    if not added_any: break
        else:
            for song_path in danh_sach_tong:
                if not try_add_audio(song_path): loi_nhac.append(os.path.basename(song_path))

        if loi_nhac:
            msg = f"{loi_nhac[0]}" if len(loi_nhac) == 1 else f"{loi_nhac[0]} và {len(loi_nhac) - 1} bài khác"
            print(f"⚠️ [DỰ ÁN {safe_name}] Bỏ qua {len(loi_nhac)} bài nhạc hỏng: {msg}")

        if not ds_audio_chon:
            raise Exception("Lỗi Nhạc: Tất cả file MP3 đều bị hỏng hoặc trống!")

        so_bai_nhac = len(ds_audio_chon)
        build_audio_track(ds_audio_chon, F_NHAC_TAM)
        print(f"🎵 [DỰ ÁN {safe_name}] Đã ghép xong {so_bai_nhac} bài nhạc, tổng {tong_thoi_gian_nhac:.1f}s")
        ds_audio_chon.clear()
        gc.collect()

        if update_status_func: update_status_func(index, "Đang đúc Video", "indigo-400", 5)

        try:
            c_goc = VideoFileClip(ds_video[0], audio=False)
            w_goc, h_goc = c_goc.size
            w = w_goc if w_goc % 2 == 0 else w_goc - 1
            h = h_goc if h_goc % 2 == 0 else h_goc - 1
            target_size = (w, h)
            chung_fps = int(c_goc.fps or 30)
            if chung_fps > 60: chung_fps = 30
            c_goc.close()
        except Exception:
            raise Exception(f"Video nền đầu tiên bị hỏng: {os.path.basename(ds_video[0])}")

        # -------------- XỬ LÝ RAW CLIP (BẰNG FFMPEG NATIVE, ÍT RAM, ƯU TIÊN GPU KHI XUẤT) --------------
        ds_video_hop_le = []
        loi_video = []
        for v_path in ds_video:
            if os.path.exists(v_path):
                ds_video_hop_le.append(v_path)
            else:
                loi_video.append(os.path.basename(v_path))

        if loi_video:
            msg = f"{loi_video[0]}" if len(loi_video) == 1 else f"{loi_video[0]} và {len(loi_video) - 1} video khác"
            print(f"⚠️ [DỰ ÁN {safe_name}] Bỏ qua {len(loi_video)} Video hỏng: {msg}")

        if not ds_video_hop_le:
            raise Exception("Lỗi đọc File! Tất cả Phôi Video đều hỏng.")

        # -------------- THUẬT TOÁN NỐI (giữ nguyên: chỉ 1 clip thì tách nửa sau + nửa đầu) --------------
        if len(ds_video_hop_le) == 1:
            v0 = ds_video_hop_le[0]
            full_dur = get_video_duration(v0)
            mid_point = full_dur / 2.0
            segments = [
                {"path": v0, "trim": (mid_point, full_dur)},
                {"path": v0, "trim": (0, mid_point)},
            ]
        else:
            segments = [{"path": v, "trim": None} for v in ds_video_hop_le]

        file_khung_ok = ""
        if file_khung:
            if os.path.exists(file_khung):
                file_khung_ok = file_khung
                print(f"🖼️ [DỰ ÁN {safe_name}] Dùng khung PNG (chỉ video nền, không đè Intro/Outro): {os.path.basename(file_khung)}")
            else:
                print(f"⚠️ [DỰ ÁN {safe_name}] Không tìm thấy file khung PNG, bỏ qua.")

        T = tg_hieu_ung
        seg_durs_est = []
        for seg in segments:
            if seg["trim"]:
                seg_durs_est.append((seg["trim"][1] - seg["trim"][0]) / v_speed)
            else:
                seg_durs_est.append(get_video_duration(seg["path"]) / v_speed)
        min_dur = min(seg_durs_est) if seg_durs_est else 1.0
        if T >= (min_dur / 2.0):
            T = max(0.1, min_dur / 2.5)

        # -------------- NỐI CLIP + ÁP DỤNG HIỆU ỨNG CHUYỂN CẢNH (ffmpeg filter, GPU khi xuất) --------------
        if che_do_video == 'xuyen_suot':
            print(f"🎬 [DỰ ÁN {safe_name}] Chế độ 1 video chạy xuyên suốt (lặp liền mạch, không chuyển cảnh)...")
        else:
            print(f"🎬 [DỰ ÁN {safe_name}] Gộp {len(segments)} đoạn thành 1 video nền (hiệu ứng: {hieu_ung})...")
        stage_video = _stage_status(update_status_func, 5, 65)
        if che_do_video == 'xuyen_suot':
            # Chỉ chuẩn hoá đúng 1 lần clip gốc (kèm khung/tốc độ), sau đó lặp bằng concat copy -> rất nhanh
            build_normalized_clip(ds_video_hop_le[0], target_size, chung_fps, v_speed, F_PHOI, chat_luong, stage_video, index, safe_name, file_khung_ok)
            phoi_dur = get_video_duration(F_PHOI)
        else:
            phoi_dur = build_phoi_video(segments, target_size, chung_fps, v_speed, hieu_ung, T, F_PHOI, chat_luong, stage_video, index, safe_name, file_khung_ok)
        print(f"✅ [DỰ ÁN {safe_name}] Dựng xong video nền, thời lượng {phoi_dur:.1f}s")
        gc.collect()

        thoi_gian_intro_seq, thoi_gian_outro_seq = 0, 0
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

        if file_intro:
            try:
                print(f"🎞️ [DỰ ÁN {safe_name}] Đang ghép Intro...")
                stage_intro = _stage_status(update_status_func, 65, 75)
                build_normalized_clip(file_intro, target_size, chung_fps, 1.0, F_INTRO_TAM, chat_luong, stage_intro, index, safe_name)
                thoi_gian_intro_seq = get_video_duration(F_INTRO_TAM)
            except Exception:
                print(f"❌ [LỖI INTRO] Hỏng file: {os.path.basename(file_intro)}. Bỏ qua ghép Intro.")
        if update_status_func: update_status_func(index, "Đóng gói Final", "orange-400", 75)

        if file_outro:
            try:
                print(f"🎞️ [DỰ ÁN {safe_name}] Đang ghép Outro...")
                stage_outro = _stage_status(update_status_func, 75, 85)
                build_normalized_clip(file_outro, target_size, chung_fps, 1.0, F_OUTRO_TAM, chat_luong, stage_outro, index, safe_name)
                thoi_gian_outro_seq = get_video_duration(F_OUTRO_TAM)
            except Exception:
                print(f"❌ [LỖI OUTRO] Hỏng file: {os.path.basename(file_outro)}. Bỏ qua ghép Outro.")
        if update_status_func: update_status_func(index, "Đóng gói Final", "orange-400", 85)

        target_loop_section = tong_thoi_gian_nhac - thoi_gian_intro_seq - thoi_gian_outro_seq
        if target_loop_section < 0: target_loop_section = phoi_dur
        mid_loops = math.ceil(target_loop_section / phoi_dur) if phoi_dur > 0 else 1

        with open(F_LOOP, "w", encoding="utf-8") as f:
            if file_intro and os.path.exists(F_INTRO_TAM): f.write(f"file '{os.path.abspath(F_INTRO_TAM).replace(chr(92), '/')}'\n")
            for _ in range(mid_loops): f.write(f"file '{os.path.abspath(F_PHOI).replace(chr(92), '/')}'\n")
            if file_outro and os.path.exists(F_OUTRO_TAM): f.write(f"file '{os.path.abspath(F_OUTRO_TAM).replace(chr(92), '/')}'\n")

        output_path = os.path.join(output_dir, f"{safe_name}.mp4")

        cmd_final = [FFMPEG_EXE, "-y", "-nostdin", "-f", "concat", "-safe", "0", "-i", F_LOOP, "-i", F_NHAC_TAM]
        # Không cắt cứng theo target_seconds -> nhạc phát trọn vẹn hết bài, không đứt giữa chừng.
        # Video loop ở trên đã được dựng đủ dài để phủ hết tong_thoi_gian_nhac, nên "-shortest"
        # sẽ tự dừng đúng khi nhạc kết thúc, không cần ép "-t".
        cmd_final.extend(["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", output_path])

        print(f"📦 [DỰ ÁN {safe_name}] Đang đóng gói file cuối cùng...")
        du_kien_tong_dur = max(tong_thoi_gian_nhac, phoi_dur)
        stage_final = _stage_status(update_status_func, 85, 99)
        def _on_pct_final(pct):
            stage_final(index, "Đóng gói Final", "orange-400", pct)
        returncode_final, stderr_final = _run_ffmpeg_with_progress(cmd_final, flags, du_kien_tong_dur, _on_pct_final)

        if returncode_final != 0:
            print(f"🚨 [LỖI GHÉP CUỐI] {stderr_final.decode(errors='ignore')[-500:]}")
            raise Exception("Lỗi ghép Video ngầm FFmpeg.")

        if not os.path.exists(output_path):
            raise Exception("FFmpeg không tạo ra file Output!")

        if update_status_func: update_status_func(index, "Hoàn thành", "emerald-500", 100)
        print(f"🎉 [DỰ ÁN {safe_name}] HOÀN THÀNH -> {output_path}")
        return True

    except Exception as e:
        tb_text = traceback.format_exc()
        print(f"🚨 [LỖI DỰ ÁN {safe_name if 'safe_name' in locals() else index}]\n{tb_text}")
        err_msg = str(e)
        if len(err_msg) > 40: err_msg = err_msg[:37] + "..."
        if update_status_func: update_status_func(index, f"❌ {err_msg}", "red-500", 0)
        return False
    finally:
        try:
            if project_temp: shutil.rmtree(project_temp)
        except: pass


LAST_DIALOG_ERROR = ""

def get_file_safe_isolated(title, ext_list, multiple=True, is_dir=False):
    global LAST_DIALOG_ERROR
    LAST_DIALOG_ERROR = ""
    ext_clean = ext_list.replace(" ", ";")

    fd_out, temp_out = tempfile.mkstemp(suffix=".txt")
    os.close(fd_out)

    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        exe_path = sys.executable

        # CHỈ đổi sang pythonw.exe khi đang chạy ở dạng script .py/.pyw
        # thông thường (chưa đóng gói). Khi đã build .exe (sys.frozen),
        # exe_path CHÍNH LÀ file .exe của app -> gọi lại chính nó với cờ
        # --pick-dialog để nó tự nhận diện và chỉ mở hộp thoại, không mở
        # lại toàn bộ giao diện NiceGUI (tránh treo do tranh cổng 8080).
        if not getattr(sys, 'frozen', False) and os.name == 'nt' and exe_path.lower().endswith("python.exe"):
            pythonw_path = exe_path[:-10] + "pythonw.exe"
            if os.path.exists(pythonw_path): exe_path = pythonw_path

        # Chạy dạng script (.py/.pyw) thì BẮT BUỘC phải truyền đường dẫn file script,
        # nếu không Python báo "unknown option --pick-dialog" và hộp thoại không bao giờ hiện.
        # Dạng .exe đóng gói thì exe_path chính là app nên không cần.
        if getattr(sys, 'frozen', False):
            args = [exe_path]
        else:
            args = [exe_path, os.path.abspath(__file__)]
        args += ["--pick-dialog", temp_out, "1" if is_dir else "0", "1" if multiple else "0", title, ext_clean]
        proc = subprocess.run(args, creationflags=flags, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if proc.returncode != 0:
            LAST_DIALOG_ERROR = ((proc.stderr or "").strip().splitlines() or [f"mã thoát {proc.returncode}"])[-1][:200]

        with open(temp_out, 'r', encoding='utf-8') as f: out = f.read().strip()
        if not out: return [] if multiple else ""
        if is_dir: return out
        return out.split("|||") if multiple else out
    except Exception as e:
        LAST_DIALOG_ERROR = str(e)[:200]
        return [] if multiple else ""
    finally:
        try: os.remove(temp_out)
        except: pass

# =========================================================================
# GIAO DIỆN V8.0 (OCEAN SLATE + SUNO AI FILLER 🤖)
# =========================================================================
AUDIO_EXT = ('.mp3', '.wav', '.m4a', '.flac', '.aac', '.ogg', '.wma', '.opus')

def quet_nhac_trong_thu_muc(folder):
    """Quét file nhạc trong thư mục VÀ toàn bộ thư mục con (trước đây chỉ quét tầng ngoài cùng)."""
    files = []
    for root_dir, _, names in os.walk(folder):
        for n in sorted(names):
            if n.lower().endswith(AUDIO_EXT) and not n.startswith('.'):
                files.append(os.path.join(root_dir, n))
    return files

STATE_KEY = {'video': 'ds_video', 'nhac_hay': 'ds_nhac_hay', 'nhac_thuong': 'ds_nhac_thuong', 'nhac_suno': 'ds_nhac_suno',
             'intro': 'file_intro', 'outro': 'file_outro', 'khung': 'file_khung', 'video_don': 'video_don', 'video_auto': 'ds_video'}
app_state = {
    'ds_video': [], 'ds_nhac_hay': [], 'ds_nhac_thuong': [], 'ds_nhac_suno': [], 'file_intro': "", 'file_outro': "", 'file_khung': "", 'video_don': "",
    'output_dir': os.path.abspath(os.path.join(WORKSPACE_DIR, "Output")),
    'hang_doi': [], 'is_rendering': False
}
os.makedirs(app_state['output_dir'], exist_ok=True)

log_console = None
log_queue = queue.Queue()  # luồng render (worker thread) chỉ bỏ tin nhắn vào đây, KHÔNG đụng trực tiếp vào log_console
_original_print = builtins.print
def gui_print(*args, **kwargs):
    msg = " ".join(map(str, args))
    _original_print(*args, **kwargs)
    try:
        log_queue.put_nowait(msg)
    except Exception:
        pass
builtins.print = gui_print

def _drain_log_queue():
    """Chạy trên luồng UI chính (qua ui.timer) để đẩy tin nhắn từ hàng đợi vào log_console an toàn."""
    if log_console is None:
        return
    try:
        while True:
            msg = log_queue.get_nowait()
            log_console.push(msg)
    except queue.Empty:
        pass

# ===== BẮT ĐẦU: HỆ THỐNG CẬP NHẬT =====
import time, json, hashlib, asyncio, webbrowser
import urllib.request
from urllib.parse import urljoin

APP_VERSION = "8.0.0"
# Link tới file version.json trên mạng (xem hướng dẫn: GitHub raw / hosting bất kỳ, phải là HTTPS)
UPDATE_URL = "https://raw.githubusercontent.com/TEN_GITHUB/TEN_REPO/main/version.json"
LAUNCHER_VERSION = int(os.environ.get('RSP_LAUNCHER_VERSION', '999'))   # 999 = chạy từ mã nguồn
SCRIPT_PATH = os.environ.get('RSP_APP_SCRIPT') or os.path.abspath(__file__)  # file sẽ bị thay khi cập nhật

def _ver_tuple(v):
    out = []
    for part in str(v).strip().lstrip('vV').split('.'):
        m = re.match(r'\d+', part)
        out.append(int(m.group()) if m else 0)
    return tuple(out)

def _sha_chuan(data):
    # chuẩn hoá xuống dòng để Git/Windows đổi CRLF<->LF cũng không làm sai mã kiểm tra
    return hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()

def _http_get(url, timeout=20, max_bytes=8 * 1024 * 1024):
    req = urllib.request.Request(url, headers={'User-Agent': 'RenderStudioPro-Updater'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise RuntimeError('File cập nhật quá lớn, đã huỷ để an toàn.')
    return data

def kiem_tra_cap_nhat():
    """Đọc version.json trên mạng. Trả về dict (có khoá _co_ban_moi). Lỗi thì raise."""
    if 'TEN_GITHUB' in UPDATE_URL:
        raise RuntimeError('Chưa cấu hình link cập nhật (UPDATE_URL) trong phần mềm.')
    sep = '&' if '?' in UPDATE_URL else '?'
    try:
        data = _http_get(f"{UPDATE_URL}{sep}t={int(time.time())}", 15, 256 * 1024)
    except Exception as e:
        raise RuntimeError(f'Không kết nối được máy chủ cập nhật (kiểm tra Internet). Chi tiết: {e}')
    m = json.loads(data.decode('utf-8-sig'))
    m['_co_ban_moi'] = _ver_tuple(m.get('version', '0')) > _ver_tuple(APP_VERSION)
    return m

def ap_dung_cap_nhat(m):
    """Tải mã mới -> kiểm tra toàn vẹn + cú pháp -> thay file an toàn (có bản sao lưu .bak)."""
    url, sha = m.get('url'), (m.get('sha256') or '').lower()
    if not url or not sha:
        raise RuntimeError('version.json thiếu "url" hoặc "sha256".')
    data = _http_get(urljoin(UPDATE_URL, url), 60)
    if _sha_chuan(data) != sha:
        raise RuntimeError('File tải về không khớp mã kiểm tra (sha256) - có thể tải lỗi hoặc chưa upload xong. Thử lại sau.')
    text = data.decode('utf-8')
    compile(text, 'renvideo.pyw', 'exec')   # lỗi cú pháp -> raise, KHÔNG ghi đè bản đang chạy
    if f'APP_VERSION = "{m.get("version")}"' not in text:
        raise RuntimeError('Số phiên bản trong file không khớp version.json.')
    target = SCRIPT_PATH
    os.makedirs(os.path.dirname(target) or '.', exist_ok=True)
    if os.path.exists(target):
        shutil.copy2(target, target + '.bak')
    tmp = target + '.new'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, target)
    return target

def khoi_dong_lai_app():
    """Mở bản mới sau vài giây (đợi bản cũ nhả cổng 8080) rồi tắt bản đang chạy."""
    exe = sys.executable
    if getattr(sys, 'frozen', False):
        cmd = f'ping -n 4 127.0.0.1 >nul & start "" "{exe}"'
    else:
        cmd = f'ping -n 4 127.0.0.1 >nul & start "" "{exe}" "{SCRIPT_PATH}"'
    if os.name == 'nt':
        subprocess.Popen(cmd, shell=True, close_fds=True, creationflags=0x08000000 | 0x00000008,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen([exe, SCRIPT_PATH] if not getattr(sys, 'frozen', False) else [exe])
    try:
        from nicegui import app as _ng_app
        _ng_app.shutdown()
    except Exception:
        pass
    threading.Timer(6, lambda: os._exit(0)).start()
# ===== KẾT THÚC: HỆ THỐNG CẬP NHẬT =====

def tat_phan_mem():
    ui.notify('Đang tắt hệ thống...', type='info', position='top')
    os._exit(0)

@ui.page('/')
def main_page():
    global log_console
    ui.colors(primary='#3b82f6', secondary='#6366f1', accent='#f43f5e', dark='#0f172a', positive='#10b981', negative='#ef4444')
    
    ui.add_head_html('''
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        
        body { 
            background-color: #0f172a; 
            font-family: "Inter", sans-serif; 
            color: #f8fafc;
            overflow-x: hidden;
        }

        .text-glow {
            color: #60a5fa; 
            font-weight: 800;
            text-shadow: 0 0 15px rgba(96, 165, 250, 0.4);
            letter-spacing: 2px;
        }

        .marquee-container {
            width: 100%;
            overflow: hidden;
            background: #1e293b; 
            border-bottom: 1px solid #334155;
            padding: 8px 0;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }
        .marquee-content {
            white-space: nowrap;
            animation: marquee 25s linear infinite;
            color: #38bdf8; 
            font-weight: 600;
            font-size: 14px;
            letter-spacing: 1px;
        }
        @keyframes marquee { 0% { transform: translateX(100%); } 100% { transform: translateX(-100%); } }

        .pro-card {
            background-color: #1e293b; 
            border: 1px solid #334155;
            border-radius: 16px;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2);
            transition: border-color 0.3s ease;
        }
        .pro-card:hover { border-color: #475569; }
        
        .list-row {
            background-color: #0f172a; 
            border: 1px solid #334155;
            border-radius: 10px;
            transition: all 0.2s ease;
        }
        .list-row:hover {
            border-color: #60a5fa;
            background-color: #1e293b;
        }

        .btn-main {
            background: linear-gradient(135deg, #3b82f6, #6366f1) !important;
            border: none !important;
            color: white !important;
            font-weight: 700 !important;
            box-shadow: 0 4px 10px rgba(59, 130, 246, 0.3) !important;
            transition: all 0.3s ease !important;
        }
        .btn-main:hover {
            box-shadow: 0 6px 15px rgba(59, 130, 246, 0.5) !important;
            transform: translateY(-2px);
        }
        .btn-main:disabled {
            background: #334155 !important;
            color: #94a3b8 !important;
            box-shadow: none !important;
            transform: none !important;
        }

        .custom-scrollbar::-webkit-scrollbar { width: 8px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #475569; border-radius: 4px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #60a5fa; }
        
        .q-field__control { background: #0f172a !important; border-radius: 8px !important; }
        .q-field__native { color: #f8fafc !important; font-family: "Inter", sans-serif; font-size: 14px; font-weight: 600;}
        .q-field--outlined .q-field__control:before { border: 1px solid #334155 !important; }
        .q-field--outlined .q-field__control:after { border: 1px solid #3b82f6 !important; }
        
        .q-menu { background: #1e293b !important; border: 1px solid #334155 !important; border-radius: 8px; box-shadow: 0 10px 25px rgba(0,0,0,0.5) !important; padding: 4px;}
        .q-item { color: #cbd5e1 !important; border-radius: 6px; margin: 2px; font-weight: 500;}
        .q-item:hover, .q-item.q-manual-focusable--focused { background: #3b82f6 !important; color: #ffffff !important; }
        </style>
    ''')

    # ---------- CẬP NHẬT PHẦN MỀM ----------
    up_state = {'m': None, 'full': False}
    with ui.dialog() as dlg_up, ui.card().classes('pro-card p-6 min-w-[460px] max-w-[580px]'):
        ui.label('CẬP NHẬT PHẦN MỀM').classes('text-xs font-bold text-blue-400 tracking-widest uppercase mb-2')
        lbl_up_title = ui.label('').classes('text-base font-bold text-white')
        lbl_up_notes = ui.label('').classes('text-[13px] text-slate-300 whitespace-pre-line mb-2')
        up_progress = ui.linear_progress(show_value=False).props('indeterminate').classes('w-full')
        up_progress.set_visibility(False)
        with ui.row().classes('w-full justify-end gap-2 mt-2'):
            btn_up_close = ui.button('Đóng', on_click=dlg_up.close).props('flat no-caps')
            btn_up_go = ui.button('Cập nhật ngay', icon='system_update', on_click=lambda: thuc_hien_cap_nhat()).props('unelevated no-caps').classes('btn-main')
            btn_up_go.set_visibility(False)

    def _hien_dialog(tieu_de, noi_dung='', co_nut=False):
        lbl_up_title.text = tieu_de; lbl_up_notes.text = noi_dung
        up_progress.set_visibility(False); btn_up_go.set_visibility(co_nut)
        dlg_up.open()

    async def kiem_tra_cap_nhat_ui(chu_dong=True):
        btn_update.disable()
        try:
            m = await run.io_bound(kiem_tra_cap_nhat)
        except Exception as e:
            if chu_dong: _hien_dialog('Không kiểm tra được cập nhật', str(e))
            return
        finally:
            btn_update.enable()
        up_state['m'] = m
        if not m.get('_co_ban_moi'):
            if chu_dong: _hien_dialog(f'Bạn đang dùng bản mới nhất (V{APP_VERSION})')
            return
        btn_update.text = f"Cập nhật V{m.get('version')}"; btn_update.props('color=accent')
        ghi_chu = m.get('notes', '')
        if int(m.get('min_launcher', 0) or 0) > LAUNCHER_VERSION:
            up_state['full'] = True; btn_up_go.text = 'Mở trang tải'
            tieu_de = f"Có bản mới V{m.get('version')} - cần tải bộ cài đầy đủ"
            ghi_chu += "\n\n(Bản này thay đổi thành phần lõi nên không cập nhật nhanh được.)"
        else:
            up_state['full'] = False; btn_up_go.text = 'Cập nhật ngay'
            tieu_de = f"Có bản mới V{m.get('version')} (đang dùng V{APP_VERSION})"
        if chu_dong:
            _hien_dialog(tieu_de, ghi_chu, True)
        else:
            ui.notify(f"Có bản cập nhật mới V{m.get('version')} - bấm nút Cập nhật ở góc trên.", type='info', position='top', timeout=8000)

    async def thuc_hien_cap_nhat():
        m = up_state.get('m')
        if not m: return
        if up_state.get('full'):
            if m.get('full_url'): webbrowser.open(m['full_url'])
            return
        if app_state.get('is_rendering', False):
            ui.notify('Đang render - hãy đợi xong rồi cập nhật.', type='warning', position='top'); return
        btn_up_go.disable(); btn_up_close.disable()
        lbl_up_title.text = f"Đang tải V{m.get('version')}..."; up_progress.set_visibility(True)
        try:
            await run.io_bound(ap_dung_cap_nhat, m)
        except Exception as e:
            up_progress.set_visibility(False)
            lbl_up_title.text = 'Cập nhật thất bại (bản hiện tại vẫn giữ nguyên, dùng bình thường)'
            lbl_up_notes.text = str(e)
            btn_up_go.enable(); btn_up_close.enable()
            return
        lbl_up_title.text = 'Cập nhật xong! Đang khởi động lại...'
        await asyncio.sleep(1.5)
        khoi_dong_lai_app()

    with ui.row().classes('w-full h-16 bg-[#1e293b] border-b border-[#334155] items-center justify-between px-8 sticky top-0 z-50'):
        with ui.row().classes('items-center gap-3'):
            ui.icon('rocket_launch', size='sm', color='blue-400')
            ui.label('RENDER STUDIO PRO').classes('text-lg text-glow')
        with ui.row().classes('items-center gap-4'):
            ui.label(f'V{APP_VERSION} (SUNO AI FILLER 🤖)').classes('text-[11px] font-bold tracking-widest px-3 py-1 bg-[#0f172a] text-blue-400 border border-blue-500/30 rounded')
            btn_update = ui.button('Cập nhật', icon='system_update', on_click=lambda: kiem_tra_cap_nhat_ui(True)).props('unelevated dense no-caps size=sm color=primary').classes('px-3')
            ui.button(icon='close', on_click=tat_phan_mem).props('flat round size="sm"').classes('text-slate-400 hover:bg-red-500/20 hover:text-red-400')

    ui.add_body_html('''
        <div class="marquee-container">
            <div class="marquee-content">
                ✨ RENDER STUDIO PRO V8.0 ✨ ĐÃ THÊM KHO "NHẠC SUNO" DỰ PHÒNG TỰ ĐỘNG ĐẮP BÙ CHO CHẾ ĐỘ "KHÔNG LẶP" ĐỂ ĐẢM BẢO THỜI LƯỢNG ✨ CẬP NHẬT MỚI: TỰ ĐỘNG PHÁT HẾT "NHẠC HAY" RỒI MỚI ĐẾN "NHẠC THƯỜNG" ✨ CHÚC SẾP LÊN XU HƯỚNG TRIỆU VIEW! 🚀
            </div>
        </div>
    ''')

    with ui.row().classes('w-full max-w-[1350px] mx-auto mt-6 px-4 gap-6 items-stretch flex-nowrap'):
        
        with ui.column().classes('w-[48%] min-w-[500px] gap-6'): 
            
            with ui.card().classes('w-full p-6 pro-card flex-col'):
                ui.label('1. KHO TÀI NGUYÊN').classes('text-xs font-bold text-blue-400 mb-4 tracking-widest uppercase')
                
                with ui.row().classes('w-full gap-3 mb-5'):
                    input_ten = ui.input('Tên Video', value='video1').classes('flex-grow w-2/3').props('dark outlined dense')
                    lbl_out = ui.input('Thư mục lưu', value=app_state['output_dir']).classes('flex-grow w-1/3').props('dark outlined dense readonly')
                    async def pick_out_dir():
                        res = await run.io_bound(get_file_safe_isolated, "Chọn thư mục lưu", "", False, True)
                        if res: app_state['output_dir'] = res; lbl_out.value = res
                        elif LAST_DIALOG_ERROR: ui.notify(f'Không mở được hộp thoại chọn thư mục: {LAST_DIALOG_ERROR}', type='negative', position='top', timeout=8000)
                    ui.button(icon='folder_open', on_click=pick_out_dir).props('outline color="primary"').classes('h-[40px] w-[40px] border-[#334155] hover:border-blue-400')

                row_refs = {}
                def _reset_row(key):
                    if key in row_refs:
                        ls, ic = row_refs[key]
                        ls.text = "Chưa có dữ liệu"; ic.classes(replace='text-slate-500')

                async def pick_file(loai, btn, lbl, icon_el):
                    btn.disable()
                    try:
                        if loai == 'video_auto':
                            loai = 'video_don' if tg_video.value == 'don' else 'video'
                        if loai == 'video':
                            res = await run.io_bound(get_file_safe_isolated, "Chọn Video Nền", "*.mp4 *.mov")
                            if res:
                                app_state['ds_video'] = list(res); app_state['video_don'] = ""; _reset_row('video_don')
                                lbl.text = f"Đã nạp {len(res)} video (gộp thành 1)"; icon_el.classes(replace='text-blue-400')
                        elif loai == 'video_don':
                            res = await run.io_bound(get_file_safe_isolated, "Chọn 1 Video chạy xuyên suốt", "*.mp4 *.mov", False)
                            if res:
                                app_state['video_don'] = res; app_state['ds_video'] = []; _reset_row('video')
                                lbl.text = f"Xuyên suốt: {os.path.basename(res)}"; icon_el.classes(replace='text-blue-400')
                        elif loai == 'nhac_hay':
                            res = await run.io_bound(get_file_safe_isolated, "Chọn Thư Mục Nhạc Ưu Tiên", "", False, True)
                            if res: 
                                files = quet_nhac_trong_thu_muc(res)
                                if files: app_state['ds_nhac_hay'] = files; lbl.text = f"Đã nạp {len(files)} bài • {os.path.basename(res) or res}"; icon_el.classes(replace='text-amber-400')
                                else: ui.notify(f'Không thấy file nhạc nào trong "{res}" (đã quét cả thư mục con). Hỗ trợ: mp3, wav, m4a, flac, aac, ogg, wma, opus.', type='warning', position='top', timeout=6000)
                        elif loai == 'nhac_thuong':
                            res = await run.io_bound(get_file_safe_isolated, "Chọn Thư Mục Nhạc Phụ", "", False, True)
                            if res: 
                                files = quet_nhac_trong_thu_muc(res)
                                if files: app_state['ds_nhac_thuong'] = files; lbl.text = f"Đã nạp {len(files)} bài • {os.path.basename(res) or res}"; icon_el.classes(replace='text-emerald-400')
                                else: ui.notify(f'Không thấy file nhạc nào trong "{res}" (đã quét cả thư mục con). Hỗ trợ: mp3, wav, m4a, flac, aac, ogg, wma, opus.', type='warning', position='top', timeout=6000)
                        elif loai == 'nhac_suno':
                            res = await run.io_bound(get_file_safe_isolated, "Chọn Thư Mục Nhạc Suno", "", False, True)
                            if res: 
                                files = quet_nhac_trong_thu_muc(res)
                                if files: app_state['ds_nhac_suno'] = files; lbl.text = f"Đã nạp {len(files)} bài • {os.path.basename(res) or res}"; icon_el.classes(replace='text-pink-400')
                                else: ui.notify(f'Không thấy file nhạc nào trong "{res}" (đã quét cả thư mục con). Hỗ trợ: mp3, wav, m4a, flac, aac, ogg, wma, opus.', type='warning', position='top', timeout=6000)
                        elif loai == 'intro':
                            res = await run.io_bound(get_file_safe_isolated, "Chọn Video Intro", "*.mp4 *.mov", False)
                            if res: app_state['file_intro'] = res; lbl.text = "Đã nạp Intro"; icon_el.classes(replace='text-purple-400')
                        elif loai == 'outro':
                            res = await run.io_bound(get_file_safe_isolated, "Chọn Video Outro", "*.mp4 *.mov", False)
                            if res: app_state['file_outro'] = res; lbl.text = "Đã nạp Outro"; icon_el.classes(replace='text-purple-400')
                        elif loai == 'khung':
                            res = await run.io_bound(get_file_safe_isolated, "Chọn Khung PNG", "*.png", False)
                            if res: app_state['file_khung'] = res; lbl.text = f"Đã nạp: {os.path.basename(res)}"; icon_el.classes(replace='text-cyan-400')
                    finally:
                        btn.enable()
                        if LAST_DIALOG_ERROR:
                            ui.notify(f'Không mở được hộp thoại chọn file: {LAST_DIALOG_ERROR}', type='negative', position='top', timeout=8000)

                def media_row(title, type_key, icon_name, is_folder=False):
                    with ui.row().classes('w-full items-center justify-between p-3 mb-2 list-row'):
                        with ui.row().classes('items-center gap-3 w-[70%] overflow-hidden'):
                            ic = ui.icon(icon_name, size='sm').classes('text-slate-500 transition-colors')
                            with ui.column().classes('gap-0'):
                                ui.label(title).classes('font-semibold text-[13px] text-slate-100')
                                lbl_status = ui.label('Chưa có dữ liệu').classes('text-[12px] text-slate-400 truncate')
                        with ui.row().classes('gap-2'):
                            btn_chon = ui.button(icon='add').props('flat round color="primary" size="sm"').classes('bg-[#1e293b] border border-[#334155] hover:border-blue-400 hover:bg-blue-500/10')
                            btn_chon.on_click(lambda tk=type_key, bc=btn_chon, ls=lbl_status, i=ic: pick_file(tk, bc, ls, i))
                            def xoa_file(tk=type_key, ls=lbl_status, i=ic):
                                key = STATE_KEY.get(tk, tk)
                                if tk == 'video_auto': app_state['video_don'] = ""
                                app_state[key] = [] if key in ['ds_video', 'ds_nhac_hay', 'ds_nhac_thuong', 'ds_nhac_suno'] else ""; ls.text = "Chưa có dữ liệu"; i.classes(replace='text-slate-500')
                            ui.button(icon='close').props('flat round color="slate-500" size="sm"').classes('hover:bg-red-500/20 hover:text-red-400').on_click(xoa_file)
                    row_refs[type_key] = (lbl_status, ic)
                    return lbl_status

                with ui.row().classes('w-full gap-3'):
                    with ui.column().classes('w-[48%] gap-1'):
                        def _doi_che_do_video(e):
                            app_state['video_don'] = ""; app_state['ds_video'] = []; _reset_row('video_auto')
                        tg_video = ui.toggle({'gop': 'Gộp nhiều video → 1', 'don': '1 video xuyên suốt'}, value='gop', on_change=_doi_che_do_video).props('no-caps dense unelevated size=sm toggle-color=primary').classes('mb-1')
                        media_row('Video Nền', 'video_auto', 'movie')
                        media_row('Video Intro', 'intro', 'play_circle')
                        media_row('Video Outro', 'outro', 'stop_circle')
                        media_row('Khung PNG (chỉ video nền)', 'khung', 'filter_frames')
                    with ui.column().classes('w-[48%] gap-1'):
                        media_row('Nhạc Ưu Tiên', 'nhac_hay', 'library_music', True)
                        media_row('Nhạc Phụ', 'nhac_thuong', 'queue_music', True)
                        media_row('Nhạc Suno (Đắp bù)', 'nhac_suno', 'smart_toy', True)

            with ui.card().classes('w-full p-6 pro-card'):
                ui.label('2. THÔNG SỐ RENDER').classes('text-xs font-bold text-blue-400 mb-4 tracking-widest uppercase')
                
                with ui.row().classes('w-full gap-3 mb-5'):
                    sel_hieu_ung = ui.select(['Mờ êm ái', 'Tối thui', 'Chớp sáng', 'Cắt cái rụp'], value='Mờ êm ái', label='Chuyển cảnh').classes('flex-grow w-1/4').props('dark outlined dense')
                    sel_tg_hieu_ung = ui.select({0.5: '0.5s', 1.0: '1.0s', 1.5: '1.5s', 2.0: '2.0s'}, value=1.0, label='Thời gian').classes('flex-grow w-1/4').props('dark outlined dense')
                    sel_toc_do = ui.select({0.8: '0.8x (Chậm)', 1.0: '1.0x (Gốc)', 1.2: '1.2x (Nhanh)'}, value=1.0, label='Tốc độ').classes('flex-grow w-1/4').props('dark outlined dense')
                    sel_chat_luong = ui.select({'5000k': 'Nhẹ (CapCut)', '10000k': 'Nét cao', '20000k': 'Siêu nét'}, value='5000k', label='Chất lượng').classes('flex-grow w-1/4').props('dark outlined dense')

                with ui.row().classes('w-full items-center justify-between mb-5 pt-5 border-t border-[#334155]'):
                    with ui.row().classes('items-center gap-1'):
                        ui.label('Độ dài từ').classes('font-medium text-slate-300 mr-1 text-[13px]')
                        input_tu = ui.number(value=20, min=0, format='%d').classes('w-16').props('dark outlined dense input-class="font-semibold text-[15px] text-white"')
                        ui.label('đến').classes('text-slate-300 text-[13px] mx-1')
                        input_den = ui.number(value=30, min=0, format='%d').classes('w-16').props('dark outlined dense input-class="font-semibold text-[15px] text-white"')
                        ui.label('phút').classes('text-slate-300 text-[13px] ml-1')
                        
                        sel_che_do_nhac = ui.select(['Lặp vô tận', 'Không lặp (Báo lỗi)'], value='Lặp vô tận').classes('w-40 ml-4').props('dark outlined dense')

                    def lay_do_dai():
                        all_songs = app_state['ds_nhac_hay'] + app_state['ds_nhac_thuong'] + app_state.get('ds_nhac_suno', [])
                        tong = 0
                        loi = []
                        for f in all_songs:
                            dur = get_video_duration(f) if os.path.exists(f) else 0.0
                            if dur > 0:
                                tong += dur
                            else:
                                loi.append(os.path.basename(f))
                        
                        if loi:
                            msg = f"{loi[0]}" if len(loi) == 1 else f"{loi[0]} và {len(loi)-1} bài khác"
                            print(f"⚠️ Phát hiện {len(loi)} bài nhạc hỏng (Đã tự động bỏ qua): {msg}")
                            
                        if tong == 0 and all_songs:
                            raise Exception("Tất cả nhạc đều hỏng!")
                            
                        return tong

                    async def auto_tinh_gio(btn):
                        if not app_state['ds_nhac_hay'] and not app_state['ds_nhac_thuong'] and not app_state.get('ds_nhac_suno', []):
                            ui.notify('Vui lòng chọn nhạc trước!', type='warning')
                            return
                        btn.disable()
                        btn.text = 'Đang tính...'
                        try:
                            tong_giay = await run.io_bound(lay_do_dai)
                            tong_phut = int(tong_giay // 60)
                            input_den.value = tong_phut
                            if (input_tu.value or 0) > tong_phut: input_tu.value = tong_phut
                            ui.notify(f'Đã khớp nhạc: tổng {tong_phut} phút (đặt làm mức tối đa).', type='positive')
                        except Exception as e:
                            ui.notify(f"❌ {str(e)}", type='negative', position='top', timeout=8000)
                            print(f"🚨 [LỖI TÍNH NHẠC]: {str(e)}")
                        finally:
                            btn.text = 'Khớp nhạc'
                            btn.enable()

                    ui.button('Khớp nhạc', icon='sync', on_click=lambda e: auto_tinh_gio(e.sender)).props('outline size="sm" color="primary"').classes('py-2 border-[#334155]')

                async def add_to_queue():
                    if not (app_state['ds_video'] or app_state.get('video_don')) or (not app_state['ds_nhac_hay'] and not app_state['ds_nhac_thuong'] and not app_state.get('ds_nhac_suno', [])):
                        ui.notify('Lỗi: Thiếu Video nền hoặc Nhạc!', type='negative')
                        return
                    
                    t_min, t_max = float(input_tu.value or 0), float(input_den.value or 0)
                    if t_min > t_max: t_min, t_max = t_max, t_min
                    lo, hi = int(t_min * 60), int(t_max * 60)
                    t_secs = random.randint(lo, hi) if hi > 0 else 0
                    
                    if 'Không lặp' in sel_che_do_nhac.value and t_secs > 0:
                        ui.notify('Đang đối chiếu thời gian nhạc...', type='info')
                        try:
                            tong_giay = await run.io_bound(lay_do_dai)
                        except Exception as e:
                            ui.notify(f"❌ KHÔNG THỂ THÊM: {str(e)}", type='negative', position='top', timeout=8000)
                            return
                            
                        if lo > tong_giay:
                            ui.notify(f'Cảnh báo: Thời gian tối thiểu ({lo}s) vượt quá tổng thời lượng Nhạc ({int(tong_giay)}s).', type='negative', position='top', timeout=5000)
                            return
                        t_secs = random.randint(lo, max(lo, min(hi, int(tong_giay))))

                    du_an = {
                        "ten_file": input_ten.value or "video1",
                        "ds_video": ([app_state['video_don']] if app_state.get('video_don') else app_state['ds_video'].copy()),
                        "che_do_video": 'xuyen_suot' if app_state.get('video_don') else 'gop',
                        
                        "ds_nhac_hay": app_state['ds_nhac_hay'].copy(),
                        "ds_nhac_thuong": app_state['ds_nhac_thuong'].copy(),
                        "ds_nhac_suno": app_state.get('ds_nhac_suno', []).copy(),
                        "file_intro": app_state.get('file_intro', ""), "file_outro": app_state.get('file_outro', ""),
                        "file_khung": app_state.get('file_khung', ""),
                        "target_seconds": t_secs, "output_dir": app_state['output_dir'],
                        "hieu_ung": sel_hieu_ung.value, "tg_hieu_ung": sel_tg_hieu_ung.value,
                        "v_speed": sel_toc_do.value,
                        "che_do_nhac": sel_che_do_nhac.value,
                        "chat_luong": sel_chat_luong.value,
                        "trang_thai": "Chờ xử lý", "color": "slate-400", "progress": 0
                    }
                    app_state['hang_doi'].append(du_an); ve_lai_hang_doi()
                    try:
                        t = du_an['ten_file']
                        prefix_name = t.rstrip('0123456789')
                        if prefix_name != t:
                            num = int(t[len(prefix_name):])
                            input_ten.value = f"{prefix_name}{num + 1}"
                    except: pass

                ui.button('THÊM VÀO HÀNG ĐỢI RENDER', icon='playlist_add', on_click=add_to_queue).classes('w-full h-[45px] rounded-lg btn-main') 

        with ui.column().classes('flex-grow w-[50%] min-w-[500px] gap-6'): 
            
            with ui.card().classes('w-full pro-card flex-1 p-0 flex flex-col h-[400px] overflow-hidden'):
                with ui.row().classes('w-full px-6 py-4 border-b border-[#334155] items-center justify-between bg-[#1e293b] shrink-0'):
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('format_list_bulleted', size='sm', color='slate-400')
                        ui.label('DANH SÁCH RENDER').classes('text-xs font-bold text-blue-400 tracking-widest uppercase')
                    with ui.row().classes('items-center gap-4'):
                        sel_parallel = ui.select(options={1: '1 Luồng', 2: '2 Luồng (Chuẩn)', 3: '3 Luồng', 4: '4 Luồng (Vắt kiệt)'}, value=2).props('dark outlined dense borderless').classes('w-36 text-[13px] font-semibold text-slate-200')
                        ui.button('XÓA TẤT CẢ', on_click=lambda: [app_state['hang_doi'].clear(), ve_lai_hang_doi()]).props('flat color="red-400" size="sm"').classes('hover:bg-red-500/10 font-medium')

                with ui.column().classes('w-full px-5 pt-3 pb-1 gap-1 bg-[#1e293b] border-b border-[#334155] shrink-0'):
                    with ui.row().classes('w-full items-center justify-between'):
                        ui.label('TỔNG TIẾN ĐỘ XỬ LÝ').classes('text-[10px] font-bold text-slate-400 tracking-wider')
                        overall_pct_lbl = ui.label('0%').classes('text-[11px] font-bold text-blue-400')
                    overall_progress = ui.linear_progress(value=0, show_value=False).props('rounded size="8px" color="blue-400" track-color="#0f172a"').classes('w-full')

                queue_container = ui.column().classes('w-full flex-1 overflow-y-auto p-4 gap-2 custom-scrollbar min-h-0 bg-[#0f172a]')

                def update_status(index, text, color, percent=None):
                    if index < len(app_state['hang_doi']):
                        app_state['hang_doi'][index]['trang_thai'] = text
                        app_state['hang_doi'][index]['color'] = color
                        if percent is not None:
                            app_state['hang_doi'][index]['progress'] = max(0, min(100, percent))

                ui_elements = {}

                def ve_lai_hang_doi():
                    queue_container.clear()
                    ui_elements.clear()
                    if not app_state['hang_doi']:
                        with queue_container:
                            with ui.column().classes('w-full h-full items-center justify-center opacity-40 mt-12'):
                                ui.icon('inbox', size='4xl')
                                ui.label('Hàng đợi trống').classes('text-sm mt-2 font-medium')
                        return
                        
                    for i, d in enumerate(app_state['hang_doi']):
                        with queue_container:
                            card_col = ui.column().classes(f'w-full gap-2 px-4 py-3 bg-[#1e293b] border-l-4 border-{d["color"]} rounded-lg shadow-sm hover:bg-[#334155] transition-colors')
                            with card_col:
                                with ui.row().classes('w-full items-center justify-between'):
                                    with ui.row().classes('items-center gap-4 w-[65%]'):
                                        ui.label(f"{i+1:02d}").classes('font-bold text-slate-400 text-lg font-mono')
                                        with ui.column().classes('gap-0'):
                                            ui.label(d['ten_file']).classes('font-semibold text-[14px] text-slate-100 truncate')
                                            ui.label(f"Thời lượng: {d['target_seconds']//60} phút {d['target_seconds']%60:02d}s • Cân bằng phần cứng").classes('text-[11px] text-slate-400')
                                    
                                    with ui.row().classes('items-center gap-3'):
                                        lbl = ui.label(d['trang_thai']).classes(f'text-[11px] font-bold text-{d["color"]} bg-{d["color"]}/10 px-2 py-1 rounded uppercase')
                                        
                                        btn_class = 'hidden' if app_state.get('is_rendering', False) else 'hover:text-red-400 hover:bg-red-500/10'
                                        btn = ui.button(icon='delete_outline', on_click=lambda idx=i: [app_state['hang_doi'].pop(idx), ve_lai_hang_doi()]).props('flat round size="sm" color="slate-400"').classes(btn_class)

                                with ui.row().classes('w-full items-center gap-2'):
                                    prog = ui.linear_progress(value=d.get('progress', 0) / 100, show_value=False).props(f'rounded size="6px" color="{d["color"]}" track-color="#0f172a"').classes('flex-grow')
                                    pct_lbl = ui.label(f"{int(d.get('progress', 0))}%").classes('text-[10px] font-mono text-slate-400 w-10 text-right')
                            
                            ui_elements[i] = {'row': card_col, 'lbl': lbl, 'btn': btn, 'prog': prog, 'pct_lbl': pct_lbl}
                ve_lai_hang_doi()

                def sync_ui():
                    if app_state['hang_doi']:
                        for i, d in enumerate(app_state['hang_doi']):
                            if i in ui_elements:
                                el = ui_elements[i]
                                pct = d.get('progress', 0)
                                if el['lbl'].text != d['trang_thai']:
                                    el['lbl'].text = d['trang_thai']
                                    el['lbl'].classes(replace=f'text-[11px] font-bold text-{d["color"]} bg-{d["color"]}/10 px-2 py-1 rounded uppercase')
                                    el['row'].classes(replace=f'w-full gap-2 px-4 py-3 bg-[#1e293b] border-l-4 border-{d["color"]} rounded-lg shadow-sm hover:bg-[#334155] transition-colors')
                                    el['prog'].props(f'rounded size="6px" color="{d["color"]}" track-color="#0f172a"')
                                if el['prog'].value != pct / 100:
                                    el['prog'].value = pct / 100
                                    el['pct_lbl'].text = f"{int(pct)}%"

                        tong_pct = sum(d.get('progress', 0) for d in app_state['hang_doi']) / len(app_state['hang_doi'])
                    else:
                        tong_pct = 0

                    if overall_progress.value != tong_pct / 100:
                        overall_progress.value = tong_pct / 100
                        overall_pct_lbl.text = f"{int(tong_pct)}%"

                ui.timer(0.5, sync_ui)
                ui.timer(5, lambda: kiem_tra_cap_nhat_ui(False), once=True)
                ui.timer(0.3, _drain_log_queue)

                with ui.row().classes('w-full p-4 border-t border-[#334155] bg-[#1e293b] shrink-0'):
                    async def xu_ly_render_batch():
                        if not app_state['hang_doi']: return
                        if app_state.get('is_rendering', False): return 
                        
                        app_state['is_rendering'] = True
                        ve_lai_hang_doi() 
                        btn_start.disable()
                        btn_start.text = 'HỆ THỐNG ĐANG XỬ LÝ...'
                        
                        max_w = sel_parallel.value
                        def thread_worker():
                            with concurrent.futures.ThreadPoolExecutor(max_workers=max_w) as executor:
                                futures = []
                                for i, du_an in enumerate(app_state['hang_doi']):
                                    if "Hoàn thành" in du_an["trang_thai"]: continue 
                                    future = executor.submit(
                                        render_du_an_cach_ly, du_an["ten_file"], du_an["ds_video"], 
                                        du_an.get("ds_nhac_hay", []), du_an.get("ds_nhac_thuong", []), du_an.get("ds_nhac_suno", []),
                                        du_an["file_intro"], du_an["file_outro"], 
                                        du_an["target_seconds"], du_an["output_dir"], du_an["hieu_ung"], du_an["tg_hieu_ung"], 
                                        du_an.get("v_speed", 1.0), du_an.get("che_do_nhac", "Lặp vô tận"), du_an.get("chat_luong", "5000k"), update_status, i,
                                        file_khung=du_an.get("file_khung", ""), che_do_video=du_an.get("che_do_video", "gop")
                                    )
                                    futures.append(future)
                                
                                for future in concurrent.futures.as_completed(futures):
                                    try: future.result()
                                    except Exception as exc: print(f"\n[LỖI TIẾN TRÌNH NGẦM]: {exc}\n")

                        try:
                            await run.io_bound(thread_worker)
                            ui.notify('Hoàn tất toàn bộ hàng đợi!', type='positive', position='top-right')
                        except Exception as e: print(f"LỖI PHẦN MỀM: {e}")
                        finally:
                            app_state['is_rendering'] = False
                            btn_start.enable()
                            btn_start.text = 'BẮT ĐẦU XỬ LÝ'
                            ve_lai_hang_doi()

                    btn_start = ui.button('BẮT ĐẦU XỬ LÝ', icon='play_arrow', on_click=xu_ly_render_batch).classes('w-full h-[45px] rounded-lg btn-main')

            with ui.card().classes('w-full h-[160px] p-0 pro-card flex flex-col overflow-hidden'):
                with ui.row().classes('w-full px-5 py-2 bg-[#1e293b] border-b border-[#334155] items-center justify-between'):
                    ui.label('SYSTEM LOG').classes('text-[11px] font-bold text-slate-400 tracking-wider')
                
                log_console = ui.log(max_lines=200).classes('w-full flex-grow bg-[#0f172a] text-[#f8fafc] font-mono text-[12px] p-4 leading-relaxed focus:outline-none custom-scrollbar')
                log_console.push("[SYSTEM] Khởi động V8.0 thành công.\n[SMART FILLER] Đã thêm kho 'Nhạc Suno'. Nếu chế độ Không lặp thiếu thời gian, Nhạc Suno sẽ được gọi ra để đắp bù hoàn hảo vào cuối Video.\n[READY] Đã sẵn sàng làm việc...")

def resource_path(name):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)

_ico = resource_path('icon.ico')
ui.run(title="Render Studio Pro", port=8080, reload=False, dark=True, native=True, window_size=(1300, 850), favicon=_ico if os.path.exists(_ico) else None)