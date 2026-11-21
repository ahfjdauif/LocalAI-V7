# -*- coding: utf-8 -*-
"""
本地AI · 在线部署版（V7）

桌面本地大模型客户端（基于 Ollama 框架二次封装）。安装包仅包含软件本体，
不含推理环境与模型文件；首次启动进入「部署页」，由用户选择模型后，
软件联网下载 Ollama 运行环境与所选模型，部署完成后进入聊天界面。

本文件为软件主体程序：内置一个轻量本地 HTTP 服务，并通过 pywebview
以桌面窗口方式加载前端页面（setup.html / chat.html）。
前端只负责界面与交互，所有与 Ollama、下载部署、文档解析、运行模式相关的逻辑均在本文件实现。

Copyright (c) 2026 折**  保留所有合法权利
"""

import os
import sys
import re
import json
import time
import base64
import hashlib
import socket
import shutil
import zipfile
import platform
import tempfile
import threading
import subprocess
import urllib.request
import urllib.error
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ----------------------------------------------------------------------------
# 全局常量
# ----------------------------------------------------------------------------
APP_NAME = "本地AI · 通义千问"
APP_VERSION = "V7"
HOST = "127.0.0.1"          # 本地服务监听地址
PORT = 21434                # 本地服务监听端口
OLLAMA_HOST = "127.0.0.1"   # Ollama 服务地址
OLLAMA_PORT = 11500         # Ollama 服务端口（避开系统自带 Ollama 的 11434）
RUN_MODE_FILE = "run_mode.json"   # 运行模式配置（gpu / cpu / hybrid）
MODEL_DIR = "models"        # 模型目录名
ENV_DIR = "Ollama"          # 运行环境目录名
TMP_DIR = "_setup_tmp"      # 部署过程中的临时目录

# 运行环境下载源：国内镜像优先，失败回退官方地址
GH_PATH = "/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip"
ENV_SOURCES = [
    "https://gh-proxy.com/https://github.com" + GH_PATH,
    "https://ghfast.top/https://github.com" + GH_PATH,
    "https://github.com" + GH_PATH,
]

# 模型目录：来源为魔搭社区（国内直连），权重为 Qwen2.5 官方发布的 GGUF
MODEL_BASE = "https://www.modelscope.cn/models/%s/resolve/master/%s"
MODEL_CATALOG = {
    "qwen2.5:1.5b": {
        "label": "通义千问 1.5B",
        "note": "轻量，低配电脑也能跑",
        "use": "日常问答、文字整理、简单翻译",
        "ram": "4 GB",
        "tags": ["轻量", "快速"],
        "repo": "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        "files": [
            ("qwen2.5-1.5b-instruct-q4_k_m.gguf", 1117320736),
        ],
        "sha256": "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e",
    },
    "qwen2.5:3b": {
        "label": "通义千问 3B",
        "note": "笔记本流畅可用",
        "use": "写作、总结、代码片段、日常办公",
        "ram": "6 GB",
        "tags": ["均衡", "笔记本"],
        "repo": "Qwen/Qwen2.5-3B-Instruct-GGUF",
        "files": [
            ("qwen2.5-3b-instruct-q4_k_m.gguf", 2104932768),
        ],
        "sha256": "626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d",
    },
    "qwen2.5:7b": {
        "label": "通义千问 7B（推荐）",
        "note": "效果与速度的平衡点",
        "use": "通用问答、长文写作、代码辅助",
        "ram": "8 GB",
        "tags": ["推荐", "通用"],
        # 单文件 GGUF：分片版在部分 ollama 版本会报 "invalid split GGUF"
        "repo": "lmstudio-community/Qwen2.5-7B-Instruct-GGUF",
        "files": [
            ("Qwen2.5-7B-Instruct-Q4_K_M.gguf", 4683073952),
        ],
        "sha256": "3e357ab3eda2c442f25c0080bb8998eedc05fd16ce1728eacff9ccc5c3d240c6",
    },
    "qwen2.5:14b": {
        "label": "通义千问 14B",
        "note": "质量明显提升，建议独显或 16G 以上内存",
        "use": "专业写作、复杂推理、代码重构",
        "ram": "16 GB",
        "tags": ["高质量"],
        "repo": "lmstudio-community/Qwen2.5-14B-Instruct-GGUF",
        "files": [
            ("Qwen2.5-14B-Instruct-Q4_K_M.gguf", 8988110688),
        ],
        "sha256": "141de2876e84ae38d3dd667277949a720cdba17f96bf5b57598088e075f02c56",
    },
    "qwen2.5:32b": {
        "label": "通义千问 32B",
        "note": "接近商用质量，需要高端显卡",
        "use": "长文档分析、专业领域问答、复杂代码",
        "ram": "32 GB",
        "tags": ["专业"],
        "repo": "lmstudio-community/Qwen2.5-32B-Instruct-GGUF",
        "files": [
            ("Qwen2.5-32B-Instruct-Q4_K_M.gguf", 19851336288),
        ],
        "sha256": "d063fcda68bdd122f926d62597ccb86d0e6c9c1ff12c7e4a9563a957985f71bf",
    },
    "qwen2.5:72b": {
        "label": "通义千问 72B",
        "note": "旗舰级效果，需要 48GB 以上内存/显存",
        "use": "复杂推理、科研与专业任务",
        "ram": "64 GB",
        "tags": ["旗舰"],
        "repo": "lmstudio-community/Qwen2.5-72B-Instruct-GGUF",
        "files": [
            ("Qwen2.5-72B-Instruct-Q4_K_M.gguf", 47415715200),
        ],
        "sha256": "c2e1721ee5c7d642194f7e024e342f48acd348219c72c86e784868ad41c508d0",
    },
}

_ollama_proc = None         # 由本进程拉起的 ollama 子进程句柄
_owns_service = False       # 本进程是否负责停止 ollama 服务
_server = None              # 本地 HTTP 服务实例

# 部署状态（供部署页轮询）
_setup_lock = threading.Lock()
_setup = {
    "stage": "idle",        # idle / env / model / create / done / error
    "model": "",
    "percent": 0,
    "speed": 0,             # 字节/秒
    "downloaded": 0,
    "total": 0,
    "message": "",
    "error": "",
}
_setup_cancel = threading.Event()
_setup_thread = None


# ----------------------------------------------------------------------------
# 原生启动闪屏：无边框圆角窗口 + 启动图 + 状态文字（纯 ctypes，不依赖 tkinter）。
# 双击后 Python 一起来就显示；网页启动页画出第一帧时由 /api/ui-ready 关掉。
# ----------------------------------------------------------------------------
try:
    import ctypes
    import ctypes.wintypes as wt

    _SP_USER32 = ctypes.WinDLL("user32", use_last_error=True)
    _SP_GDI32 = ctypes.WinDLL("gdi32", use_last_error=True)
    _SP_KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _SP_OK = True
except Exception:  # 非 Windows / 受限环境：闪屏降级为无
    ctypes = None
    wt = None
    _SP_USER32 = _SP_GDI32 = _SP_KERNEL32 = None
    _SP_OK = False


LRESULT = ctypes.c_ssize_t
_SP_WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class _SP_WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wt.UINT),
        ("lpfnWndProc", _SP_WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
    ]


class _SP_RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _SP_PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", wt.HDC),
        ("fErase", wt.BOOL),
        ("rcPaint", _SP_RECT),
        ("fRestore", wt.BOOL),
        ("fIncUpdate", wt.BOOL),
        ("rgbReserved", ctypes.c_byte * 32),
    ]


WM_PAINT = 0x000F
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_ERASEBKGND = 0x0014
WM_APP_TEXT = 0x8001
WM_TIMER = 0x0113

WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
IMAGE_BITMAP = 0
LR_LOADFROMFILE = 0x0010
SRCCOPY = 0x00CC0020
TRANSPARENT = 1
DT_VCENTER = 0x00000004
DT_SINGLELINE = 0x00000020
SW_SHOW = 5
AW_BLEND = 0x00080000
AW_HIDE = 0x00010000


def _splash_proto():
    _SP_USER32.RegisterClassW.argtypes = [ctypes.POINTER(_SP_WNDCLASSW)]
    _SP_USER32.CreateWindowExW.restype = wt.HWND
    _SP_USER32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
    _SP_USER32.DefWindowProcW.restype = LRESULT
    _SP_USER32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    _SP_USER32.BeginPaint.restype = wt.HDC
    _SP_USER32.BeginPaint.argtypes = [wt.HWND, ctypes.POINTER(_SP_PAINTSTRUCT)]
    _SP_USER32.EndPaint.argtypes = [wt.HWND, ctypes.POINTER(_SP_PAINTSTRUCT)]
    _SP_USER32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
    _SP_USER32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
    _SP_USER32.DispatchMessageW.restype = LRESULT
    _SP_USER32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
    _SP_USER32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    _SP_USER32.PostQuitMessage.argtypes = [ctypes.c_int]
    _SP_USER32.InvalidateRect.argtypes = [wt.HWND, ctypes.POINTER(_SP_RECT), wt.BOOL]
    _SP_USER32.SetWindowRgn.argtypes = [wt.HWND, wt.HRGN, wt.BOOL]
    _SP_USER32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wt.UINT]
    _SP_USER32.GetSystemMetrics.argtypes = [ctypes.c_int]
    _SP_USER32.LoadImageW.restype = wt.HANDLE
    _SP_USER32.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT,
                                  ctypes.c_int, ctypes.c_int, wt.UINT]
    _SP_USER32.DrawTextW.argtypes = [wt.HDC, wt.LPCWSTR, ctypes.c_int,
                                 ctypes.POINTER(_SP_RECT), wt.UINT]
    _SP_USER32.AnimateWindow.argtypes = [wt.HWND, wt.DWORD, wt.DWORD]
    _SP_GDI32.BitBlt.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             wt.HDC, ctypes.c_int, ctypes.c_int, wt.DWORD]
    _SP_GDI32.StretchBlt.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                     wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                     wt.DWORD]
    _SP_GDI32.CreateCompatibleDC.restype = wt.HDC
    _SP_GDI32.CreateCompatibleDC.argtypes = [wt.HDC]
    _SP_GDI32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
    _SP_GDI32.CreateRoundRectRgn.restype = wt.HRGN
    _SP_GDI32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
    _SP_GDI32.CreateFontW.restype = wt.HFONT
    _SP_GDI32.CreateFontW.argtypes = [ctypes.c_int] * 5 + [wt.DWORD] * 8 + [wt.LPCWSTR]
    _SP_GDI32.SetBkMode.argtypes = [wt.HDC, ctypes.c_int]
    _SP_GDI32.SetTextColor.argtypes = [wt.HDC, wt.COLORREF]
    _SP_KERNEL32.GetModuleHandleW.restype = wt.HINSTANCE
    _SP_KERNEL32.GetModuleHandleW.argtypes = [wt.LPCWSTR]




