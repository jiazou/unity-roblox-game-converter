using UnityEngine
// Handles loading data from the Asset Bundle to handle different themes for the game
-- Dictionary<K,V>: use Luau table {}string, ThemeData> themeDataList
    -- Dictionary<K,V>: use Luau table {}string, ThemeData> dictionnary { get { return themeDataList; } }

    local m_Loaded = false
    bool loaded { get { return m_Loaded; } }

    ThemeData GetThemeData(string type)
    {
        ThemeData list
        if (themeDataList == nil  or  not themeDataList.TryGetValue(type, out list))
            return nil
        return list
end
    local function LoadDatabase()
    {
        // If not nil the dictionary was already loaded.
        if themeDataList == nil then
            themeDataList = new -- Dictionary<K,V>: use Luau table {}string, ThemeData>()
            yield return Addressables.LoadAssetsAsync<ThemeData>("themeData", op =>
            {
                if op ~= nil then
                    if(not themeDataList.ContainsKey(op.themeName))
                        table.insert(themeDataList, op.themeName, op)
end
            })
            m_Loaded = true
endend
end