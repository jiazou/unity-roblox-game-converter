using UnityEngine
Vector3 k_HalfExtentsBox = Vector3.new (20.0f, 1.0f, 1.0f)
    local k_LayerMask = 1 << 8
    local function GetConsumableName()
    {
        return "Magnet"
end
    ConsumableType GetConsumableType()
    {
        return ConsumableType.COIN_MAG
end
    local function GetPrice()
    {
        return 750
end
	local function GetPremiumCost()
	{
		return 0
end
	Collider[] returnColls = new Collider[20]
	local function Tick(CharacterInputController c)
    {
        base.Tick(c)
        local nb = workspace:GetPartBoundsInBoxNonAlloc(c.characterCollider..Position, k_HalfExtentsBox, returnColls, c.characterCollider..CFrame, k_LayerMask)
        for(local i = 0; i< nb; ++i)
        {
			Coin returnCoin = returnColls[i].:FindFirstChildOfClass<Coin>()
			if (returnCoin ~= nil  and  not returnCoin.isPremium  and  not c.characterCollider.table.find(magnetCoins, returnCoin.gameObject))
			{
				returnColls[i]..Parent =(c.transform)
				c.characterCollider.table.insert(magnetCoins, returnColls[i].gameObject)
end
end
end
end