class _Splash(object):
    """无边框圆角原生窗口，显示启动图 + 一行状态文字。"""

    W, H = 620, 400

    def __init__(self, bmp_path):
        self.bmp_path = bmp_path
        self._text = "正在启动…"
        self._hwnd = None
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._thread = None
        self._proc = _SP_WNDPROC(self._on_message)
        self._bmp = None
        self._memdc = None
        self._font = None
        self._w = self.W
        self._h = self.H
        self._sc = 1.0

    # ---------- 对外接口 ----------
    def start(self, timeout=1.5):
        if not _SP_OK or not os.path.isfile(self.bmp_path):
            return False
        _splash_proto()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self._ready.wait(timeout)

    def set_text(self, text):
        with self._lock:
            self._text = str(text)
        if self._hwnd:
            _SP_USER32.PostMessageW(self._hwnd, WM_APP_TEXT, 0, 0)

    def close(self):
        hwnd = self._hwnd
        if hwnd:
            _SP_USER32.PostMessageW(hwnd, WM_CLOSE, 0, 0)

    # ---------- 内部 ----------
    def _on_message(self, hwnd, msg, wparam, lparam):
        if msg == WM_PAINT:
            self._paint(hwnd)
            return 0
        if msg == WM_APP_TEXT:
            _SP_USER32.InvalidateRect(hwnd, None, True)
            return 0
        if msg == WM_TIMER:
            _SP_USER32.InvalidateRect(hwnd, None, False)
            return 0
        if msg == WM_ERASEBKGND:
            return 1
        if msg == WM_CLOSE:
            # 淡出后再销毁，避免闪屏"啪"地一下消失
            try:
                _SP_USER32.AnimateWindow(hwnd, 200, AW_BLEND | AW_HIDE)
            except Exception:
                pass
            _SP_USER32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            self._hwnd = None
            _SP_USER32.PostQuitMessage(0)
            return 0
        return _SP_USER32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _paint(self, hwnd):
        ps = _SP_PAINTSTRUCT()
        hdc = _SP_USER32.BeginPaint(hwnd, ctypes.byref(ps))
        try:
            if self._memdc and self._bmp:
                _SP_GDI32.StretchBlt(hdc, 0, 0, self._w, self._h,
                                     self._memdc, 0, 0, self.W, self.H, SRCCOPY)
            _SP_GDI32.SetBkMode(hdc, TRANSPARENT)
            _SP_GDI32.SetTextColor(hdc, 0x00F2E4D4)  # COLORREF: #D4E4F2
            if self._font:
                _SP_GDI32.SelectObject(hdc, self._font)
            rc = _SP_RECT(int(22 * self._sc), self._h - int(58 * self._sc),
                          self._w - int(22 * self._sc), self._h - int(16 * self._sc))
            with self._lock:
                text = self._text
            _SP_USER32.DrawTextW(hdc, text, -1, ctypes.byref(rc), DT_VCENTER | DT_SINGLELINE)
        finally:
            _SP_USER32.EndPaint(hwnd, ctypes.byref(ps))

    def _run(self):
        try:
            hinst = _SP_KERNEL32.GetModuleHandleW(None)
            cls_name = "LocalAISplashWnd"
            wc = _SP_WNDCLASSW()
            wc.style = 0
            wc.lpfnWndProc = self._proc
            wc.hInstance = hinst
            wc.lpszClassName = cls_name
            _SP_USER32.RegisterClassW(ctypes.byref(wc))

            self._bmp = _SP_USER32.LoadImageW(None, self.bmp_path, IMAGE_BITMAP, 0, 0,
                                          LR_LOADFROMFILE)
            if not self._bmp:
                return
            sc = _dpi_scale()
            self._sc = sc
            self._w = int(round(self.W * sc))
            self._h = int(round(self.H * sc))
            scr_w = _SP_USER32.GetSystemMetrics(0)
            scr_h = _SP_USER32.GetSystemMetrics(1)
            x = max(0, (scr_w - self._w) // 2)
            y = max(0, (scr_h - self._h) // 2 - int(40 * sc))
            hwnd = _SP_USER32.CreateWindowExW(
                WS_EX_TOPMOST | WS_EX_TOOLWINDOW, cls_name, "本地AI",
                WS_POPUP | WS_VISIBLE, x, y, self._w, self._h, None, None, hinst, None)
            if not hwnd:
                return
            self._hwnd = hwnd
            hdc = _SP_USER32.GetDC(hwnd)
            self._memdc = _SP_GDI32.CreateCompatibleDC(hdc)
            _SP_GDI32.SelectObject(self._memdc, self._bmp)
            _SP_USER32.ReleaseDC(hwnd, hdc)
            rgn = _SP_GDI32.CreateRoundRectRgn(0, 0, self._w + 1, self._h + 1,
                                               int(22 * sc), int(22 * sc))
            _SP_USER32.SetWindowRgn(hwnd, rgn, True)
            self._font = _SP_GDI32.CreateFontW(-int(15 * sc), 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 5, 0,
                                           "Microsoft YaHei")
            try:
                _SP_USER32.AnimateWindow(hwnd, 220, AW_BLEND)
            except Exception:
                pass
            _SP_USER32.UpdateWindow(hwnd)
            _SP_USER32.SetTimer(hwnd, 1, 250, None)
            self._ready.set()

            msg = wt.MSG()
            while _SP_USER32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                _SP_USER32.TranslateMessage(ctypes.byref(msg))
                _SP_USER32.DispatchMessageW(ctypes.byref(msg))
        except Exception:
            pass
        finally:
            self._ready.set()

_splash_obj = None


def _splash_bmp_path():
    return os.path.join(web_dir(), "splash_bg.bmp")


_SPLASH_ENABLED = False   # 小窗口动画已按需求去掉，只保留网页启动页


def splash_init():
    """显示原生闪屏（当前已关闭，仅保留实现）。"""
    global _splash_obj
    if not _SPLASH_ENABLED or not _SP_OK or _splash_obj is not None:
        return
    try:
        bmp = _splash_bmp_path()
        if not os.path.isfile(bmp):
            return
        _splash_obj = _Splash(bmp)
        _splash_obj.start(timeout=1.2)
    except Exception:
        _splash_obj = None


def splash_text(msg):
    """更新闪屏状态文字（失败静默）。"""
    if _splash_obj is None:
        return
    try:
        _splash_obj.set_text(msg)
    except Exception:
        pass


def splash_close():
    """关闭闪屏（幂等）。"""
    global _splash_obj
    if _splash_obj is None:
        return
    try:
        _splash_obj.close()
    except Exception:
        pass
    _splash_obj = None


def _splash_close_after(delay):
    """兜底：网页万一没就绪，也在若干秒后撤掉闪屏。"""
    time.sleep(delay)
    splash_close()




# ----------------------------------------------------------------------------
# 路径解析：区分「开发态（源码运行）」与「发布态（PyInstaller 单文件）」
# ----------------------------------------------------------------------------
def app_dir():
    """返回程序所在目录。打包后为 exe 所在目录，未打包时为源码目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def web_dir():
    """返回前端页面目录。打包后前端页面被释放到 exe 同级的 web 目录。"""
    base = app_dir()
    cand = os.path.join(base, "web")
    if os.path.isdir(cand):
        return cand
    # 开发态回退：源码同级 web 目录
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def models_dir():
    """返回模型目录（Ollama 的 models 根目录）。"""
    return os.path.join(app_dir(), MODEL_DIR)


def env_dir():
    """返回运行环境目录。"""
    return os.path.join(app_dir(), ENV_DIR)


def tmp_dir():
    """返回部署临时目录。"""
    return os.path.join(app_dir(), TMP_DIR)


def short_path(path):
    """返回 Windows 8.3 短路径，用于规避中文/空格/长路径导致的失败。"""
    try:
        if platform.system() == "Windows":
            import ctypes
            buf = ctypes.create_unicode_buffer(1024)
            if ctypes.windll.kernel32.GetShortPathNameW(path, buf, 1024):
                if buf.value:
                    return buf.value
    except Exception:
        pass
    return path


def deploy_log(text):
    """把部署过程的错误细节追加到程序目录下的日志，方便用户回传排查。"""
    try:
        fp = os.path.join(app_dir(), "部署错误日志.txt")
        # 日志超过 512KB 就滚动一次，避免越积越大
        try:
            if os.path.isfile(fp) and os.path.getsize(fp) > 512 * 1024:
                bak = fp + ".1"
                if os.path.isfile(bak):
                    os.remove(bak)
                os.replace(fp, bak)
        except Exception:
            pass
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(fp, "a", encoding="utf-8") as f:
            f.write("\n===== %s =====\n%s\n" % (stamp, text))
        return fp
    except Exception:
        return ""


def free_space_gb(path=None):
    """返回程序所在磁盘的可用空间（GB）。"""
    try:
        p = path or app_dir()
        while p and not os.path.exists(p):
            p = os.path.dirname(p)
        return shutil.disk_usage(p).free / float(1024 ** 3)
    except Exception:
        return -1.0


def _strip_bundle_paths(env):
    """把 PyInstaller 解压目录（_MEIxxxx）从子进程 PATH 里摘掉。

    这是临时目录删不掉的根因：ollama 继承的 PATH 里带着 _MEI，它拉起的
    llama-server 会优先从 _MEI 里加载 msvcp140/vcruntime140 等运行库，
    我们退出时这些 DLL 仍被 llama-server 占用，引导程序就删不掉目录，
    弹出 "Failed to remove temporary directory" 并留下一份 140+ MB 的副本。
    """
    try:
        mei = getattr(sys, "_MEIPASS", "") or ""
        mei = os.path.abspath(mei) if mei else ""
    except Exception:
        mei = ""
    path = env.get("PATH") or ""
    parts = []
    for p in path.split(os.pathsep):
        if not p:
            continue
        try:
            ap = os.path.abspath(p)
        except Exception:
            ap = p
        if mei and (ap == mei or ap.startswith(mei + os.sep)):
            continue
        if "_MEI" in p.upper():
            continue
        parts.append(p)
    env["PATH"] = os.pathsep.join(parts)
    for k in list(env):
        if k.startswith("_PYI_"):
            env.pop(k, None)
    return env


def _child_env():
    """给所有子进程用的干净环境（不含本程序的解压目录）。"""
    try:
        return _strip_bundle_paths(dict(os.environ))
    except Exception:
        return None


def _run_hidden(args, **kw):
    """统一以「无窗口」方式运行子进程。

    CREATE_NO_WINDOW 让控制台程序不分配控制台；STARTF_USESHOWWINDOW + SW_HIDE
    再兜一层，保证任何情况下都不会冒出黑色命令框。
    """
    kw.setdefault("creationflags", _win_flags())
    kw.setdefault("startupinfo", _hidden_startupinfo())
    if "env" not in kw:
        kw["env"] = _child_env()
    return subprocess.run(args, **kw)


def _dpi_scale():
    """当前系统 DPI 缩放倍数（1.0 = 100%，1.25 = 125%）。"""
    try:
        import ctypes
        dpi = ctypes.windll.user32.GetDpiForSystem()
        if dpi:
            return dpi / 96.0
    except Exception:
        pass
    return 1.0


def _set_dpi_aware():
    """必须在创建任何窗口之前调用。

    pywebview/WebView2 初始化时会把进程 DPI 感知切到 per-monitor；如果闪屏窗口
    已经显示，系统会按新缩放重算它的尺寸和位置（左上角锚点不动），视觉上就是
    "闪屏突然缩到左上角并卡一下"。先把感知固定下来，就不会再有这次跳变。
    """
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)  # PER_MONITOR_AWARE_V2
        return
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


def clean_stale_mei(max_age_hours=6):
    """清理以前残留的 _MEI 解压目录（当前进程在用的、以及 6 小时内的会跳过）。"""
    if platform.system() != "Windows":
        return 0
    removed = 0
    try:
        cur = os.path.abspath(getattr(sys, "_MEIPASS", "") or "")
    except Exception:
        cur = ""
    root = os.environ.get("TEMP") or tempfile.gettempdir()
    try:
        names = os.listdir(root)
    except Exception:
        return 0
    for name in names:
        if not name.upper().startswith("_MEI"):
            continue
        p = os.path.join(root, name)
        if not os.path.isdir(p):
            continue
        ap = os.path.abspath(p)
        if cur and (ap == cur or cur.startswith(ap + os.sep)):
            continue
        try:
            if time.time() - os.path.getmtime(p) < max_age_hours * 3600:
                continue
        except Exception:
            continue
        try:
            shutil.rmtree(p, ignore_errors=True)
            if not os.path.exists(p):
                removed += 1
        except Exception:
            pass
    return removed


def _hide_own_console():
    """如果本进程被附着到控制台（源码运行、调试器、命令行启动），立刻隐藏并脱离。"""
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        u32 = ctypes.windll.user32
        hwnd = k32.GetConsoleWindow()
        if hwnd:
            u32.ShowWindow(hwnd, 0)   # SW_HIDE
            k32.FreeConsole()
    except Exception:
        pass


def _win_flags():
    return 0x08000000 if platform.system() == "Windows" else 0


def _hidden_startupinfo():
    """隐藏子进程窗口（ollama 派生的子进程也会继承，避免黑色弹窗）。"""
    if platform.system() != "Windows":
        return None
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        return si
    except Exception:
        return None


def _ollama_version(exe):
    """读取 ollama 客户端版本，用于日志定位。"""
    try:
        r = _run_hidden([exe, "--version"], stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, timeout=30)
        lines = r.stdout.decode("utf-8", "replace").strip().splitlines()
        return lines[-1][:80] if lines else "unknown"
    except Exception as e:
        return "读取失败：%s" % e


def _list_models_text(exe, env):
    """执行 ollama list，返回文本输出（失败时返回错误说明）。"""
    try:
        r = _run_hidden([exe, "list"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        timeout=60, env=env)
        return r.stdout.decode("utf-8", "replace")
    except Exception as e:
        return "list 执行失败：%s" % e


def _model_in_list(exe, env, model_key):
    """判断模型是否真的出现在 ollama list 中（以服务端为准）。"""
    for line in _list_models_text(exe, env).splitlines():
        parts = line.split()
        if parts and parts[0] == model_key:
            return True
    return False


def ollama_exe():
    """定位 ollama 可执行文件；找不到时返回空字符串（绝不返回裸命令名）。"""
    for cand in (os.path.join(env_dir(), "ollama.exe"),
                 os.path.join(app_dir(), "ollama.exe")):
        if os.path.isfile(cand):
            return cand
    found = shutil.which("ollama")
    return found or ""


# ----------------------------------------------------------------------------
# 环境 / 模型检测
# ----------------------------------------------------------------------------
def _manifests_dirs(root):
    """返回模型清单目录列表（兼容 ollama 的 manifests 与 manifests-v2）。"""
    out = []
    for name in ("manifests-v2", "manifests"):
        d = os.path.join(root, name)
        if os.path.isdir(d):
            out.append(d)
    return out


def _api_tags_models(timeout=4):
    """查询本程序推理服务的模型列表（服务未启动时返回空列表）。"""
    try:
        with urllib.request.urlopen("http://%s:%d/api/tags" % (OLLAMA_HOST, OLLAMA_PORT),
                                    timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace") or "{}")
        return [m.get("name") for m in (data.get("models") or []) if m.get("name")]
    except Exception:
        return []


def _has_model(root=None):
    """判断是否已有可用模型：先查模型目录，再问推理服务本体。"""
    roots = []
    if root:
        roots.append(root)
    roots.append(models_dir())
    # 注意：不要再看 %USERPROFILE%\.ollama\models。本程序的 serve 一律把
    # OLLAMA_MODELS 强制指向安装目录下的 models，用户机器上原有的官方 Ollama
    # 模型不能算“本程序已部署”，否则会在没有任何可用模型时误判为就绪，
    # 直接进聊天页且看不到部署入口。
    for r in roots:
        for m in _manifests_dirs(r):
            for _dp, _dn, _fn in os.walk(m):
                if _fn:
                    return True
    # 目录里没有，但服务端可能有（例如服务用了别的模型目录）
    if service_running() and _api_tags_models():
        return True
    return False


def env_ready():
    """运行环境是否就绪：必须真的存在 ollama.exe 文件。"""
    exe = ollama_exe()
    return bool(exe) and os.path.isfile(exe)


def port_open(host, port, timeout=1.0):
    """检测某端口是否可连接（用于判断 Ollama 服务是否已启动）。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def service_running():
    """Ollama 服务是否在运行。"""
    return port_open(OLLAMA_HOST, OLLAMA_PORT)


# ----------------------------------------------------------------------------
# 运行模式（GPU / CPU / GPU+CPU 联合）
# ----------------------------------------------------------------------------
def read_run_mode():
    """读取运行模式配置，默认 gpu。"""
    try:
        fp = os.path.join(app_dir(), RUN_MODE_FILE)
        if os.path.isfile(fp):
            with open(fp, "r", encoding="utf-8") as f:
                mode = (json.load(f) or {}).get("mode", "gpu")
                if mode in ("gpu", "cpu", "hybrid"):
                    return mode
    except Exception:
        pass
    return "gpu"


def write_run_mode(mode):
    """保存运行模式配置（先写临时文件再替换，避免写一半断电留下坏文件）。"""
    fp = os.path.join(app_dir(), RUN_MODE_FILE)
    tmp = fp + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"mode": mode}, f)
        os.replace(tmp, fp)
    except Exception:
        try:
            with open(fp, "w", encoding="utf-8") as f:
                json.dump({"mode": mode}, f)
        except Exception:
            pass


