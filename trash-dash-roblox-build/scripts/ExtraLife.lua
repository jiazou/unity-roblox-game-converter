using UnityEngine
local k_MaxLives = 3
    local k_CoinValue = 10
    local function GetConsumableName()
    {
        return "Life"
end
    ConsumableType GetConsumableType()
    {
        return ConsumableType.EXTRALIFE
end
    local function GetPrice()
    {
        return 2000
end
	local function GetPremiumCost()
	{
		return 5
end
    local function CanBeUsed(CharacterInputController c)
    {
        if (c.currentLife == c.maxLife)
            return false
        return true
end
    local function Started(CharacterInputController c)
    {
        yield return base.Started(c)
        if (c.currentLife < k_MaxLives)
            c.currentLife += 1
		else
            c.coins += k_CoinValue
end
end