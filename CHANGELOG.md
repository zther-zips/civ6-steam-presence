# 修改记录（Changelog）

> 本文件记录「文明六 Steam 好友状态外显（CiviPresence）」项目的所有修改，按时间**倒序**排列。
> 每次改动后，请在最上方追加新条目，保持格式一致。

---

## 2026-08-15

### v2.0 —— 项目完结：整理复盘、明确结论、转公开（约 15:30）

**做了什么**
- 重写 `README.md` 为复盘版，诚实交代三件事：干了什么 / 为什么 Steam 不可行 / 能在哪里实现。
- 明确项目最终结论：**Steam 好友列表自定义状态是平台硬限制，第三方无法实现**；但「状态采集层」完整可用，可复用到 Discord / QQ。
- 补充替代方案说明（Discord Rich Presence 推荐、QQ 个性签名）。
- 仓库由私有转为公开。

**为什么 Steam 最终不可行（技术定论）**
- `SetRichPresence("steam_display", "自定义文本")` 返回 True 只代表调用成功，不代表 Steam 会显示。
- `steam_display` 的值必须是开发商（Firaxis）在 Steamworks 后台注册的 localization token（如 `#Status_Playing`），第三方传入普通字符串会被 Steam 丢弃或显示空白。
- `status` 键只在「查看游戏信息」对话框可见，好友列表主显示不显示。
- 绕过手段（DLL 注入有 VAC 风险、「非 Steam 游戏」改名是静态的）均不实用。
- 这是 Steam 阻止第三方刷广告/违规内容的安全设计，不会为 mod 开放。

**替代方案（可复用采集层）**
- **Discord Rich Presence**：100% 开放，注册应用拿 Client ID 即可，`details`/`state`/大图/计时器全支持，采集层无需改动。
- **QQ 个性签名**：NapCat / Lagrange 协议框架，`set_qq_profile` 改 `personal_note`；有封号风险，建议小号、降频。

---

### v1.10 —— 修复 Python 解析 Lua.log 失败（约 13:25）

**现象**
- Lua 端已正常 print 出 `RULESET=风云变幻||DIFFICULTY=王子||...`，但 Python 工具一直只显示兜底「文明六」，无详细状态。

**根因**
- 文明六会在 Lua 的 print 输出前自动加「脚本名: 」前缀，Lua.log 实际行是 `CiviPresence: CIVI_PRESENCE_DATA::...`。
- Python 的 `parse_lua_log` 用 `line.startswith("CIVI_PRESENCE_DATA::")` 匹配，带前缀后永远匹配不到 → 返回空 dict → 兜底显示。

**修复**
- `parse_lua_log` 改用 `line.find("CIVI_PRESENCE_DATA::")` 定位标记，取标记之后的内容解析，兼容任意前缀。

**实测**
- 解析结果：`RULESET=风云变幻, DIFFICULTY=王子, TURN=6, ERA=远古时代, TECH=采矿业, CIVIC=法典, GP=大将军,0`
- 显示文本：`文明六 | 风云变幻 | 王子 | (第6回合) · 远古时代 · 研发:采矿业 · 市政:法典 · 伟人:大将军 0`

---

### v1.6 —— 修复 Lua 脚本从未加载（缺 ImportFiles）+ 全量诊断输出（约 11:40）

**根因（有日志证据）**
- mod 在「额外内容」能显示、已勾选启用，`Mods.sqlite` 里 `CiviPresenceUI (AddUserInterfaces)` 组件也在，但 `Lua.log` 里完全没有 CiviPresence 痕迹、状态文件 `CiviPresence.txt` 从未生成 → **Lua 脚本根本没被加载**。
- 对照 workshop 成熟 UI mod（YosugaGallery / QuickDeals）：它们都同时用 `ImportFiles` 把 mod 自己的 lua/xml 导入游戏**虚拟文件系统（VFS）**，`LuaContext` 的 `FileName` 才能在运行时解析到 mod 文件。CiviPresence 只用了 `AddUserInterfaces`，缺 `ImportFiles`，`FileName="CiviPresence"` 无法命中。
- 另：xml 根元素 `<Context Name="...">` 改为无 Name 的 `<Context>`（YosugaGallery/QuickDeals 均为无 Name）；`LuaContext` 按惯例补 `Hidden="1"`。

**修复**
- `CiviPresence.modinfo` 在 `InGameActions` 新增 `ImportFiles`（导入 `Lua/CiviPresence.lua` + `Lua/CiviPresence.xml`）。
- `Lua/CiviPresence.xml` 根元素去 Name、LuaContext 加 Hidden。
- `Lua/CiviPresence.lua` 全量加 `print` 诊断（脚本加载、文件写入能力测试、每次刷新结果、错误），全部输出到 `Lua.log`，便于确认「脚本是否加载」+「io 是否可写」。
- 三处文件已同步到 `D:/workspace/civ6_steam_presence_v1.2/mod/` 与已安装目录。

**待验证（关键）**
- 文明六 Lua 沙箱**可能禁用 `io.open` 写文件**（workshop 里没有任何 mod 用 io.open）。若文件仍写不出，需改走 `print` 到 `Lua.log` 通道，由外部工具 tail 解析。

