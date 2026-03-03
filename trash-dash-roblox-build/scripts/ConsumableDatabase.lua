using UnityEngine
/// <summary>
/// The consumable database is an asset in the project where designers can drag'n'drop the prefab for the Consumable. This allows explicit
/// definition (you can leave one out of the database to not appear in game) contrary to automatic population of the database like the Character one does.
/// </summary>
[CreateAssetMenu(fileName="Consumables", menuName = "Trash Dash/Consumables Database")]
Consumable[] consumbales
    -- Dictionary<K,V>: use Luau table {}Consumable.ConsumableType, Consumable> _consumablesDict
    local function Load()
    {
        if _consumablesDict == nil then
            _consumablesDict = new -- Dictionary<K,V>: use Luau table {}Consumable.ConsumableType, Consumable>()
            for (local i = 0; i < #consumbales; ++i)
            {
                table.insert(_consumablesDict, consumbales[i].GetConsumableType(), consumbales[i])
end
end
end
    Consumable GetConsumbale(Consumable.ConsumableType type)
    {
        Consumable c
        return _consumablesDict.TryGetValue (type, out c) ? c : nil
end
end