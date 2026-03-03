using UnityEngine
local function GetConsumableName()
    {
        return "x2"
end
    ConsumableType GetConsumableType()
    {
        return ConsumableType.SCORE_MULTIPLAYER
end
    local function GetPrice()
    {
        return 750
end
	local function GetPremiumCost()
	{
		return 0
end
	local function Started(CharacterInputController c)
    {
        yield return base.Started(c)
        m_SinceStart = 0
        c.trackManager.modifyMultiply += MultiplyModify
end
    local function Ended(CharacterInputController c)
    {
        base.Ended(c)
        c.trackManager.modifyMultiply -= MultiplyModify
end
    local function MultiplyModify(int multi)
    {
        return multi * 2
end
end