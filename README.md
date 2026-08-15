# 文明六 游戏状态外显（CiviPresence）

> 把文明六游戏内的实时状态（规则集、难度、回合、时代、科技、奇观、战争、伟人……）导出给第三方程序，让它显示在好友可见的位置上（Steam 好友列表 / Discord / QQ）。

---

## ⚠️ 项目结论（2026-08-15）

**Steam 好友列表的自定义状态，第三方无法实现——这是 Steam 平台的硬性限制，不是代码问题。**

原因一句话：Steam 好友列表的「正在游玩 xxx」文本由游戏开发商（Firaxis）在 Steamworks 后台注册的本地化 token 控制，第三方传入的自定义字符串会被 Steam 直接丢弃或显示空白。

**但这个项目没有白做**：其中「游戏内状态采集」这整层是完整可用的，而且已经在真实对局里验证通过。它可以直接复用到 **Discord Rich Presence** 或 **QQ 个性签名** 等开放平台上，换掉「上报」那一段即可。

---

## TL;DR

| 问题 | 答案 |
|---|---|
| 采集游戏状态（mod 侧） | ✅ 已完成，实测可用 |
| 外部工具读状态（Python 侧） | ✅ 已完成，零依赖，实测可用 |
| 显示到 **Steam 好友列表** | ❌ 不可行（平台硬限制） |
| 显示到 **Discord** | ✅ 可行，100% 开放，推荐 |
| 显示到 **QQ 个性签名** | ✅ 可行（需协议框架，有封号风险） |

---

## 一、这个项目干了什么

采用「**mod 采集 + 外部工具上报**」的两段式架构（因为文明六的 Lua mod 环境没有 Steam API，也无法直接联网）：

```
┌──────────────────────────────┐   print 输出到日志    ┌──────────────────────┐
│ 文明六 mod（Lua，UI 上下文）  │ ───────────────────▶ │ Lua.log              │
│ 采集 9 个字段               │  CIVI_PRESENCE_DATA::  │ （游戏日志文件）       │
└──────────────────────────────┘  RULESET=..||TURN=..   └──────────┬───────────┘
                                                                   │ 每 5 秒读尾部
                                                                   ▼
                                                  ┌──────────────────────────┐
                                                  │ 外部工具（Python，零依赖） │
                                                  │ 解析日志 → 拼文本         │
                                                  │ ctypes 调 steam_api64.dll │
                                                  │ SetRichPresence()        │
                                                  └──────────┬───────────────┘
                                                             ▼
                                                ❌ Steam 好友列表不显示自定义文本
                                                （API 调用成功，但 Steam 丢弃非 token 文本）
```

**采集到的字段**（全部在真实对局中验证通过）：

| 字段 | 含义 | 示例 |
|---|---|---|
| `RULESET` | 规则集 | 风云变幻 |
| `DIFFICULTY` | 难度 | 王子 |
| `TURN` | 当前回合 | 6 |
| `ERA` | 时代 | 远古时代 |
| `TECH` | 正在研发的科技 | 采矿业 |
| `CIVIC` | 正在研究的市政 | 法典 |
| `WONDER` | 正在建造的奇观 | 巨石阵 |
| `ATWAR` | 交战的文明列表 | 亚历山大 |
| `GP` | 最接近招募的伟人 | 大将军,0 |

**输出数据格式**（在 `Lua.log` 里，每刷新一次打印一行）：

```
CiviPresence: CIVI_PRESENCE_DATA::RULESET=风云变幻||DIFFICULTY=王子||TURN=6||ERA=远古时代||TECH=采矿业||CIVIC=法典||WONDER=||ATWAR=亚历山大||GP=大将军,0
```

---

## 二、为什么 Steam 上实现不了（硬限制分析）

### 2.1 Steam Rich Presence 的机制

游戏通过 `SetRichPresence(key, value)` 上报状态，其中两个 key 最关键：