def mode_env(mode):
    """把运行模式转换为 Ollama 相关环境变量。"""
    env = dict(os.environ)
    # 统一把模型目录指向本程序 models 目录
    env["OLLAMA_MODELS"] = models_dir()
    # 强制使用本程序自己的端口，避免被系统里已有 Ollama 的配置带偏
    env["OLLAMA_HOST"] = "%s:%d" % (OLLAMA_HOST, OLLAMA_PORT)
    if mode == "cpu":
        env["OLLAMA_NUM_GPU"] = "0"
        env.pop("CUDA_VISIBLE_DEVICES", None)
    elif mode == "hybrid":
        env["OLLAMA_NUM_GPU"] = "999"   # 交给 Ollama 自动按显存分配层
    else:  # gpu
        env["OLLAMA_NUM_GPU"] = "999"
    return _strip_bundle_paths(env)


# ----------------------------------------------------------------------------
# Ollama 服务进程管理
# ----------------------------------------------------------------------------
def _kill_port_owner(port):
    """结束占用指定端口的进程，保证服务是我们自己按正确配置拉起的。"""
    if platform.system() != "Windows":
        return
    try:
        out = _run_hidden(["netstat", "-ano", "-p", "TCP"], stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL)
        pids = set()
        for line in out.stdout.decode("utf-8", "replace").splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[1].endswith(":%d" % port) and parts[3] == "LISTENING":
                if parts[4].isdigit():
                    pids.add(int(parts[4]))
        for pid in pids:
            try:
                _run_hidden(["taskkill", "/F", "/PID", str(pid)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        return True
    except Exception as e:
        deploy_log("结束端口 %d 占用进程失败：%s" % (port, e))
        return False


def start_service(mode=None, _attempt=1):
    """启动 Ollama 服务进程（若已在运行则直接返回）。"""
    global _ollama_proc
    if service_running():
        # 端口上有服务，但若不是本进程拉起的，它可能没带我们的 OLLAMA_MODELS，
        # 会造成模型被写到用户目录、随后判定为"未注册"。这种情况先接管。
        if _ollama_proc is not None and _ollama_proc.poll() is None:
            return True
        _kill_port_owner(OLLAMA_PORT)
        time.sleep(1)
    if mode is None:
        mode = read_run_mode()
    exe = ollama_exe()
    if not exe:
        return False
    try:
        creation = 0
        if platform.system() == "Windows":
            # CREATE_NO_WINDOW，避免弹出黑色控制台窗口
            creation = 0x08000000
        os.makedirs(tmp_dir(), exist_ok=True)
        logf = open(os.path.join(tmp_dir(), "ollama_serve.log"), "ab")
        try:
            _ollama_proc = subprocess.Popen(
                [exe, "serve"],
                cwd=app_dir(),
                env=mode_env(mode),
                stdout=logf,
                stderr=logf,
                creationflags=creation,
                startupinfo=_hidden_startupinfo(),
            )
        finally:
            # 子进程已继承句柄，这里的副本及时关掉，避免每次重启泄漏一个 fd
            try:
                logf.close()
            except Exception:
                pass
    except Exception as e:
        deploy_log("启动 ollama serve 失败：%s" % e)
        return False
    # 等待端口可用（每次最多 15 秒）
    for _ in range(30):
        if service_running():
            return True
        time.sleep(0.5)
    if _attempt < 2:
        # 刚停过服务时，旧进程可能还没完全退出，端口没释放；清理后再来一次
        try:
            if _ollama_proc is not None and _ollama_proc.poll() is None:
                _ollama_proc.kill()
        except Exception:
            pass
        time.sleep(1.2)
        _kill_port_owner(OLLAMA_PORT)
        return start_service(mode, _attempt=2)
    if not service_running():
        tail = ""
        try:
            with open(os.path.join(tmp_dir(), "ollama_serve.log"), "rb") as f:
                tail = f.read()[-800:].decode("utf-8", "replace")
        except Exception:
            pass
        deploy_log("ollama serve 启动后 30 秒内端口 %d 仍不可用（已重试 1 次）。serve 输出：%s"
                   % (OLLAMA_PORT, tail.strip()))
    return service_running()


def stop_service():
    """停止 Ollama 服务（优先结束由本进程拉起的子进程）。"""
    global _ollama_proc
    try:
        if _ollama_proc is not None and _ollama_proc.poll() is None:
            _ollama_proc.terminate()
            try:
                _ollama_proc.wait(timeout=5)
            except Exception:
                _ollama_proc.kill()
    except Exception:
        pass
    _ollama_proc = None
    # 只结束占用本程序端口的实例；绝不能 taskkill /IM ollama.exe，
    # 否则会把用户自己安装、正在使用的官方 Ollama 一起杀掉。
    if service_running():
        _kill_port_owner(OLLAMA_PORT)
    # 模型进程也要收掉：它可能还占着 _MEI 里的运行库，导致目录删不掉
    try:
        _run_hidden(["taskkill", "/F", "/IM", "llama-server.exe"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    for _ in range(16):
        if not service_running():
            break
        time.sleep(0.25)
    return not service_running()


# ----------------------------------------------------------------------------
# 与 Ollama 通信的轻量 HTTP 转发
# ----------------------------------------------------------------------------
def ollama_url(path):
    return "http://%s:%d%s" % (OLLAMA_HOST, OLLAMA_PORT, path)


def ollama_get(path, timeout=5):
    """GET 方式访问 Ollama，返回 (status, body_text)。"""
    try:
        req = urllib.request.Request(ollama_url(path), method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)


def ollama_stream(path, payload, timeout=600):
    """POST 方式访问 Ollama 并流式返回（生成器，逐块产出字节）。"""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        ollama_url(path), data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    try:
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            yield chunk
    finally:
        try:
            resp.close()
        except Exception:
            pass


def ollama_post_json(path, payload, timeout=600):
    """POST 方式访问 Ollama，非流式返回完整 JSON 文本。"""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        ollama_url(path), data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)


# ----------------------------------------------------------------------------
# 模型中心：内置清单 + 联网校验（ModelScope 官方仓库）
# ----------------------------------------------------------------------------
CATALOG_CACHE_FILE = "catalog_cache.json"
_catalog_lock = threading.Lock()
_catalog_state = {"checked_at": "", "online": False, "models": {}, "error": ""}
_catalog_last_try = 0.0


def _model_size(meta):
    return sum(sz for _n, sz in meta["files"])


def _load_catalog_cache():
    """读取上次联网校验结果（大小/sha256/时间）。"""
    try:
        fp = os.path.join(app_dir(), CATALOG_CACHE_FILE)
        if not os.path.isfile(fp):
            return
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        with _catalog_lock:
            _catalog_state["checked_at"] = data.get("checked_at", "")
            _catalog_state["online"] = bool(data.get("online"))
            _catalog_state["models"] = data.get("models") or {}
    except Exception:
        pass


def _save_catalog_cache():
    try:
        fp = os.path.join(app_dir(), CATALOG_CACHE_FILE)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(_catalog_state, f, ensure_ascii=False)
    except Exception:
        pass


def _fetch_repo_files(repo):
    """查 ModelScope 仓库文件列表，返回 {文件名: (大小, sha256)}。"""
    url = ("https://www.modelscope.cn/api/v1/models/%s/repo/files"
           "?Revision=master&Recursive=true" % repo)
    req = urllib.request.Request(url, headers={"User-Agent": "LocalAI/2.1"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode("utf-8", "replace") or "{}")
    out = {}
    for f in ((data.get("Data") or {}).get("Files") or []):
        path = f.get("Path") or ""
        if path.lower().endswith(".gguf"):
            out[path] = (int(f.get("Size") or 0), (f.get("Sha256") or "").lower())
    return out


def refresh_catalog(force=False, min_interval=30):
    """联网刷新模型大小与 sha256；失败时保留内置值。"""
    global _catalog_last_try
    now = time.time()
    if not force and now - _catalog_last_try < min_interval:
        return _catalog_state
    _catalog_last_try = now
    models = {}
    ok_any = False
    err = ""
    for key, meta in MODEL_CATALOG.items():
        try:
            files = _fetch_repo_files(meta["repo"])
            fname = meta["files"][0][0]
            if fname in files:
                size, sha = files[fname]
                models[key] = {"size": size, "sha256": sha}
                ok_any = True
        except Exception as e:
            err = str(e)
    with _catalog_lock:
        if ok_any:
            _catalog_state["models"].update(models)
            _catalog_state["checked_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _catalog_state["online"] = ok_any
        _catalog_state["error"] = err
    if ok_any:
        _save_catalog_cache()
    return _catalog_state


def catalog_snapshot():
    """给前端用的模型清单（含是否已安装）。"""
    installed = set()
    if service_running():
        installed = set(_api_tags_models(timeout=3))
    try:
        for key in MODEL_CATALOG:
            for root in [models_dir()]:
                for mdir in _manifests_dirs(root):
                    p = os.path.join(mdir, "ollama.com", "library",
                                     key.split(":")[0], key.split(":")[1])
                    if os.path.isdir(p):
                        installed.add(key)
    except Exception:
        pass
    with _catalog_lock:
        cache = dict(_catalog_state)
    models = []
    for key, meta in MODEL_CATALOG.items():
        info = (cache.get("models") or {}).get(key) or {}
        size = int(info.get("size") or _model_size(meta))
        models.append({
            "key": key,
            "label": meta["label"],
            "note": meta["note"],
            "use": meta.get("use", ""),
            "ram": meta.get("ram", ""),
            "tags": meta.get("tags", []),
            "size": size,
            "installed": key in installed,
            "sha256": info.get("sha256") or meta.get("sha256", ""),
        })
    return {
        "models": models,
        "online": bool(cache.get("online")),
        "checked_at": cache.get("checked_at", ""),
        "error": cache.get("error", ""),
    }


def _validate_model(key):
    return key if key in MODEL_CATALOG else ""


def _validate_mode(mode):
    return mode if mode in ("gpu", "cpu", "hybrid") else ""


def _api_error(code, msg, hint=""):
    return {"error": msg, "code": code, "hint": hint}

# ----------------------------------------------------------------------------
# 部署状态管理
# ----------------------------------------------------------------------------
_state_cache = {"t": 0.0, "env": False, "has_model": False}


def _invalidate_state():
    """模型/环境发生变化后立刻让状态缓存失效。"""
    _state_cache["t"] = 0.0


def _quick_flags(ttl=1.5):
    """带缓存的就绪检测：前端约 0.9 秒轮询一次，没必要每次遍历模型目录。"""
    now = time.time()
    if now - _state_cache["t"] < ttl:
        return _state_cache["env"], _state_cache["has_model"]
    env = env_ready()
    has_model = _has_model()
    _state_cache.update({"t": now, "env": env, "has_model": has_model})
    return env, has_model


def setup_state():
    """返回当前部署状态副本。"""
    with _setup_lock:
        st = dict(_setup)
    env, has_model = _quick_flags()
    st["env"] = env
    st["has_model"] = has_model
    st["models_dir"] = models_dir()
    st["env_dir"] = env_dir()
    st["busy"] = bool(_setup_thread is not None and _setup_thread.is_alive())
    return st


def _set_setup(**kw):
    """更新部署状态字段。"""
    with _setup_lock:
        _setup.update(kw)


def _set_progress(stage, message, downloaded=None, total=None, speed=None):
    """更新进度：阶段、提示语、已下载字节、总字节、速度。"""
    fields = {"stage": stage, "message": message}
    if downloaded is not None:
        fields["downloaded"] = int(downloaded)
    if total is not None:
        fields["total"] = int(total)
    if speed is not None:
        fields["speed"] = int(speed)
    if downloaded is not None and total:
        fields["percent"] = int(min(100, downloaded * 100 / total))
    _set_setup(**fields)


# ----------------------------------------------------------------------------
# 下载：带进度、可取消、失败重试
# ----------------------------------------------------------------------------
def _human_size(n):
    """把字节数格式化为可读大小。"""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f GB" % n


def download_file(url, dest, base_done=0, base_total=0, retries=2):
    """下载单个文件到 dest，期间回报进度；支持取消。失败按 retries 重试。"""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LocalAI/2.1"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                length = int(resp.headers.get("Content-Length") or 0)
                done = 0
                t0 = time.time()
                t_last = t0
                d_last = 0
                with open(dest, "wb") as f:
                    while True:
                        if _setup_cancel.is_set():
                            raise RuntimeError("已取消")
                        chunk = resp.read(262144)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        now = time.time()
                        if now - t_last >= 0.5:
                            speed = (done - d_last) / (now - t_last)
                            total = base_total or (base_done + (length or done))
                            _set_progress(_setup["stage"], _setup["message"],
                                          base_done + done, total, speed)
                            t_last, d_last = now, done
                return done
        except Exception as e:
            last = e
            if _setup_cancel.is_set() or "已取消" in str(e):
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("下载失败：%s（%s）" % (url, last))


def probe_total(url):
    """探测远程文件的总字节数；服务器不支持 Range 时退回 Content-Length。"""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "LocalAI/2.1",
            "Range": "bytes=0-0",
        })
        with urllib.request.urlopen(req, timeout=20) as r:
            cr = r.headers.get("Content-Range") or ""
            cl = r.headers.get("Content-Length") or ""
        if "/" in cr:
            tail = cr.split("/")[-1].strip()
            if tail.isdigit():
                return int(tail)
        if cl.isdigit():
            return int(cl)
    except Exception:
        pass
    return None


def supports_range(url):
    """探测服务器是否真的支持 Range 分段（返回 206 且带 Content-Range）。

    若服务器忽略 Range 返回 200，多连接分段会各自从 0 读到分片长度，
    合并后得到的是“大小正确、内容错乱”的坏文件；必须先判断再决定策略。
    """
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "LocalAI/2.1",
            "Range": "bytes=0-1023",
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            return (getattr(r, "status", r.getcode()) == 206
                    and bool(r.headers.get("Content-Range")))
    except Exception:
        return False


def probe_speed(url, budget=2.5, sample=512 * 1024):
    """对单个下载源做小样本测速，返回字节/秒（失败返回 0）。"""
    n = 0
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "LocalAI/2.1",
            "Range": "bytes=0-%d" % (sample - 1),
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            while n < sample:
                if time.time() - t0 > budget:
                    break
                chunk = r.read(65536)
                if not chunk:
                    break
                n += len(chunk)
    except Exception:
        return 0
    dt = time.time() - t0
    return int(n / dt) if dt > 0 else 0


def pick_source(sources, budget=2.5):
    """并行测速挑选当前网络下最快的源；顺序仍以镜像优先，但以实测速度为准。"""
    results = {}

    def probe(url):
        results[url] = probe_speed(url, budget)

    ths = []
    for u in sources:
        t = threading.Thread(target=probe, args=(u,), daemon=True)
        t.start()
        ths.append(t)
    for t in ths:
        t.join()
    best = max(sources, key=lambda u: results.get(u, 0))
    return best, results.get(best, 0), results


def verify_sha256(path, expected, chunk=1 << 20):
    """校验文件 SHA256 是否与官方一致（大文件按 1MB 分块读，避免占内存）。"""
    if not expected or not os.path.isfile(path):
        return False
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                b = f.read(chunk)
                if not b:
                    break
                h.update(b)
        return h.hexdigest().lower() == expected.lower()
    except Exception:
        return False


def download_parallel(url, dest, total=None, base_done=0, base_total=0, threads=8, retries=2):
    """多连接分段下载：把文件切成若干区间并发拉取，最后合并为完整文件。

    很多站点对“单连接整文件下载”限速（几十 KB/s），但允许分段并发；
    因此默认 8 连接分段下载，可把速度提升数倍。若服务器不支持 Range、
    或文件较小时，自动退化为单流下载。
    """
    if total is None:
        total = probe_total(url)
    if not total or total < 2 * 1024 * 1024:
        return download_file(url, dest, base_done, base_total, retries=retries)
    if not supports_range(url):
        # 源不支持 Range：分段下载会产出损坏文件，退回单流下载
        return download_file(url, dest, base_done, base_total, retries=retries)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    threads = max(1, min(int(threads), 8))
    seg = (total + threads - 1) // threads
    parts = [dest + ".part%d" % i for i in range(threads)]
    spans = []
    for idx in range(threads):
        start = idx * seg
        end = min(total - 1, start + seg - 1)
        spans.append((start, end, end - start + 1))
    # 断点续传：分片大小与本次 target 绑定，若上次的 total/分片方案不同则丢弃
    marker = dest + ".partinfo"
    try:
        if os.path.exists(marker):
            with open(marker, "r", encoding="utf-8") as f:
                info = json.load(f)
            if info.get("total") != total or info.get("threads") != threads:
                for p in parts:
                    try:
                        os.remove(p)
                    except Exception:
                        pass
        with open(marker, "w", encoding="utf-8") as f:
            json.dump({"total": total, "threads": threads}, f)
    except Exception:
        pass
    errors = []

    def worker(idx):
        start, end, need = spans[idx]
        part = parts[idx]
        attempt = 0
        while attempt <= retries:
            if _setup_cancel.is_set():
                return
            try:
                have = os.path.getsize(part) if os.path.exists(part) else 0
                if have >= need:
                    return
                # 从已下载处继续，避免中断后整段重下
                req = urllib.request.Request(url, headers={
                    "User-Agent": "LocalAI/2.1",
                    "Range": "bytes=%d-%d" % (start + have, end),
                })
                with urllib.request.urlopen(req, timeout=30) as r:
                    if getattr(r, "status", r.getcode()) != 206:
                        raise RuntimeError("源未返回分段内容（非 206）")
                    with open(part, "ab" if have else "wb") as f:
                        while True:
                            if _setup_cancel.is_set():
                                return
                            chunk = r.read(131072)
                            if not chunk:
                                break
                            f.write(chunk)
                            if f.tell() >= need:
                                break
                if os.path.getsize(part) >= need:
                    return
            except Exception as e:
                errors.append(str(e))
            attempt += 1
            # 保留已下载的部分，下次从断点继续
            if attempt <= retries:
                time.sleep(1.2 * attempt)

    ths = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(threads)]
    for t in ths:
        t.start()
    t_last = time.time()
    d_last = 0
    while any(t.is_alive() for t in ths):
        time.sleep(0.5)
        done = 0
        for p in parts:
            try:
                done += os.path.getsize(p)
            except Exception:
                pass
        now = time.time()
        if now - t_last >= 0.5:
            speed = (done - d_last) / (now - t_last)
            _set_progress(_setup["stage"], _setup["message"],
                          base_done + min(done, total), base_total or total, speed)
            t_last, d_last = now, done
    for t in ths:
        t.join()
    if _setup_cancel.is_set():
        # 保留已下载分片，方便下次续传
        raise RuntimeError("已取消")
    got = 0
    for p in parts:
        try:
            got += os.path.getsize(p)
        except Exception:
            pass
    if got < total:
        detail = errors[-1] if errors else "网络中断"
        raise RuntimeError(
            "下载中断（已获取 %s / %s），点「重试」会从中断处继续，不会从头再来；%s"
            % (_human_size(got), _human_size(total), detail))
    with open(dest, "wb") as out:
        for p in parts:
            with open(p, "rb") as f:
                shutil.copyfileobj(f, out)
            try:
                os.remove(p)
            except Exception:
                pass
    try:
        if os.path.exists(marker):
            os.remove(marker)
    except Exception:
        pass
    _set_progress(_setup["stage"], _setup["message"], base_done + total, base_total or total, 0)
    return total


# ----------------------------------------------------------------------------
# 部署第一步：下载并解压 Ollama 运行环境
# ----------------------------------------------------------------------------
def install_env():
    """下载 Ollama（Windows x64）压缩包并解压到安装目录。

    下载前先对各个源并行测速，取当前网络下最快的一个；下载本身走多连接
    分段并发，避免被单连接限速拖成“卡住不动”的假象。
    """
    os.makedirs(tmp_dir(), exist_ok=True)
    zpath = os.path.join(tmp_dir(), "ollama-windows-amd64.zip")
    free_gb = free_space_gb()
    if 0 <= free_gb < 5.0:
        raise RuntimeError(
            "磁盘空间不足：下载并解压运行环境需要约 5 GB，当前只剩 %.1f GB。"
            "请清理磁盘后再试。" % free_gb)
    _set_progress("env", "正在测速并选择最快的下载源…", 0, 0, 0)
    src, speed, results = pick_source(ENV_SOURCES, budget=2.5)
    best_kb = int(speed / 1024) if speed else 0
    if speed <= 0:
        raise RuntimeError("所有下载源当前均不可达，请检查网络后点「开始部署」重试")
    host = urllib.parse.urlparse(src).hostname or src
    total = probe_total(src)
    if os.path.isfile(zpath) and total and os.path.getsize(zpath) == total:
        _set_progress("env", "已存在完整安装包，直接解压…", total, total, 0)
        speed = 0
    else:
        msg = "正在下载运行环境（Ollama，%s）— 源：%s（%d KB/s）" % (
            _human_size(total) if total else "大小未知", host, best_kb)
        _set_progress("env", msg, 0, total or 0, speed)
        try:
            download_parallel(src, zpath, total=total, threads=8)
        except Exception as e:
            raise RuntimeError("运行环境下载失败（%s）。可点「开始部署」重试，"
                               "或手动安装 Ollama 后重启本软件。" % e)
    _set_progress("env", "正在解压运行环境…")
    target = env_dir()
    os.makedirs(target, exist_ok=True)
    with zipfile.ZipFile(zpath) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        all_n = float(len(names) or 1)
        for i, name in enumerate(names, start=1):
            if _setup_cancel.is_set():
                raise RuntimeError("已取消")
            z.extract(name, target)
            if i % 40 == 0 or i == len(names):
                _set_progress("env", "正在解压运行环境（%d/%d）…" % (i, len(names)),
                              int(all_n), int(all_n), 0)
    try:
        os.remove(zpath)
    except Exception:
        pass
    if not os.path.isfile(os.path.join(target, "ollama.exe")):
        # 兼容压缩包内多一层目录的情况
        for root, _dirs, files in os.walk(target):
            if "ollama.exe" in files and os.path.abspath(root) != os.path.abspath(target):
                for f in files:
                    shutil.move(os.path.join(root, f), os.path.join(target, f))
                break
    if not os.path.isfile(os.path.join(target, "ollama.exe")):
        raise RuntimeError("运行环境解压后未找到 ollama.exe，请重试")


# ----------------------------------------------------------------------------
# 部署第二步：下载模型权重并注册为 Ollama 模型
# ----------------------------------------------------------------------------
def install_model(model_key):
    """下载所选模型的 GGUF 权重，并用 ollama create 注册到本地模型目录。"""
    meta = MODEL_CATALOG.get(model_key)
    if not meta:
        raise RuntimeError("未知模型：%s" % model_key)
    work = os.path.join(tmp_dir(), "model")
    os.makedirs(work, exist_ok=True)
    total = sum(size for _n, size in meta["files"])
    # 分段下载期间“分片临时文件 + 合并后的完整文件”会同时存在，约需 2.2 倍空间；
    # 之后注册时 ollama 还要再复制一份到 blobs，同样约 2.2 倍峰值。
    need_dl = (total * 2.2) / float(1024 ** 3)
    free_gb = free_space_gb()
    if 0 <= free_gb < need_dl:
        raise RuntimeError(
            "磁盘空间不足：下载并注册该模型需要约 %.1f GB，当前只剩 %.1f GB。"
            "请清理磁盘后再试。" % (need_dl, free_gb))
    expected_sha = meta.get("sha256")
    done_base = 0
    for fname, fsize in meta["files"]:
        dst = os.path.join(work, fname)
        if os.path.isfile(dst) and os.path.getsize(dst) == fsize:
            # 上次已下载完整：先校验哈希，坏文件不能直接拿去注册
            if expected_sha:
                _set_progress("model", "正在校验已下载文件 %s…" % fname, done_base, total, 0)
                if verify_sha256(dst, expected_sha):
                    done_base += fsize
                    continue
                try:
                    os.remove(dst)
                except Exception:
                    pass
            else:
                done_base += fsize
                continue
        for attempt in range(2):
            url = MODEL_BASE % (meta["repo"], fname)
            _set_progress("model", "正在下载模型文件 %s（%s）…" % (fname, _human_size(fsize)),
                          done_base, total, 0)
            download_parallel(url, os.path.join(work, fname), total=fsize,
                              base_done=done_base, base_total=total, threads=8)
            if not expected_sha:
                break
            _set_progress("model", "正在校验下载完整性（%s）…" % fname, done_base, total, 0)
            if verify_sha256(os.path.join(work, fname), expected_sha):
                break
            try:
                os.remove(os.path.join(work, fname))
            except Exception:
                pass
            if attempt == 1:
                raise RuntimeError(
                    "模型文件校验失败（%s）：下载内容与官方不一致，可能是网络中断导致的数据损坏。"
                    "请检查网络后点「重试」。" % fname)
        done_base += fsize
    # --- 注册前的自检：文件完整性、磁盘空间、模型目录 ---
    for fname, fsize in meta["files"]:
        p = os.path.join(work, fname)
        if not os.path.isfile(p) or os.path.getsize(p) != fsize:
            raise RuntimeError("模型文件下载不完整：%s（%s）" % (fname, _human_size(fsize)))
    # 此时模型文件已在磁盘，注册时 ollama 会再复制一份到 blobs
    need_gb = (total * 1.05) / float(1024 ** 3)
    free_gb = free_space_gb()
    if 0 <= free_gb < need_gb:
        raise RuntimeError(
            "磁盘空间不足：注册模型还需要约 %.1f GB，当前只剩 %.1f GB。"
            "请清理磁盘后点「重试」。" % (need_gb, free_gb))
    os.makedirs(models_dir(), exist_ok=True)

    _set_progress("create", "正在注册模型（首次注册需 1~3 分钟）…", total, total, 0)
    modelfile = os.path.join(work, "Modelfile")
    # 必须用完整文件名：分片 GGUF（xxx-00001-of-00002.gguf）一旦被截成 8.3 短名，
    # ollama 会报 "invalid split GGUF"。中文路径实测可正常读取。
    src_abs = os.path.join(work, meta["files"][0][0]).replace("\\", "/")
    with open(modelfile, "w", encoding="utf-8") as f:
        f.write('FROM "%s"\n' % src_abs)
        f.write('PARAMETER num_ctx 8192\n')
    exe = ollama_exe()
    if not exe or not os.path.isfile(exe):
        raise RuntimeError("运行环境未安装成功（找不到 ollama.exe）。请先完成第 1 步「运行环境」再试")
    env_create = mode_env(read_run_mode())

    def _ensure_service(force_restart=False):
        """确保推理服务就绪；force_restart 时先停掉旧进程再重新拉起。"""
        if force_restart:
            stop_service()
            time.sleep(1)
        if service_running():
            return True
        return start_service()

    if not _ensure_service():
        raise RuntimeError("推理服务未能启动，无法注册模型。详情见程序目录下的「部署错误日志.txt」")

    proc = None
    out = ""
    for attempt in (1, 2):
        if attempt == 2:
            # 第一次失败后重启服务，再试一次（常见于端口被旧进程占用）
            _ensure_service(force_restart=True)
        proc = _run_hidden(
            [exe, "create", model_key, "-f", modelfile],
            cwd=work, env=env_create,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        out = (proc.stdout or b"").decode("utf-8", "replace")
        if proc.returncode == 0:
            break

    if proc is None or proc.returncode != 0:
        rc = proc.returncode if proc is not None else "?"
        logf = deploy_log(
            "ollama create 失败（rc=%s，已重试 1 次）\n模型：%s\n命令：%s create %s -f %s\n"
            "工作目录：%s\nollama 版本：%s\nOLLAMA_MODELS=%s\nOLLAMA_HOST=%s\n"
            "服务端口可用：%s\n磁盘可用 %.1f GB\n模型文件大小：%s\n输出：\n%s"
            % (rc, model_key, exe, model_key, modelfile, work, _ollama_version(exe),
               env_create.get("OLLAMA_MODELS"), env_create.get("OLLAMA_HOST"),
               service_running(), free_gb,
               ", ".join("%s=%d" % (n, os.path.getsize(os.path.join(work, n)))
                         for n, _s in meta["files"] if os.path.isfile(os.path.join(work, n))),
               out))
        tail = out[-700:].strip().replace("\n", " ")
        low = out.lower()
        hint = ""
        if "connect" in low or "refused" in low or "dial" in low:
            hint = "（连不上推理服务：端口被占用或服务启动失败）"
        elif "space" in low or "no space" in low:
            hint = "（磁盘空间不足）"
        elif "invalid" in low or "unsupported" in low or "format" in low:
            hint = "（模型文件异常：可能下载不完整或 ollama 版本过旧）"
        elif "permission" in low or "access is denied" in low:
            hint = "（没有写入权限：请把软件装在非系统保护目录，或以管理员身份运行一次）"
        raise RuntimeError("模型注册失败%s：%s%s" % (
            hint, tail or "（无输出）",
            "；详情见 %s" % logf if logf else ""))

    # 以服务端实际结果为准（避免模型写到了别的 OLLAMA_MODELS 目录造成误判）
    if not _model_in_list(exe, env_create, model_key):
        listed = _list_models_text(exe, env_create)
        logf = deploy_log(
            "create 返回成功，但模型未出现在 ollama list 中。\n模型：%s\n"
            "OLLAMA_MODELS=%s\nlist 输出：\n%s" % (model_key, env_create.get("OLLAMA_MODELS"), listed))
        raise RuntimeError(
            "模型注册返回成功但列表里找不到它%s。请重启本软件后重试；详情见 %s"
            % ("（list：%s）" % listed.strip().replace("\n", " ")[:200] if listed else "",
               logf or "程序目录下的「部署错误日志.txt」"))
    # 注册成功后可删除临时权重，避免重复占用磁盘
    try:
        shutil.rmtree(work, ignore_errors=True)
    except Exception:
        pass
    _invalidate_state()


def _setup_worker(model_key):
    """部署线程：环境 → 模型 → 完成。"""
    global _setup_thread
    try:
        _setup_cancel.clear()
        _set_setup(model=model_key, error="", percent=0, speed=0, downloaded=0, total=0)
        if not env_ready():
            install_env()
        if _setup_cancel.is_set():
            raise RuntimeError("已取消")
        if not service_running() and not start_service():
            raise RuntimeError("运行环境未能启动（ollama serve 起不来）。请点「重试」；"
                               "若反复失败，请把程序目录下的「部署错误日志.txt」发给作者")
        install_model(model_key)
        if _has_model():
            _set_progress("done", "部署完成，可以开始对话了", 100, 100, 0)
            _set_setup(percent=100, error="")
        else:
            raise RuntimeError("模型未注册成功，请重试")
    except Exception as e:
        _set_setup(stage="error", error=str(e), message="部署中断")
    finally:
        _setup_thread = None


def start_setup(model_key):
    """启动部署线程；同一时间只允许一个部署任务。"""
    global _setup_thread
    if _setup_thread is not None and _setup_thread.is_alive():
        return False
    _setup_thread = threading.Thread(target=_setup_worker, args=(model_key,), daemon=True)
    _setup_thread.start()
    return True


def cancel_setup():
    """请求取消当前部署任务。"""
    _setup_cancel.set()
    return True


# ----------------------------------------------------------------------------
# 文档解析：把上传的各类文件抽取为纯文本，作为对话的背景知识
# ----------------------------------------------------------------------------
def _read_docx(path):
    """解析 Word(.docx)，用标准库直接读 document.xml。"""
    import xml.etree.ElementTree as ET
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    out = []
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    for para in root.iter(ns + "p"):
        texts = []
        for t in para.iter(ns + "t"):
            texts.append(t.text or "")
        line = "".join(texts)
        if line.strip():
            out.append(line)
    return "\n".join(out)


def _read_pptx(path):
    """解析 PPT(.pptx)，逐页读取文本。"""
    import xml.etree.ElementTree as ET
    a_ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    out = []
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist()
                       if re.match(r"ppt/slides/slide\d+\.xml", n))
        for i, name in enumerate(names, start=1):
            root = ET.fromstring(z.read(name))
            texts = [t.text or "" for t in root.iter(a_ns + "t")]
            body = " ".join(x for x in texts if x.strip())
            out.append("[第%d页] %s" % (i, body))
    return "\n".join(out)


def _read_xlsx(path):
    """解析 Excel(.xlsx)，逐表逐行拼接单元格。"""
    import openpyxl
    out = []
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    for ws in wb.worksheets:
        out.append("[工作表] %s" % ws.title)
        for row in ws.iter_rows(values_only=True):
            cells = ["" if c is None else str(c) for c in row]
            line = " | ".join(cells).strip()
            if line:
                out.append(line)
    wb.close()
    return "\n".join(out)


def _read_pdf(path):
    """解析 PDF，逐页抽取文本。"""
    import fitz  # PyMuPDF
    out = []
    doc = fitz.open(path)
    for i, page in enumerate(doc, start=1):
        out.append("[第%d页]" % i)
        out.append(page.get_text("text", sort=True))
    doc.close()
    return "\n".join(out)


def _read_text(path):
    for enc in ("utf-8", "gbk", "utf-16", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read(4 * 1024 * 1024)
        except Exception:
            continue
    return ""


def extract_text(name, path):
    """根据扩展名派发到对应解析器，返回 (文本, 页数信息)。"""
    ext = os.path.splitext(name)[1].lower()
    if ext == ".docx":
        return _read_docx(path), []
    if ext == ".pptx":
        return _read_pptx(path), []
    if ext == ".xlsx":
        return _read_xlsx(path), []
    if ext == ".pdf":
        return _read_pdf(path), []
    if ext in (".txt", ".md", ".csv", ".log", ".json", ".xml"):
        return _read_text(path), []
    # 未知类型：按文本兜底
    return _read_text(path), []


def handle_extract(payload):
    """处理 /api/extract：base64 文件内容 -> 抽取文本。"""
    name = payload.get("name", "upload.bin")
    b64 = payload.get("content_b64", "")
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return 400, {"error": "文件内容解码失败"}
    suffix = os.path.splitext(str(name))[1].lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix or ""):
        suffix = ".bin"
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        with open(tmp, "wb") as f:
            f.write(raw)
        text, pages = extract_text(name, tmp)
        # 超长文档只保留前 20 万字，避免一次性回传把界面和内存拖死
        if len(text) > 200000:
            text = text[:200000] + "\n\n（文档过长，已截断，仅保留前 20 万字）"
        return 200, {"text": text, "pages": pages, "count": len(text)}
    except Exception as e:
        return 500, {"error": "解析失败：%s" % e, "code": "E2101",
                     "hint": "文件可能损坏或加密，换一个文件试试"}
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass


# ----------------------------------------------------------------------------
# 本地 HTTP 服务：承载前端页面与全部 API 接口
# ----------------------------------------------------------------------------
CTYPE = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8",
}


# ----------------------------------------------------------------------------
# 环境自检 / 日志 / 打开目录
# ----------------------------------------------------------------------------
def _tail_text(path, limit=6000):
    """读取文件末尾若干字节（用于把日志回传给作者）。"""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - limit))
            return f.read().decode("utf-8", "replace")
    except Exception:
        return ""


