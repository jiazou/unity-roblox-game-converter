using UnityEngine
#if UNITY_ANALYTICS
#endif

local function Populate()
    {
		m_RefreshCallback = nil
        for _, v in (Transform t in listRoot)
        {
            .Destroy(t.gameObject)
end
        for _, v in(KeyValuePair<string, Character> pair in CharacterDatabase.dictionary)
        {
            Character c = pair.Value
            if c ~= nil then
                prefabItem..CloneAsync().Completed += (op) =>
                {
                    if (op.Result == nil  or  !(op.Result is GameObject))
                    {
                        warn(string.format("Unable to load character shop list {0}.", prefabItem.Asset.name))
                        return
end
                    GameObject newEntry = op.Result
                    newEntry..Parent =(listRoot, false)
                    ShopItemListItem itm = newEntry.:FindFirstChildOfClass<ShopItemListItem>()
                    itm.icon.sprite = c.icon
                    itm.nameText.text = c.characterName
                    itm.pricetext.text = c.tostring(cost)
                    itm.buyButton.image.sprite = itm.buyButtonSprite
                    if c.premiumCost > 0 then
                        itm.premiumText..Parent..Parent(true)
                        itm.premiumText.text = c.tostring(premiumCost)
                    else
                        itm.premiumText..Parent..Parent(false)
end
                    itm.buyButton.onClick.AddListener(delegate() { Buy(c); })
                    m_RefreshCallback += delegate() { RefreshButton(itm, c); }
                    RefreshButton(itm, c)
                }
end
end
end
	local function RefreshButton(ShopItemListItem itm, Character c)
	{
		if c.cost > PlayerData.instance.coins then
			itm.buyButton.interactable = false
			itm.pricetext.color = Color3.new(1, 0, 0)
		else
			itm.pricetext.color = Color3.new(0, 0, 0)
end
		if c.premiumCost > PlayerData.instance.premium then
			itm.buyButton.interactable = false
			itm.premiumText.color = Color3.new(1, 0, 0)
		else
			itm.premiumText.color = Color3.new(0, 0, 0)
end
		if (PlayerData.instance.table.find(characters, c.characterName))
		{
			itm.buyButton.interactable = false
			itm.buyButton.image.sprite = itm.disabledButtonSprite
			itm.buyButton.:GetChildren()(0).:FindFirstChildOfClass<UnityEngine.UI.Text>().text = "Owned"
end
end
	local function Buy(Character c)
    {
        PlayerData.instance.coins -= c.cost
		PlayerData.instance.premium -= c.premiumCost
        PlayerData.instance.AddCharacter(c.characterName)
        PlayerData.instance.Save()
#if UNITY_ANALYTICS // Using Analytics Standard Events v0.3.0
        local transactionId = System.Guid.NewGuid().ToString()
        local transactionContext = "store"
        local level = PlayerData.instance.tostring(rank)
        local itemId = c.characterName
        local itemType = "non_consumable"
        local itemQty = 1
        AnalyticsEvent.ItemAcquired(
            AcquisitionType.Soft,
            transactionContext,
            itemQty,
            itemId,
            itemType,
            level,
            transactionId
        )
        if c.cost > 0 then
            AnalyticsEvent.ItemSpent(
                AcquisitionType.Soft, // Currency type
                transactionContext,
                c.cost,
                itemId,
                PlayerData.instance.coins, // Balance
                itemType,
                level,
                transactionId
            )
end
        if c.premiumCost > 0 then
            AnalyticsEvent.ItemSpent(
                AcquisitionType.Premium, // Currency type
                transactionContext,
                c.premiumCost,
                itemId,
                PlayerData.instance.premium, // Balance
                itemType,
                level,
                transactionId
            )
end
#endif

        // Repopulate to change button accordingly.
        Populate()
end
end