- `steam_display`：控制**好友列表**的主显示文本
- `status`：控制「查看游戏信息」对话框里的文本

**`steam_display` 的特殊规则**：它的 value 必须是形如 `#Status_Playing` 的 **localization token**，而 token 对应的本地化模板**只能由游戏开发商（Firaxis）在 Steamworks 后台注册和配置**。

### 2.2 实测发生了什么

| 步骤 | 结果 |
|---|---|
| `SteamAPI_Init()` | ✅ True（工具成功接入 Steam） |
| 获取 `ISteamFriends` 接口 | ✅ 成功（修复了 HSteamUser 硬编码问题） |
| `SetRichPresence("steam_display", "文明六 | 风云变幻 | 第6回合")` | ✅ 返回 True |
| `SetRichPresence("status", "同上")` | ✅ 返回 True |
| **好友列表实际显示** | ❌ 仍只显示「正在游玩 文明六」 |
| 「查看游戏信息」对话框 | ⚠️ `status` 文本可见，但好友列表看不到 |

**结论**：`SetRichPresence` 返回 True 只代表「调用成功、值已写入内存」，不代表 Steam 会展示。`steam_display` 收到非 token 的自定义字符串时，Steam 找不到对应 token，直接丢弃。

### 2.3 为什么绕不过去

1. **token 注册权在开发商手里**：自定义 `steam_display` 模板必须 Firaxis 在 Steamworks 后台操作，普通玩家和 mod 作者没有这个权限。
2. **DLL 注入拦截 Steam API**：技术上可行，但有 **VAC 封号风险**，不建议。
3. **「非 Steam 游戏」改名**：Steam 显示的是快捷方式的**静态名称**（`shortcuts.vdf`），不会跟随窗口标题动态刷新，且会显示成「正在玩 非 Steam 游戏：xxx」，又丑又冲突，没有实用价值。

这是 Steam 为了阻止第三方在状态栏刷广告/违规内容的**安全设计**，不是 bug，也不会为 mod 开放。

---

## 三、那能在哪里实现？（替代方案）

### 3.1 Discord Rich Presence —— 推荐，业界主流

Discord 的 Rich Presence 对第三方开发者 **100% 开放**，Steam 不给你的一切它都给：