def build_diag():
    """逐项检查运行环境，问题项附带错误码，方便用户一句话回传。"""
    items = []

    def add(name, ok, detail, code=""):
        items.append({"name": name, "ok": bool(ok), "detail": str(detail),
                      "code": code if not ok else ""})

    exe = ollama_exe()
    env_ok = bool(exe) and os.path.isfile(exe)
    add("ollama.exe", env_ok, exe if env_ok else "未找到（请先完成第 1 步部署）", "E2003")

    mdir = models_dir()
    add("模型目录", os.path.isdir(mdir), mdir if os.path.isdir(mdir) else "目录不存在", "E2004")

    tags = _api_tags_models(timeout=3)
    add("可用模型", bool(tags), "、".join(tags) if tags else "没有可用模型（请先完成部署）", "E2002")

    listen = port_open(HOST, PORT, 0.4)
    add("本地服务 21434", listen, "监听中" if listen else "未监听", "E1001")

    running = service_running()
    add("AI 推理服务 11500", running,
        "运行中" if running else "未启动（可点右上角「AI服务」开关）", "E1003")

    free = free_space_gb()
    add("磁盘剩余", free < 0 or free >= 2,
        ("%.1f GB" % free) if free >= 0 else "未知", "E3001")

    logf = os.path.join(app_dir(), "部署错误日志.txt")
    has_log = os.path.isfile(logf)
    add("部署错误日志", True, logf if has_log else "暂无错误日志（这是好事）")
    add("程序版本", True, "%s ｜ %s" % (APP_VERSION, app_dir()))

    bad = [i for i in items if not i["ok"]]
    hint = ""
    if bad:
        hint = "；".join("%s：%s" % (i["name"], i["detail"]) for i in bad)
    return {
        "ok": not bad,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "version": APP_VERSION,
        "items": items,
        "hint": hint,
        "first_code": bad[0]["code"] if bad else "",
        "log_tail": _tail_text(logf, 2000) if has_log else "",
    }