---

### v1.5 —— 修复无法获取 ISteamFriends 接口（约 11:15）

**根因**
- `get_friends_interface` 里 `SteamInternal_FindOrCreateUserInterface(0, ...)` 硬编码第一个参数（HSteamUser）为 0，但本机 `SteamAPI_GetHSteamUser()` 返回 **1**，传 0 拿不到任何接口。
  - 实测：hSteamUser=0 时 SteamFriends001~018 全部 NULL；hSteamUser=1 时全部有效。

**修复**
- `setup_steam_api` 增加 `SteamAPI_GetHSteamUser` 原型声明。
- `get_friends_interface` 改为 `huser = SteamAPI_GetHSteamUser()`，再 `FindOrCreateUserInterface(huser, ...)`；接口版本列表补上 `SteamFriends018`。

**实测**
- `SteamAPI_Init=True`，`HSteamUser=1`，`ISteamFriends=有效指针`，`SetRichPresence(status/steam_display)=True` ✅

---

### v1.4 —— 修复工具 SteamAPI_Init 失败（约 11:00）

**根因**
- `tool/steam_appid.txt` 带 UTF-8 BOM（`EF BB BF`）+ 末尾换行，Steam 要求纯 ASCII 数字，BOM 导致 `SteamAPI_Init` 解析 AppID 失败。
  - 十六进制证据：原文件 `EF BB BF 32 38 39 30 37 30 0A`（BOM + "289070" + \n）
- 修复：重写为纯 `289070`（6 字节，无 BOM 无换行）。
- 已实测：`SteamAPI_Init = True`。

**排查知识（重要）**
- `steam_appid.txt` 必须是**无 BOM 的纯 ASCII**，只写数字 AppID，不要用记事本"另存为 UTF-8"（会加 BOM）。
- 游戏运行时工具同时 init 同一 AppID（289070）是允许的（本方案设计如此，靠共享 AppID 才能把 Rich Presence 显示到好友列表）。

---

### v1.3 —— 定位 mod 不显示的真正根因（约 10:40）

**根因（有数据库证据）**
- 游戏**确实扫描并解析了** `CiviPresence.modinfo`（`Mods.sqlite` 的 `ScannedFiles` / `Mods` 表都有记录，ModId 正确，中英文文本也都解析成功），所以**不是路径问题**，本地 `Mods` 目录是对的，无需放 workshop。
- 真正原因：`CiviPresence.modinfo` 缺少 `<CompatibleVersions>` 属性 → 游戏判定「不兼容当前版本」，没有把 mod 放进 `ModGroupItems`（默认分组），因此「额外内容」界面不显示。
  - 对照：所有能显示的 workshop mod 都带 `CompatibleVersions=1.2,2.0` + `AffectsSavedGames=0`，而 CiviPresence 两者皆缺，且 `ModGroupItems` 为空。

**修复**
- `CiviPresence.modinfo` 的 `<Properties>` 新增：
  - `<AffectsSavedGames>0</AffectsSavedGames>`
  - `<CompatibleVersions>1.2,2.0</CompatibleVersions>`
- 顺带把 `AddUserInterfaces` 的 `<Context>InGame</Context>` 按官方格式包进 `<Properties>`（原为直接子元素，虽不影响显示但非标准）。

**关键排查知识（重要）**
- 文明六 mod 数据/日志实际位置在 `C:\Users\<用户>\AppData\Local\Firaxis Games\Sid Meier's Civilization VI\`（`Mods.sqlite`、`Logs\`），**不在**文档目录。
- 判断 mod 是否被游戏识别：查 `Mods.sqlite` → `Mods` 表有没有 ModId；判断是否显示：查 `ModGroupItems` 表有没有对应 ModRowId。

---

### v1.2 —— 修复 mod 不显示 + 文档路径重定向（约 10:00）

**修复**
- 修复 mod 在游戏「额外内容」里不显示的问题：
  - `CiviPresence.modinfo` 的 `<Mod id>` 去掉花括号 `{}`（文明六只认不带花括号的 GUID，带花括号会被静默跳过）
  - `AddUserInterfaces` 改为标准结构：新增 `Lua/CiviPresence.xml`（UI context），modinfo 引用 `.xml` 而非直接引用 `.lua`
- 修复文档目录重定向导致状态文件写入失败：
  - 用户「文档」被重定向到 `D:/Documents`（原代码写 `%USERPROFILE%/Documents` = 不存在的 C 盘路径）
  - `Lua/CiviPresence.lua` 与 `tool/civi_presence.py` 均改为候选目录探测，优先 `D:/Documents`，自动落到第一个可写目录

**说明**
- mod 正确安装位置：`D:/Documents/My Games/Sid Meier's Civilization VI/Mods/CiviPresence/`（**不是** Steam workshop 目录 `289070`）
- 若游戏正在运行，需完全退出后重启才会扫描到新 mod

---

### v1.1 —— 修复 steam_api64.dll 定位（约 09:42）

