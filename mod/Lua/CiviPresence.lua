-- ============================================================================
-- CiviPresence.lua —— 文明六 Steam 好友状态外显（UI 上下文版）
--
-- 文明六 Lua 沙箱禁用了 io / os 库，无法直接写文件。
-- 因此本脚本把采集到的状态通过 print 输出到 Lua.log，
-- 由外部工具（tool/civi_presence.py）解析 Lua.log 后设置 Steam Rich Presence。
--
-- 输出格式（每刷新一次打印一行）：
--   CIVI_PRESENCE_DATA::RULESET=..||DIFFICULTY=..||TURN=..||ERA=..||TECH=..||CIVIC=..||WONDER=..||ATWAR=..||GP=..
--   （未进入对局时：CIVI_PRESENCE_DATA::STATE=nogame）
-- ============================================================================

print("CiviPresence: script loaded (UI)")

-- 安全调用：任何 API 报错都返回默认值，绝不中断整个脚本
local function Safe(fn, default)
    local ok, v = pcall(fn)
    if ok and v ~= nil then
        return v
    end
    return default
end

-- 本地化查找（失败返回原 key）
local function Loc(locKey)
    if locKey == nil or locKey == "" then return "" end
    return Safe(function() return Locale.Lookup(locKey) end, tostring(locKey))
end

-- 通过 hash 反查 type（返回 nil 表示未找到）
local function TypeByHash(gameInfoTable, targetHash)
    if targetHash == nil then return nil end
    return Safe(function()
        for row in gameInfoTable() do
            if row.Hash == targetHash then return row end
        end
        return nil
    end, nil)
end

-- ---------------------------------------------------------------------------
-- 各字段采集（每个都独立 pcall 保护）
-- ---------------------------------------------------------------------------

local function GetRuleSetName()
    -- GetRuleSet() 返回规则集类型字符串（如 RULESET_EXPANSION_2），
    -- GetValue("RULESET") 在对局中会被清空，不能用。
    local rs = Safe(function() return GameConfiguration.GetRuleSet() end, "")
    if rs == nil or rs == "" then return "" end

    -- GameInfo.Rulesets 表不暴露给 Lua（文明六代码从不使用它），
    -- 因此直接用硬编码映射到显示名。
    local map = {
        ["RULESET_STANDARD"]    = "标准规则",
        ["RULESET_EXPANSION_1"] = "迭起兴衰",
        ["RULESET_EXPANSION_2"] = "风云变幻",
    }
    return map[rs] or rs
end

local function GetDifficultyName(localPlayerID)
    return Safe(function()
        local cfg = PlayerConfigurations[localPlayerID]
        if cfg == nil then return "" end
        local diffID = cfg:GetHandicapTypeID()
        if diffID == nil then return "" end
        local row = GameInfo.Difficulties[diffID]
        if row == nil then return tostring(diffID) end
        return Loc(row.Name)
    end, "")
end

local function GetTurn()
    return Safe(function() return Game.GetCurrentGameTurn() end, "")
end

local function GetEraName()
    local eraIndex = Safe(function() return Game.GetEras():GetCurrentEra() end, nil)
    if eraIndex == nil then return "" end
    local row = GameInfo.Eras[eraIndex]
    if row == nil then return tostring(eraIndex) end
    return Loc(row.Name)
end

local function GetResearchingTech(pPlayer)
    local techIndex = Safe(function() return pPlayer:GetTechs():GetResearchingTech() end, -1)
    if techIndex == nil or techIndex == -1 then return "" end
    local row = GameInfo.Technologies[techIndex]
    if row == nil then return "" end
    return Loc(row.Name)
end

local function GetProgressingCivic(pPlayer)
    local civicIndex = Safe(function() return pPlayer:GetCulture():GetProgressingCivic() end, -1)
    if civicIndex == nil or civicIndex == -1 then return "" end
    local row = GameInfo.Civics[civicIndex]
    if row == nil then return "" end
    return Loc(row.Name)
end

local function GetBuildingWonder(pPlayer)
    return Safe(function()
        local cities = pPlayer:GetCities()
        if cities == nil then return "" end
        for _, pCity in cities:Members() do
            local hash = Safe(function() return pCity:GetBuildQueue():GetCurrentProductionTypeHash() end, -1)
            if hash ~= nil and hash ~= -1 and hash ~= 0 then
                local row = TypeByHash(GameInfo.Buildings, hash)
                if row ~= nil and row.MaxPlayerInstances == 1 then
                    return Loc(row.Name)
                end
            end
        end
        return ""
    end, "")