def open_target(what):
    """设置面板里的「打开日志 / 打开安装目录」。"""
    try:
        if platform.system() != "Windows":
            return {"ok": False, "error": "仅支持 Windows", "code": "E9000"}
        if what == "install_dir":
            os.startfile(app_dir())
            return {"ok": True}
        if what == "deploy_log":
            p = os.path.join(app_dir(), "部署错误日志.txt")
            if not os.path.isfile(p):
                with open(p, "w", encoding="utf-8") as f:
                    f.write("（暂无错误记录）\n")
            os.startfile(p)
            return {"ok": True}
        if what == "serve_log":
            p = os.path.join(tmp_dir(), "ollama_serve.log")
            if not os.path.isfile(p):
                return {"ok": False, "error": "暂无服务日志", "code": "E9002"}
            os.startfile(p)
            return {"ok": True}
        return {"ok": False, "error": "未知目标", "code": "E9001"}
    except Exception as e:
        return {"ok": False, "error": str(e), "code": "E9003"}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # 静默日志，避免控制台刷屏
        pass

    # ---- 统一响应 ----
    def _send(self, code, data, ctype="application/json; charset=utf-8"):
        """发送响应。data 为 bytes 时按 ctype 直出；否则 JSON 序列化。"""
        if isinstance(data, (bytes, bytearray)):
            body = bytes(data)
        else:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            ctype = "application/json; charset=utf-8"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _json_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except Exception:
            length = 0
        if length < 0 or length > 200 * 1024 * 1024:
            length = 0
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return {}

    # ---- 统一入口：所有请求都从这里进，异常统一成带错误码的 JSON ----
    def do_GET(self):
        try:
            return self._dispatch_get()
        except Exception as e:
            deploy_log("GET %s 处理失败：%s" % (self.path, e))
            try:
                return self._send(500, _api_error("E9000", "服务内部错误：%s" % e,
                                                  "请把错误码发给作者"))
            except Exception:
                pass

    def do_POST(self):
        try:
            return self._dispatch_post()
        except Exception as e:
            deploy_log("POST %s 处理失败：%s" % (self.path, e))
            try:
                return self._send(500, _api_error("E9000", "服务内部错误：%s" % e,
                                                  "请把错误码发给作者"))
            except Exception:
                pass

    # ---- GET ----
    def _dispatch_get(self):
        path = self.path.split("?", 1)[0]
        # 首页：环境与模型齐备进聊天页，否则进部署页
        if path in ("/", "/index.html"):
            page = "chat.html" if (env_ready() and _has_model()) else "setup.html"
            return self._serve_file(os.path.join(web_dir(), page))
        if path in ("/setup.html", "/chat.html", "/guide.html", "/splash.html", "/models.html"):
            return self._serve_file(os.path.join(web_dir(), os.path.basename(path)))
        if path == "/favicon.ico":
            ico = os.path.join(web_dir(), "app.ico")
            if os.path.isfile(ico):
                return self._serve_file(ico)
            return self._send(404, {"error": "not found"}, "text/plain")
        # API：GET
        if path == "/api/catalog":
            return self._send(200, catalog_snapshot())
        if path == "/api/diag":
            return self._send(200, build_diag())
        if path == "/api/logs":
            return self._send(200, {
                "deploy": _tail_text(os.path.join(app_dir(), "部署错误日志.txt"), 6000),
                "serve": _tail_text(os.path.join(tmp_dir(), "ollama_serve.log"), 4000),
            })
        if path == "/api/ui-ready":
            # 启动页画好第一帧后调用：这里关掉 PyInstaller 原生闪屏，
            # 避免"闪屏已关、网页还没出来"的白屏窗口
            try:
                threading.Timer(0.25, splash_close).start()  # 等网页启动页淡入后再淡出闪屏，叠化过渡
            except Exception:
                splash_close()
            return self._send(200, {"ok": True})
        if path == "/api/setup/status":
            return self._send(200, setup_state())
        if path == "/api/setup/catalog":
            catalog = [{"key": k, "label": v["label"], "note": v["note"],
                        "size": sum(s for _n, s in v["files"])}
                       for k, v in MODEL_CATALOG.items()]
            return self._send(200, {"models": catalog})
        if path == "/api/env/status":
            return self._send(200, {
                "env": env_ready(),
                "ollama": ollama_exe(),
                "models": models_dir(),
                "running": service_running(),
            })
        if path == "/api/model/status":
            return self._send(200, {"has_model": _has_model(), "models_dir": models_dir()})
        if path == "/api/runmode":
            return self._send(200, {"mode": read_run_mode(), "running": service_running()})
        if path == "/api/service/status":
            return self._send(200, {"running": service_running()})
        if path == "/api/tags":
            code, text = ollama_get("/api/tags")
            if code == 200:
                return self._send(200, text.encode("utf-8"), "application/json; charset=utf-8")
            return self._send(503, {"error": "ollama 未就绪", "detail": text})
        # 静态文件
        if path.startswith("/web/") or path.startswith("/static/"):
            rel = path.split("/", 2)[-1]
            base = os.path.abspath(web_dir())
            fp = os.path.abspath(os.path.join(base, rel))
            # 只允许 web 目录内的文件，挡掉 ../ 之类的路径穿越
            if (fp == base or fp.startswith(base + os.sep)) and os.path.isfile(fp):
                return self._serve_file(fp)
        return self._send(404, {"error": "not found"})

    def _serve_file(self, fp):
        if not os.path.isfile(fp):
            return self._send(404, {"error": "file not found"})
        ext = os.path.splitext(fp)[1].lower()
        ctype = CTYPE.get(ext, "application/octet-stream")
        with open(fp, "rb") as f:
            data = f.read()
        return self._send(200, data, ctype)

    # ---- POST ----
    MAX_BODY = 200 * 1024 * 1024   # 单个请求上限 200MB（够放 ~150MB 文档的 base64）

    def _dispatch_post(self):
        path = self.path.split("?", 1)[0]
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except Exception:
            length = 0
        if length > self.MAX_BODY:
            # 超大请求直接拒绝，避免把内存吃满
            self.close_connection = True
            return self._send(413, {"error": "内容太大（超过 200MB）", "code": "E2102",
                                    "hint": "请拆分文件后再上传"})
        payload = self._json_body()
        if path == "/api/setup/start":
            model = _validate_model((payload or {}).get("model", ""))
            if not model:
                return self._send(400, _api_error("E1101", "不支持的模型",
                                                  "请从模型中心选择列表里的模型"))
            ok = start_setup(model)
            return self._send(200 if ok else 409,
                              {"ok": ok, "state": setup_state()})
        if path == "/api/setup/cancel":
            cancel_setup()
            return self._send(200, {"ok": True})
        if path == "/api/service/start":
            ok = start_service()
            return self._send(200, {"running": service_running(), "ok": ok})
        if path == "/api/service/stop":
            stop_service()
            return self._send(200, {"running": service_running(), "ok": True})
        if path == "/api/runmode":
            mode = _validate_mode((payload or {}).get("mode", ""))
            if not mode:
                return self._send(400, _api_error("E1102", "非法运行模式",
                                                  "只支持 gpu / cpu / hybrid"))
            write_run_mode(mode)
            # 重启服务以生效（若正在运行）
            was = service_running()
            if was:
                stop_service()
                time.sleep(1)
                start_service(mode)
            return self._send(200, {"mode": mode, "running": service_running()})
        if path == "/api/catalog/refresh":
            refresh_catalog(force=True)
            return self._send(200, catalog_snapshot())
        if path == "/api/open":
            return self._send(200, open_target((payload or {}).get("what", "")))
        if path == "/api/extract":
            return self._send(*handle_extract(payload))
        if path == "/api/chat-proxy":
            return self._proxy_chat(payload)
        return self._send(404, {"error": "not found"})

    def _proxy_chat(self, payload):
        """把前端发来的对话请求转发给 Ollama /api/chat，并原样流式回传。"""
        inner = (payload or {}).get("payload") or {}
        stream = bool(inner.get("stream", False))
        if not inner.get("model"):
            return self._send(400, {"error": "缺少 model", "code": "E1002",
                                    "hint": "请先在顶部选择模型"})
        if not service_running():
            return self._send(503, {"error": "本地AI服务未启动", "code": "E1003",
                                    "hint": "点右上角「AI服务」开关，或到部署页完成部署"})
        if stream:
            # 关键：声明 Transfer-Encoding: chunked 后，正文必须按 HTTP/1.1 分块格式
            # 写出（长度行 + CRLF + 数据 + CRLF，最后 0\r\n\r\n 结束）。旧代码把
            # NDJSON 原样写出，浏览器会判为非法分块（ERR_INVALID_CHUNKED_ENCODING），
            # fetch 直接失败，界面显示"出错了：Failed to fetch"。
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                for chunk in ollama_stream("/api/chat", inner):
                    if not chunk:
                        continue
                    self.wfile.write(b"%x\r\n" % len(chunk))
                    self.wfile.write(chunk)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
            except Exception as e:
                # 上游中断：把原因作为一行 NDJSON 发给前端，再正常结束分块
                try:
                    msg = json.dumps({"error": "对话中断：%s" % e},
                                     ensure_ascii=False).encode("utf-8") + b"\n"
                    self.wfile.write(b"%x\r\n" % len(msg))
                    self.wfile.write(msg)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                except Exception:
                    pass
            try:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except Exception:
                pass
            return
        try:
            code, text = ollama_post_json("/api/chat", inner)
            return self._send(code or 200, text.encode("utf-8"),
                              "application/json; charset=utf-8")
        except Exception as e:
            return self._send(500, {"error": "对话失败：%s" % e, "code": "E5001",
                                    "hint": "打开「设置 → 查看部署日志」把最后一段发给作者"})