**修复**
- 修正外部工具 `tool/civi_presence.py` 的 `steam_api64.dll` 查找逻辑：
  - 补上游戏主程序 dll 的真实路径 `Base\Binaries\Win64Steam\steam_api64.dll`
  - 增加全盘扫描 `Steam` / `SteamLibrary` 库目录
- 实测已能自动定位到：
  `D:\SteamLibrary\steamapps\common\Sid Meier's Civilization VI\Base\Binaries\Win64Steam\steam_api64.dll`

**说明**
- 无需再手动复制 dll 到 tool 目录，脚本自动查找。

---

### v1.0 —— 项目初版（约 09:20）

**新增**
- 建立项目结构：
  - `mod/` 文明六 mod（游戏内采集状态）
  - `tool/` 外部工具（设置 Steam 状态）
  - `README.md` 使用说明
- `mod/Lua/CiviPresence.lua`：采集规则集、难度、回合、时代、科技、市政、奇观、交战文明、伟人进度，写入本地状态文件
- `mod/CiviPresence.modinfo`：mod 描述文件
- `tool/civi_presence.py`：纯 ctypes 调用 `steam_api64.dll` 的 `SetRichPresence`，零第三方依赖
- `tool/steam_appid.txt`：文明六 AppID = 289070

**关键技术结论**
- 文明六 Lua mod 环境无 Steam API，必须「mod 采集 + 外部工具上报」两段式配合
- Steam 状态文本上限 256 字节（官方 `k_cchMaxRichPresenceValueLength`）
- `SetRichPresence` 是 ISteamFriends vtable 第 43 个方法（0-based），优先用扁平导出函数 `SteamAPI_ISteamFriends_SetRichPresence`

---

### 待办 / 待验证

- [ ] 实测 mod 采集字段是否正确（尤其「时代」「伟人」两个 API）
- [ ] 验证 `steam_display` 在好友列表的实际显示效果
- [ ] 可选：接入金币 / 军事实力 / 文化 / 信仰等更多字段
- [ ] 可选：外部工具用 C++ 编译成单个 exe 便于分发

---

### v1.7 —— 修复 "Invalid file reference"（缺 Files 节点）（约 11:55）

**根因（Modding.log 明确报错）**
- `ERROR: Invalid file reference in action, did you forgot to add it in <Files>? - Lua/CiviPresence.lua`
- 文明六要求所有被 action 引用的文件必须同时列在 modinfo 的 `<Files>` 节点里；之前只写了 `AddGameplayScripts` 的 `<File>`，漏了 `<Files>` 清单 → 游戏拒绝加载该 lua。

**修复**
- modinfo 新增 `<Files>` 节点，列出 `Lua/CiviPresence.lua`（及 xml）。
- 同时（v1.6 起）已将加载方式从 `AddUserInterfaces`+`ImportFiles` 换成 `AddGameplayScripts`，事件改 `GameEvents.PlayerTurnStarted`。

### v1.8 —— 换回 UI 上下文（io/GameConfiguration 只在 UI 层可用）（约 12:05）

**现象（AddGameplayScripts 加载成功后）**
- Lua.log：`script loaded` 了，但立刻报 `attempt to index a nil value`（io 为 nil）、`function expected instead of nil`（GameConfiguration 为 nil）。
- 状态文件仍未生成。

**根因**
- 文明六的 **GameplayScripts 上下文会禁用 `io`/`os` 库，且没有 `GameConfiguration` 对象**；写文件必须走 **UI 上下文**（QuickDeals 等写文件的 mod 全在 UI 层跑）。

**修复**
- modinfo：`AddGameplayScripts` → `AddUserInterfaces`（`<Context>InGame</Context>`，只挂 xml）+ `ImportFiles`（导 lua）。
- lua：事件从 `GameEvents.PlayerTurnStarted` 改回 UI 层的 `Events.LoadGameViewStateDone` + `Events.LocalPlayerTurnBegin`。
- `<Files>` 节点保留（lua + xml）。

### v1.9 —— 换 print→Lua.log 通道（io 在 UI 层也被禁）（约 12:20）

**现象（v1.8 UI 上下文下）**
- Lua.log：`io` 仍为 nil（`attempt to index a nil value` 在 `io.open`），且 `GameInfo.RuleSets` 表名写错（应为 `Rulesets`）。

**根因**
- 文明六 Lua 沙箱在 **UI 上下文同样禁用了 `io`/`os`** —— mod 无法直接写文件。
- 但 `print` 100% 可用（Lua.log 里已有脚本的 print 输出为证）。

**新方案（已实现）**
- Lua：采集字段后 `print("CIVI_PRESENCE_DATA::K=V||...")` 单行输出；未进对局输出 `STATE=nogame`；全部字段独立 pcall 保护，单字段失败不影响整体。
- Python：改为解析 `LOCALAPPDATA\...\Logs\Lua.log` 尾部最后一条 `CIVI_PRESENCE_DATA::` 行（只读尾部 256KB）。
- 修正表名 `GameInfo.Rulesets`；时代用 `pPlayer:GetEras():GetEra()`（返回 index，`GameInfo.Eras[index]` 索引，官方代码同款写法）。
