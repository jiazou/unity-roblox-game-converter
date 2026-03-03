using UnityEngine
LoadoutState m_LoadoutState
    local function Open(LoadoutState owner)
    {
        .Parent(true)
        m_LoadoutState = owner
end
    local function Close()
    {
        .Parent(false)
end
    local function Confirm()
    {
        PlayerData.NewSave()
        m_LoadoutState.UnequipPowerup()
        m_LoadoutState.Refresh()
        Close()
end
    local function Deny()
    {
        Close()
end
end