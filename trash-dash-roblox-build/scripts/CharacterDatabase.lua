using UnityEngine
/// <summary>
/// This allows us to store a database of all characters currently in the bundles, indexed by name.
/// </summary>
-- Dictionary<K,V>: use Luau table {}string, Character> m_CharactersDict
    -- Dictionary<K,V>: use Luau table {}string, Character> dictionary {  get { return m_CharactersDict; } }

    local m_Loaded = false
    bool loaded { get { return m_Loaded; } }

    Character GetCharacter(string type)
    {
        Character c
        if (m_CharactersDict == nil  or  not m_CharactersDict.TryGetValue(type, out c))
            return nil
        return c
end
    local function LoadDatabase()
    {
        if m_CharactersDict == nil then
            m_CharactersDict = new -- Dictionary<K,V>: use Luau table {}string, Character>()
            yield return Addressables.LoadAssetsAsync<GameObject>("characters", op =>
            {
                Character c = op.:FindFirstChildOfClass<Character>()
                if c ~= nil then
                    table.insert(m_CharactersDict, c.characterName, c)
end
            })
            m_Loaded = true
end
end
end