# ----------------------------------------------------------------------------
# 启动入口
# ----------------------------------------------------------------------------
def start_server():
    global _server
    _server = ThreadingHTTPServer((HOST, PORT), Handler)
    t = threading.Thread(target=_server.serve_forever, daemon=True)
    t.start()
    return _server


def wait_server(timeout=10):
    for _ in range(int(timeout * 10)):
        if port_open(HOST, PORT, timeout=0.3):
            return True
        time.sleep(0.1)
    return False


def self_service_alive():
    """本机 21434 端口上跑的确实是本程序（而不是残留僵尸端口）。

    只有确认它真的能响应 /api/setup/status，才复用它的服务；
    否则页面会报 "network error 请确认本地AI服务已启动"。
    """
    try:
        req = urllib.request.Request("http://%s:%d/api/setup/status" % (HOST, PORT),
                                     headers={"User-Agent": "LocalAI/2.1"})
        with urllib.request.urlopen(req, timeout=3) as r:
            data = r.read().decode("utf-8", "replace")
            return getattr(r, "status", r.getcode()) == 200 and '"stage"' in data
    except Exception:
        return False


def _confirm_quit():
    """部署进行中关闭窗口时二次确认；返回 True 表示允许退出。"""
    try:
        if not setup_state().get("busy"):
            return True
    except Exception:
        return True
    try:
        import ctypes
        # MB_YESNO | MB_ICONWARNING | 默认按钮为“否”
        r = ctypes.windll.user32.MessageBoxW(
            None,
            "模型正在下载/注册，现在关闭会中断部署（已下载的部分不会丢失，下次可继续）。\n\n确定要退出吗？",
            "%s %s" % (APP_NAME, APP_VERSION), 0x04 | 0x30 | 0x100)
        return r == 6
    except Exception:
        return True


