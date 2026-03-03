using UnityEngine
local function GetConsumableName()
    {
        return "Invincible"
end
    ConsumableType GetConsumableType()
    {
        return ConsumableType.INVINCIBILITY
end
    local function GetPrice()
    {
        return 1500
end
	local function GetPremiumCost()
	{
		return 5
end
	local function Tick(CharacterInputController c)
    {
        base.Tick(c)
        c.characterCollider.SetInvincibleExplicit(true)
end
    local function Started(CharacterInputController c)
    {
        yield return base.Started(c)
        c.characterCollider.SetInvincible(duration)
end
    local function Ended(CharacterInputController c)
    {
        base.Ended(c)
        c.characterCollider.SetInvincibleExplicit(false)
end
end