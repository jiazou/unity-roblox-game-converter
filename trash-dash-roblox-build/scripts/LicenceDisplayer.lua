using UnityEngine
local function function script.Parent.AncestryChanged
    {
        PlayerData.Create()
	    if PlayerData.instance.licenceAccepted then
            // If we have already accepted the licence, we close the popup, no need for it.
            Close()
end
end
	local function Accepted()
    {
        PlayerData.instance.licenceAccepted = true
        PlayerData.instance.Save()
        Close()
end
    local function Refuse()
    {
        Application.Quit()
end
    local function Close()
    {
        .Parent(false)
end
end