def open_window(page="splash.html"):
    """打开桌面窗口：先显示启动页，由启动页判断进聊天页还是部署页。"""
    import webview
    url = "http://%s:%d/%s" % (HOST, PORT, page)
    gui = "edgechromium"
    # 窗口底色用启动页同款深蓝：页面首帧渲染前不会露出白底
    sc = _dpi_scale()
    w = int(round(1000 * sc))
    h = int(round(790 * sc))
    try:
        # 高 DPI 屏上按缩放后的尺寸会超出屏幕，这里再压到屏幕内
        import ctypes
        sw = ctypes.windll.user32.GetSystemMetrics(0)
        sh = ctypes.windll.user32.GetSystemMetrics(1)
        if sw > 0:
            w = min(w, int(sw * 0.94))
        if sh > 0:
            h = min(h, int(sh * 0.90))
    except Exception:
        pass
    window = webview.create_window(APP_NAME, url, width=w, height=h,
                                   min_size=(min(int(720 * sc), w), min(int(560 * sc), h)),
                                   background_color="#0a1730")
    try:
        window.events.closing += _confirm_quit
    except Exception:
        pass
    # 窗口一出来就把原生闪屏撤掉（稍等，避免白屏一闪）
    threading.Thread(target=_splash_close_after, args=(4.0,), daemon=True).start()
    try:
        webview.start(gui=gui)
    finally:
        splash_close()


