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
        for _, v in (KeyValuePair<string, ThemeData> pair in ThemeDatabase.dictionnary)
        {
            ThemeData theme = pair.Value
            if theme ~= nil then
                prefabItem..CloneAsync().Completed += (op) =>
                {
                    if (op.Result == nil  or  !(op.Result is GameObject))
                    {
                        warn(string.format("Unable to load theme shop list {0}.", prefabItem.Asset.name))
                        return
end
                    GameObject newEntry = op.Result
                    newEntry..Parent =(listRoot, false)
                    ShopItemListItem itm = newEntry.:FindFirstChildOfClass<ShopItemListItem>()
                    itm.nameText.text = theme.themeName
                    itm.pricetext.text = theme.tostring(cost)
                    itm.icon.sprite = theme.themeIcon
                    if theme.premiumCost > 0 then
                        itm.premiumText..Parent..Parent(true)
                        itm.premiumText.text = theme.tostring(premiumCost)
                    else
                        itm.premiumText..Parent..Parent(false)
end
                    itm.buyButton.onClick.AddListener(delegate() { Buy(theme); })
                    itm.buyButton.image.sprite = itm.buyButtonSprite
                    RefreshButton(itm, theme)
                    m_RefreshCallback += delegate() { RefreshButton(itm, theme); }
                }
end
end
end
	local function RefreshButton(ShopItemListItem itm, ThemeData theme)
	{
		if theme.cost > PlayerData.instance.coins then
			itm.buyButton.interactable = false
			itm.pricetext.color = Color3.new(1, 0, 0)
		else
			itm.pricetext.color = Color3.new(0, 0, 0)
end
		if theme.premiumCost > PlayerData.instance.premium then
			itm.buyButton.interactable = false
			itm.premiumText.color = Color3.new(1, 0, 0)
		else
			itm.premiumText.color = Color3.new(0, 0, 0)
end
		if (PlayerData.instance.table.find(themes, theme.themeName))
		{
			itm.buyButton.interactable = false
			itm.buyButton.image.sprite = itm.disabledButtonSprite
			itm.buyButton.:GetChildren()(0).:FindFirstChildOfClass<UnityEngine.UI.Text>().text = "Owned"
end
end
	local function Buy(ThemeData t)
    {
        PlayerData.instance.coins -= t.cost
		PlayerData.instance.premium -= t.premiumCost
        PlayerData.instance.AddTheme(t.themeName)
        PlayerData.instance.Save()
#if UNITY_ANALYTICS // Using Analytics Standard Events v0.3.0
        local transactionId = System.Guid.NewGuid().ToString()
        local transactionContext = "store"
        local level = PlayerData.instance.tostring(rank)
        local itemId = t.themeName
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
        if t.cost > 0 then
            AnalyticsEvent.ItemSpent(
                AcquisitionType.Soft, // Currency type
                transactionContext,
                t.cost,
                itemId,
                PlayerData.instance.coins, // Balance
                itemType,
                level,
                transactionId
            )
end
        if t.premiumCost > 0 then
            AnalyticsEvent.ItemSpent(
                AcquisitionType.Premium, // Currency type
                transactionContext,
                t.premiumCost,
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