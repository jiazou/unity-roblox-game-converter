using UnityEngine
// Base any list in the shop (Consumable, Character, Themes)
AssetReference prefabItem
    -- RectTransform: use UDim2 for positioning listRoot
	delegate local function RefreshCallback()
	RefreshCallback m_RefreshCallback
    local function Open()
    {
        Populate()
        .Parent(true)
end
    local function Close()
    {
        .Parent(false)
        m_RefreshCallback = nil
end
	local function Refresh()
	{
		m_RefreshCallback()
end
    local function Populate()
end