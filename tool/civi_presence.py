#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CiviPresence 外部工具
=====================
读取文明六 mod（Lua/CiviPresence.lua）写出的状态文件，
通过 ctypes 直接调用 steam_api64.dll 设置 Steam Rich Presence。

零第三方依赖，只需 Python 3.7+ 和 steam_api64.dll（文明六自带）。

用法：
    1. 把本目录的 steam_appid.txt（内容 289070）和 steam_api64.dll 放在一起。
    2. 启动 Steam 并登录。
    3. 先启动本工具，再启动文明六进入对局。
    4. 退出文明六后，本工具会自动清空状态并退出。

说明：
    - steam_api64.dll 可从文明六安装目录复制：
        Steam\\steamapps\\common\\Sid Meier's Civilization VI\\steam_api64.dll
    - 或者从 Steamworks SDK 获取（Steam 客户端免费下载）。
    - 脚本会尝试自动定位该 dll，找不到时请手动放到本目录。
"""

import ctypes
import os
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
APPID = 289070                     # 文明六 Steam AppID
REFRESH_INTERVAL = 5.0            # 状态刷新间隔（秒）
SHOW_DETAILS = True               # 是否在状态里附带 时代/科技/奇观/战争/伟人 等细节

# Rich Presence 的显示 key。
#   steam_display : 好友列表主显示（部分 Steam 客户端会直接显示非 token 文本）
#   status        : "查看游戏信息" 对话框里显示（这个最稳，一定显示）
RICH_PRESENCE_KEYS = ["steam_display", "status"]

# Rich Presence 单条 value 上限：256 字节（UTF-8），中文每字 3 字节。
MAX_VALUE_BYTES = 256

# 文明六进程名（用于检测游戏是否退出）
CIV6_PROCESS_NAMES = ["CivilizationVI.exe", "CivilizationVI_DX12.exe", "CivilizationVI_Exe"]


# ---------------------------------------------------------------------------
# 路径定位
# ---------------------------------------------------------------------------

def script_dir():
    return os.path.dirname(os.path.abspath(__file__))


def get_lua_log_path():
    """返回文明六 Lua.log 路径（mod 通过 print 把状态写到这个日志里）。"""
    localappdata = os.environ.get("LOCALAPPDATA") or ""
    username = os.environ.get("USERNAME") or "Administrator"
    sub = os.path.join("Firaxis Games", "Sid Meier's Civilization VI", "Logs", "Lua.log")
    candidates = []
    if localappdata:
        candidates.append(os.path.join(localappdata, sub))
    candidates.append(os.path.join(
        "C:" + os.sep + "Users", username, "AppData", "Local",
        "Firaxis Games", "Sid Meier's Civilization VI", "Logs", "Lua.log",
    ))
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return os.path.join(localappdata, sub) if localappdata else "Lua.log"


def _steam_install_path_from_registry():
    """从注册表读取 Steam 安装路径。"""
    try:
        import winreg
    except ImportError:
        return None
    keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam"),
    ]
    for hive, subkey in keys:
        try:
            with winreg.OpenKey(hive, subkey) as k:
                val, _ = winreg.QueryValueEx(k, "InstallPath")
                if val:
                    return val
        except OSError:
            continue
    return None


def _civ6_game_roots():
    """返回所有可能的文明六安装根目录。"""
    roots = []
    steam_dir = _steam_install_path_from_registry()
    if steam_dir:
        roots.append(os.path.join(
            steam_dir, "steamapps", "common", "Sid Meier's Civilization VI",
        ))
    # 扫描所有盘符下常见的 Steam / SteamLibrary 目录
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        for lib in ("Steam", "SteamLibrary"):
            base = "%s:\\%s\\steamapps\\common\\Sid Meier's Civilization VI" % (letter, lib)
            if os.path.isdir(base):
                roots.append(base)
    return roots


def find_steam_api_dll():
    """按优先级查找 steam_api64.dll。"""
    candidates = []

    # 1. 本脚本目录（手动复制到 tool/ 下最优先）
    candidates.append(os.path.join(script_dir(), "steam_api64.dll"))

    # 2. 环境变量
    env = os.environ.get("STEAM_API64_DLL")
    if env:
        candidates.append(env)

    # 3. 文明六安装目录下的常见相对位置
    #    （游戏主程序的 dll 在 Base/Binaries/Win64Steam 下，不是游戏根目录）
    rel_paths = [
        os.path.join("Base", "Binaries", "Win64Steam", "steam_api64.dll"),
        "steam_api64.dll",
    ]
    for gr in _civ6_game_roots():
        for rel in rel_paths:
            candidates.append(os.path.join(gr, rel))

    for p in candidates:
        if p and os.path.exists(p):
            return p

    # 4. 系统 PATH（最后尝试）
    try:
        return ctypes.CDLL("steam_api64.dll")._name  # 成功则返回
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Steam API（ctypes）
# ---------------------------------------------------------------------------

def setup_steam_api(dll_path):
    """加载 steam_api64.dll 并配置函数原型。"""
    steam = ctypes.CDLL(dll_path)

    steam.SteamAPI_Init.restype = ctypes.c_bool
    steam.SteamAPI_Init.argtypes = []

    steam.SteamAPI_Shutdown.restype = None
    steam.SteamAPI_Shutdown.argtypes = []

    steam.SteamAPI_RunCallbacks.restype = None
    steam.SteamAPI_RunCallbacks.argtypes = []

    steam.SteamAPI_GetHSteamUser.restype = ctypes.c_int
    steam.SteamAPI_GetHSteamUser.argtypes = []

    steam.SteamInternal_FindOrCreateUserInterface.restype = ctypes.c_void_p
    steam.SteamInternal_FindOrCreateUserInterface.argtypes = [ctypes.c_int, ctypes.c_char_p]

    return steam


def get_friends_interface(steam):
    """获取 ISteamFriends 接口指针，尝试多个接口版本。"""
    # 关键：HSteamUser 必须用 SteamAPI_GetHSteamUser() 的返回值，
    # 不能硬编码 0（实测本机返回 1，传 0 会拿不到任何接口）。
    huser = steam.SteamAPI_GetHSteamUser()
    versions = [
        b"SteamFriends018",
        b"SteamFriends017",
        b"SteamFriends016",
        b"SteamFriends015",
        b"SteamFriends014",
    ]
    for v in versions:
        ptr = steam.SteamInternal_FindOrCreateUserInterface(huser, v)
        if ptr:
            return ptr
    return None


def make_set_rich_presence(steam, friends_ptr):
    """
    返回一个 set_rich_presence(key, value) 可调用对象。
    优先使用扁平导出函数 SteamAPI_ISteamFriends_SetRichPresence；
    不存在时回退到 vtable 调用（SetRichPresence 在 vtable 索引 43）。
    """
    flat = getattr(steam, "SteamAPI_ISteamFriends_SetRichPresence", None)
    if flat is not None:
        flat.restype = ctypes.c_bool
        flat.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]

        def set_rp(key, value):
            return bool(flat(friends_ptr, key.encode("utf-8"), value.encode("utf-8")))

        return set_rp

    # vtable 兜底
    SET_RICH_PRESENCE_INDEX = 43

    def set_rp(key, value):
        vtable = ctypes.cast(friends_ptr, ctypes.POINTER(ctypes.c_void_p)).contents
        func_addr = vtable[SET_RICH_PRESENCE_INDEX]
        proto = ctypes.CFUNCTYPE(
            ctypes.c_bool,
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p,
        )
        func = proto(func_addr)
        return bool(func(friends_ptr, key.encode("utf-8"), value.encode("utf-8")))

    return set_rp


# ---------------------------------------------------------------------------
# 状态解析与拼接
# ---------------------------------------------------------------------------

def parse_lua_log(path):
    """
    从 Lua.log 里解析 mod 输出的最新状态。
    mod 每刷新一次会 print 一行：
        CIVI_PRESENCE_DATA::RULESET=..||DIFFICULTY=..||TURN=..||...
    我们只取文件尾部最后一条这样的行。
    """
    data = {}
    try:
        fsize = os.path.getsize(path)
    except OSError:
        return data

    try:
        # 只读尾部最多 256KB，避免日志很大时全量读
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            if fsize > 256 * 1024:
                f.seek(fsize - 256 * 1024)
            else:
                f.seek(0)
            tail = f.read()
    except OSError:
        return data

    # 注意：文明六会在 Lua 的 print 输出前加 "脚本名: " 前缀，
    # 所以日志行实际是 "CiviPresence: CIVI_PRESENCE_DATA::..."，
    # 不能 startswith 匹配，要用 find 定位标记。
    target = None
    marker = "CIVI_PRESENCE_DATA::"
    for line in tail.splitlines():
        idx = line.find(marker)
        if idx != -1:
            target = line[idx + len(marker):]
    if target is None:
        return data

    for kv in target.split("||"):
        if "=" in kv:
            k, _, v = kv.partition("=")
            data[k.strip()] = v.strip()
    return data


def truncate_bytes(s, limit):
    """按 UTF-8 字节数截断字符串，保证不切断一个多字节字符。"""
    b = s.encode("utf-8")
    if len(b) <= limit:
        return s
    cut = b[:limit]
    return cut.decode("utf-8", errors="ignore").rstrip()


def build_display(data):
    """把 key=value 状态拼成单行显示文本。"""
    ruleset = data.get("RULESET", "").strip()
    diff = data.get("DIFFICULTY", "").strip()
    turn = data.get("TURN", "").strip()

    parts = ["文明六"]
    if ruleset:
        parts.append(ruleset)
    if diff:
        parts.append(diff)
    if turn:
        parts.append("(第%s回合)" % turn)

    head = " | ".join(parts)

    detail = []
    if SHOW_DETAILS:
        era = data.get("ERA", "").strip()
        tech = data.get("TECH", "").strip()
        civic = data.get("CIVIC", "").strip()
        wonder = data.get("WONDER", "").strip()
        atwar = data.get("ATWAR", "").strip()
        gp = data.get("GP", "").strip()

        if era:
            detail.append(era)
        if tech:
            detail.append("研发:" + tech)
        if civic:
            detail.append("市政:" + civic)
        if wonder:
            detail.append("建造:" + wonder)
        if atwar:
            detail.append("战争:" + atwar)
        if gp:
            detail.append("伟人:" + gp.replace(",", " "))

    result = head
    if detail:
        result = head + " · " + " · ".join(detail)

    return truncate_bytes(result, MAX_VALUE_BYTES)


# ---------------------------------------------------------------------------
# 进程检测
# ---------------------------------------------------------------------------

def is_civ6_running():
    """检测文明六进程是否在运行。检测失败时返回 True（保守，不误清状态）。"""
    try:
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, timeout=10,
        )
        if out.returncode != 0:
            return True
        text = out.stdout.decode("gbk", errors="ignore")
        for name in CIV6_PROCESS_NAMES:
            if name in text:
                return True
        return False
    except Exception:
        return True


# ---------------------------------------------------------------------------
# 主循环
# ---------------------------------------------------------------------------

def main():
    os.chdir(script_dir())  # 让 SteamAPI_Init 能找到 steam_appid.txt

    dll_path = find_steam_api_dll()
    if dll_path is None:
        print("[错误] 找不到 steam_api64.dll。")
        print("请把文明六安装目录里的 steam_api64.dll 复制到本工具目录，")
        print("或设置环境变量 STEAM_API64_DLL 指向该文件。")
        return 1

    print("[信息] 使用 steam_api64.dll:", dll_path)

    try:
        steam = setup_steam_api(dll_path)
    except OSError as e:
        print("[错误] 加载 steam_api64.dll 失败:", e)
        print("提示：请确认该 dll 与系统位数一致（64 位）。")
        return 1

    if not steam.SteamAPI_Init():
        print("[错误] SteamAPI_Init 失败。")
        print("请确认：1) Steam 客户端已运行并登录；2) 本目录存在 steam_appid.txt（内容 289070）。")
        return 1

    friends_ptr = get_friends_interface(steam)
    if friends_ptr is None:
        print("[错误] 无法获取 ISteamFriends 接口。")
        steam.SteamAPI_Shutdown()
        return 1

    set_rich_presence = make_set_rich_presence(steam, friends_ptr)

    lua_log_path = get_lua_log_path()
    print("[信息] Lua.log:", lua_log_path)
    print("[信息] 工具已启动，进入对局后会自动更新 Steam 状态。Ctrl+C 退出。")

    last_display = None
    last_seen_game = True

    try:
        while True:
            data = parse_lua_log(lua_log_path)

            if data.get("STATE") == "error":
                print("[警告] mod 报错:", data.get("MSG", ""))

            display = build_display(data)

            game_running = is_civ6_running()

            if not game_running:
                # 游戏已退出：清空状态并结束
                if last_seen_game:
                    for key in RICH_PRESENCE_KEYS:
                        set_rich_presence(key, "")
                    print("[信息] 检测到文明六已退出，已清空 Steam 状态。")
                last_seen_game = False
                break
            else:
                last_seen_game = True
                if display != last_display:
                    ok = True
                    for key in RICH_PRESENCE_KEYS:
                        ok = set_rich_presence(key, display) and ok
                    if ok:
                        print("[更新] " + display)
                        last_display = display
                    else:
                        print("[警告] SetRichPresence 返回失败")

            steam.SteamAPI_RunCallbacks()
            time.sleep(REFRESH_INTERVAL)

    except KeyboardInterrupt:
        print("\n[信息] 手动退出，清空状态...")
        for key in RICH_PRESENCE_KEYS:
            set_rich_presence(key, "")
    finally:
        steam.SteamAPI_Shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