- **完全自由**：自己去 [Discord Developer Portal](https://discord.com/developers/applications) 注册一个应用，拿到 `Client ID` 就能用，无需任何审核。
- **支持的效果**：
  - `details`（第一行）——`风云变幻 · 王子 · 第6回合`
  - `state`（第二行）——`远古时代 · 研发:采矿业 · 建造:巨石阵`
  - `large_image` / `small_image`——领袖头像、时代图标
  - `timestamps`——这一局玩了多久
  - `buttons`——「加入我的游戏」等按钮
- **对接成本极低**：现有 Lua 采集 + Python 解析**完全不用改**，只需把「上报」那段从 Steam API 换成 Discord IPC（`pypresence` 库，或纯 Python 的 named pipe 实现，约 80 行）。

### 3.2 QQ 个性签名 —— 国内场景

QQ 没有官方开放 API，但协议圈有成熟框架可以登录 QQ 号并改资料：

- **框架**：NapCat（基于 NTQQ，OneBot 11 标准，活跃维护）或 Lagrange（纯协议实现）。
- **接口**：`set_qq_profile` 的 `personal_note` 字段 = 个性签名；`set_diy_online_status` 的 `wording` = 自定义在线状态。
- **⚠️ 风险**：这些框架都是**协议逆向，非官方认可**，有封号风险；且个性签名修改有频率限制，不能像 Steam 那样 5 秒刷一次，建议 30~60 秒或仅在关键状态变化时更新。

### 3.3 方案对比

| 平台 | 开放性 | 显示效果 | 风险 | 备注 |
|---|---|---|---|---|
| Steam | ❌ 封闭 | 无法自定义 | 无 | 本项目的结论 |
| **Discord** | ✅ 全开放 | 最丰富 | 无 | **推荐** |
| QQ 个性签名 | ⚠️ 协议逆向 | 单行文字 | 封号风险 | 建议小号 |

---

## 四、可复用的部分：状态采集层

「采集 → 输出到 Lua.log → Python 解析」这整层是**平台无关**的，任何下游程序都可以消费同一份数据。

### 4.1 运行采集层（可选，供复用时参考）

1. **安装 mod**：把 `mod/` 文件夹重命名为 `CiviPresence`，复制到：
   ```
   %USERPROFILE%\Documents\My Games\Sid Meier's Civilization VI\Mods\CiviPresence\
   ```
   （若「文档」目录被重定向，用实际的「我的文档」路径，例如 `D:\Documents\...`）

2. 游戏内「额外内容 → 模组」勾选启用，开一局。

3. mod 会把状态 print 到日志（无需外部工具也生效）：
   ```
   %LOCALAPPDATA%\Firaxis Games\Sid Meier's Civilization VI\Logs\Lua.log
   ```

4. 搜索 `CIVI_PRESENCE_DATA` 即可看到状态行。**至此，状态数据已经导出成功**，接什么平台都行。

### 4.2 Python 解析（同样平台无关）

`tool/civi_presence.py` 里的 `parse_lua_log()` 与 `build_display()` 已经完成了「读日志尾部 → 解析字段 → 拼文本」的全部逻辑，复用时直接调用这两个函数即可，把 `build_display()` 的产物喂给任意下游（Discord IPC / QQ API）。

---

## 五、目录结构

```
civ6-steam-presence/
├── mod/
│   ├── CiviPresence.modinfo      # mod 描述（含 CompatibleVersions 等修复）
│   └── Lua/
│       ├── CiviPresence.lua      # 采集脚本（print 到 Lua.log）
│       └── CiviPresence.xml      # UI 上下文定义
├── tool/
│   ├── civi_presence.py          # 外部工具（解析日志 + ctypes 上报 Steam）
│   └── steam_appid.txt           # 文明六 AppID = 289070（纯 ASCII，无 BOM）
├── CHANGELOG.md                  # 完整修改记录（含全部踩坑根因）
├── README.md                     # 本文件
└── .gitignore
```

> 注：`steam_api64.dll` 是版权文件，仓库不包含，需自行从游戏目录复制（见 CHANGELOG v1.1）。

---

## 六、关键踩坑记录（速查）

| # | 坑 | 根因 | 修复 |
|---|---|---|---|
| 1 | mod 在「额外内容」不显示 | modinfo 缺 `CompatibleVersions`，被判定不兼容 | 补 `1.2,2.0` + `AffectsSavedGames` |
| 2 | Lua 脚本没加载 | 缺 `ImportFiles` / `Files` 节点 | 补上 |
| 3 | `io` 为 nil | 文明六 Lua 沙箱禁用 io/os（UI 与 Gameplay 层都禁） | 改走 `print` → Lua.log 通道 |
| 4 | `SteamAPI_Init` 失败 | `steam_appid.txt` 带 UTF-8 BOM | 重写为纯 ASCII |
| 5 | 拿不到 ISteamFriends | `HSteamUser` 硬编码 0，本机实为 1 | 用 `SteamAPI_GetHSteamUser()` |
| 6 | Python 解析不到数据 | 文明六给 print 加「脚本名: 」前缀，startswith 失效 | 改用 `find` 定位标记 |

完整根因与证据见 [CHANGELOG.md](CHANGELOG.md)。

---

## 七、完整历程

从「mod 不显示」到「Steam 硬限制」，一路踩坑修复的完整时间线，见 [CHANGELOG.md](CHANGELOG.md)。最终结论：**采集层可用，Steam 显示层不可行，转 Discord / QQ。**