def _boot_service():
    """后台启动 Ollama，避免把窗口/闪屏卡在启动阶段。"""
    global _owns_service
    try:
        if service_running():
            return
        _owns_service = bool(start_service())
    except Exception as e:
        deploy_log("后台启动推理服务失败：%s" % e)


def main():
    global _owns_service
    _set_dpi_aware()
    _hide_own_console()
    # 后台清一下以前版本留下的 _MEI 残留，不影响启动
    try:
        threading.Thread(target=clean_stale_mei, daemon=True).start()
    except Exception:
        pass
    splash_init()
    splash_text("正在初始化本地服务…")
    if port_open(HOST, PORT, timeout=0.4):
        if self_service_alive():
            # 已有实例在跑且可用：复用它，只开第二个窗口，
            # 不再重复绑定端口（否则会出现 network error，且两个窗口互相杀服务）
            splash_text("正在打开窗口…")
            splash_close()
            open_window("splash.html")
            return
        # 端口被僵尸进程占着但已无响应：结束它再自己起服务
        _kill_port_owner(PORT)
        time.sleep(1)

    splash_text("正在启动本地服务…")
    start_server()
    wait_server()
    splash_text("正在检查运行环境…")
    # 服务改为后台启动：窗口可以立刻显示，启动页负责等待服务就绪
    threading.Thread(target=_boot_service, daemon=True).start()
    splash_text("正在打开界面…")
    try:
        open_window("splash.html")
    finally:
        splash_close()
        # 只有“本进程拉起的服务”才在退出时停止，避免关掉窗口把另一窗口的模型服务也杀掉
        if _owns_service:
            try:
                stop_service()
            except Exception:
                pass
        try:
            if _server is not None:
                _server.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
