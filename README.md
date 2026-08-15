# 文明六 Steam 好友状态外显（CiviPresence）

让 Steam 好友列表里不只显示「正在游玩 文明六」，而是显示你当前的详细游戏状态，例如：

```
文明六 | 风云变幻 · 王子 · 第142回合 · 远古时代 · 采矿业
```

## 工作原理

文明六的 mod（Lua）环境**没有 Steam API**，且沙箱禁用了 `io`/`os`（无法直接写文件）。所以采用「mod 采集 + 外部工具上报」的两段式方案：

```
┌──────────────────────────┐   print 输出到 Lua.log    ┌───────────────────────┐
│  文明六 mod（Lua）        │ ────────────────────────▶ │ Lua.log                │
│  采集：规则集/难度/回合/   │  CIVI_PRESENCE_DATA::...  │  （游戏日志文件）        │
│  时代/科技/市政/奇观/战争/  │                          │                        │
│  伟人进度                │                          └───────────┬───────────┘
└──────────────────────────┘                                      │ 每 5 秒读尾部
                                                                  ▼
                                                 ┌───────────────────────┐
                                                 │  外部工具（Python）      │
                                                 │  ctypes 调用            │
                                                 │  steam_api64.dll       │
                                                 │  SetRichPresence()     │
                                                 └───────────┬───────────┘
                                                             ▼
                                                    Steam 好友列表显示状态
```

## 目录结构

```
civ6-steam-presence/
├── mod/
│   ├── CiviPresence.modinfo      # 文明六 mod 描述文件
│   └── Lua/
│       ├── CiviPresence.lua      # 游戏内采集脚本（print 到 Lua.log）
│       └── CiviPresence.xml      # UI 上下文定义
└── tool/
    ├── civi_presence.py          # 外部工具（Python，解析 Lua.log 并设 Steam 状态）
    └── steam_appid.txt           # 文明六 AppID = 289070
```

## 安装与使用

### 1. 安装 mod

把整个 `mod/` 文件夹重命名为 `CiviPresence`，复制到：

```
%USERPROFILE%\Documents\My Games\Sid Meier's Civilization VI\Mods\CiviPresence\
```

（若系统「文档」目录被重定向，请使用实际的「我的文档」路径。）

启动游戏后在「额外内容 → 模组」里勾选启用，然后正常开一局。

> 注意：这个 mod 只负责把状态 print 到 Lua.log，**它本身不联网、不改 Steam 状态**。

### 2. 准备外部工具

需要 Python 3.7+（Windows），无需任何 pip 包。

还需要 `steam_api64.dll`（**本仓库不包含，需自行复制**）。二选一：

- **推荐**：从文明六安装目录复制到 `tool/` 下：
  ```
  <文明六安装目录>\Base\Binaries\Win64Steam\steam_api64.dll
  ```
  例如 Steam 版通常在 `SteamLibrary\steamapps\common\Sid Meier's Civilization VI\Base\Binaries\Win64Steam\`。
- 或从 Steamworks SDK 获取（Steam 客户端内可免费下载）。

工具启动时会自动在 Steam 库目录里搜索该 dll，找不到才需要手动复制。

### 3. 运行

1. 启动 **Steam** 并登录。
2. 先运行外部工具（保持运行）：
   ```
   cd tool
   python civi_presence.py
   ```
3. 启动文明六，进入对局。
4. 工具会每 5 秒解析一次 Lua.log 尾部并更新 Steam 状态。
5. 退出文明六后，工具会自动清空状态。

## 显示效果说明

- `steam_display`：好友列表主显示。Steam 对它的处理是——值为 `#token` 时按游戏后台配置的本地化文本渲染，否则（较新客户端）直接显示原始文本。**如果好友列表不显示**，可以在「查看游戏信息」里看到状态（`status` 键），这是 Steam 客户端机制决定的，mod 无法绕过。
- 状态文本上限 **256 字节**（Steam 硬性限制，中文约 85 字），工具会自动截断。

## 已知限制

1. **必须配合外部工具**：mod 无法单独完成，Steam 状态必须由外部进程设置。
2. **需要 Steam 运行并登录**，否则 `SteamAPI_Init` 失败。
3. **不能通过创意工坊单独分发**：创意工坊只能分发 mod（采集部分），外部工具需要单独打包。二者必须同时使用才有效果。
4. **`steam_display` 显示原始文本的兼容性**：不同 Steam 客户端版本行为可能不同，已同时设置 `status` 键作为兜底。
5. **换行不支持**：Steam 好友状态是单行文本，无法多行显示。

## 调试

进入对局后，查看游戏的 Lua 日志：

```
%LOCALAPPDATA%\Firaxis Games\Sid Meier's Civilization VI\Logs\Lua.log
```

搜索 `CIVI_PRESENCE_DATA`，每刷新一次会有一行 `RULESET=..||DIFFICULTY=..||TURN=..||ERA=..||...`：

- 若某字段为空，说明对应 API 需要微调；
- 若只有 `STATE=nogame`，说明还没进对局或没识别到本地玩家；
- 若看到 `STATE=error||MSG=...`，把错误内容反馈给开发者即可。

完整修改记录见 [CHANGELOG.md](CHANGELOG.md)。