end

local function GetAtWarList(pPlayer)
    return Safe(function()
        local names = {}
        local playerID = pPlayer:GetID()
        local diplo = pPlayer:GetDiplomacy()
        for i = 0, 63 do
            if i ~= playerID then
                local cfg = PlayerConfigurations[i]
                if cfg ~= nil and cfg:IsMajor() then
                    local atWar = Safe(function() return diplo:IsAtWarWith(i) end, false)
                    if atWar then
                        local sn = cfg:GetCivilizationShortDescription()
                        if sn ~= nil and sn ~= "" then
                            table.insert(names, sn)
                        end
                    end
                end
            end
        end
        return table.concat(names, ",")
    end, "")
end

local function GetClosestGreatPerson(pPlayer)
    return Safe(function()
        local gpPoints = pPlayer:GetGreatPeoplePoints()
        local gp = Game.GetGreatPeople()
        local bestName = ""
        local bestPct = -1

        for row in GameInfo.GreatPersonClasses() do
            local points = 0
            local cost = 0
            local classIndex = row.Index
            local classType = row.GreatPersonClassType

            pcall(function() local p = gpPoints:GetPointsTotal(classIndex); if p ~= nil then points = p end end)
            pcall(function() local c = gp:GetRecruitCost(classType); if c ~= nil and c > 0 then cost = c end end)
            if cost <= 0 then
                pcall(function() local c = gp:GetRecruitCost(classIndex); if c ~= nil and c > 0 then cost = c end end)
            end

            if cost > 0 then
                local pct = math.floor(points / cost * 100)
                if pct > bestPct then
                    bestPct = pct
                    bestName = Loc(row.Name)
                end
            end
        end

        if bestName == "" then return "" end
        return bestName .. "," .. tostring(bestPct)
    end, "")
end

-- ---------------------------------------------------------------------------
-- 输出
-- ---------------------------------------------------------------------------

local function Emit(fields)
    local parts = {}
    for _, kv in ipairs(fields) do
        local v = tostring(kv[2] or "")
        -- 去掉可能破坏解析的换行与竖线
        v = v:gsub("[\r\n]", " ")
        v = v:gsub("[|]", "/")
        table.insert(parts, kv[1] .. "=" .. v)
    end
    print("CIVI_PRESENCE_DATA::" .. table.concat(parts, "||"))
end

local function DoRefresh()
    local localPlayerID = Safe(function() return Game.GetLocalPlayer() end, -1)
    if localPlayerID == nil or localPlayerID == -1 then
        Emit({{"STATE", "nogame"}})
        return
    end

    local pPlayer = Players[localPlayerID]
    if pPlayer == nil then
        Emit({{"STATE", "noplayer"}})
        return
    end

    local ruleset    = Safe(GetRuleSetName, "")
    local difficulty = Safe(function() return GetDifficultyName(localPlayerID) end, "")
    local turn       = Safe(GetTurn, "")
    local era        = Safe(GetEraName, "")
    local tech       = Safe(function() return GetResearchingTech(pPlayer) end, "")
    local civic      = Safe(function() return GetProgressingCivic(pPlayer) end, "")
    local wonder     = Safe(function() return GetBuildingWonder(pPlayer) end, "")
    local atWar      = Safe(function() return GetAtWarList(pPlayer) end, "")
    local gp         = Safe(function() return GetClosestGreatPerson(pPlayer) end, "")

    Emit({
        {"RULESET", ruleset},
        {"DIFFICULTY", difficulty},
        {"TURN", turn},
        {"ERA", era},
        {"TECH", tech},
        {"CIVIC", civic},
        {"WONDER", wonder},
        {"ATWAR", atWar},
        {"GP", gp},
    })
end

function Refresh()
    local ok, err = pcall(DoRefresh)
    if not ok then
        print("CIVI_PRESENCE_DATA::STATE=error||MSG=" .. tostring(err):gsub("[|]", "/"))
    end
end

-- ---------------------------------------------------------------------------
-- 事件注册（UI 层事件）
-- ---------------------------------------------------------------------------
Events.LoadGameViewStateDone.Add(Refresh)
Events.LocalPlayerTurnBegin.Add(Refresh)

-- 加载时立即刷一次（未进对局会输出 STATE=nogame）
Refresh()
