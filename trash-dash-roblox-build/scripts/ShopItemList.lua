using System.Collections.Generic
#if UNITY_ANALYTICS
#endif

Consumable.ConsumableType[] s_ConsumablesTypes = System.Enum.GetValues(typeof(Consumable.ConsumableType)) as Consumable.ConsumableType[]
	local function Populate()
    {
		m_RefreshCallback = nil
        for _, v in (Transform t in listRoot)
        {
            .Destroy(t.gameObject)
end
        for(local i = 0; i < #s_ConsumablesTypes; ++i)
        {
            Consumable c = ConsumableDatabase.GetConsumbale(s_ConsumablesTypes[i])
            if c ~= nil then
                prefabItem..CloneAsync().Completed += (op) =>
                {
                    if (op.Result == nil  or  !(op.Result is GameObject))
                    {
                        warn(string.format("Unable to load item shop list {0}.", prefabItem.RuntimeKey))
                        return
end
                    GameObject newEntry = op.Result
                    newEntry..Parent =(listRoot, false)
                    ShopItemListItem itm = newEntry.:FindFirstChildOfClass<ShopItemListItem>()
                    itm.buyButton.image.sprite = itm.buyButtonSprite
                    itm.nameText.text = c.GetConsumableName()
                    itm.pricetext.text = c.GetPrice().ToString()
                    if (c.GetPremiumCost() > 0)
                    {
                        itm.premiumText..Parent..Parent(true)
                        itm.premiumText.text = c.GetPremiumCost().ToString()
                    else
                        itm.premiumText..Parent..Parent(false)
end
                    itm.icon.sprite = c.icon
                    itm.countText..Parent(true)
                    itm.buyButton.onClick.AddListener(delegate() { Buy(c); })
                    m_RefreshCallback += delegate() { RefreshButton(itm, c); }
                    RefreshButton(itm, c)
                }
end
end
end
	local function RefreshButton(ShopItemListItem itemList, Consumable c)
	{
		local count = 0
		PlayerData.instance.consumables.TryGetValue(c.GetConsumableType(), out count)
		itemList.countText.text = tostring(count)
		if (c.GetPrice() > PlayerData.instance.coins)
		{
			itemList.buyButton.interactable = false
			itemList.pricetext.color = Color3.new(1, 0, 0)
		else
			itemList.pricetext.color = Color3.new(0, 0, 0)
end
		if (c.GetPremiumCost() > PlayerData.instance.premium)
		{
			itemList.buyButton.interactable = false
			itemList.premiumText.color = Color3.new(1, 0, 0)
		else
			itemList.premiumText.color = Color3.new(0, 0, 0)
end
end
    local function Buy(Consumable c)
    {
        PlayerData.instance.coins -= c.GetPrice()
		PlayerData.instance.premium -= c.GetPremiumCost()
		PlayerData.table.insert(instance, c.GetConsumableType())
        PlayerData.instance.Save()
#if UNITY_ANALYTICS // Using Analytics Standard Events v0.3.0
        local transactionId = System.Guid.NewGuid().ToString()
        local transactionContext = "store"
        local level = PlayerData.instance.tostring(rank)
        local itemId = c.GetConsumableName()
        local itemType = "consumable"
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
        if (c.GetPrice() > 0)
        {
            AnalyticsEvent.ItemSpent(
                AcquisitionType.Soft, // Currency type
                transactionContext,
                c.GetPrice(),
                itemId,
                PlayerData.instance.coins, // Balance
                itemType,
                level,
                transactionId
            )
end
        if (c.GetPremiumCost() > 0)
        {
            AnalyticsEvent.ItemSpent(
                AcquisitionType.Premium, // Currency type
                transactionContext,
                c.GetPremiumCost(),
                itemId,
                PlayerData.instance.premium, // Balance
                itemType,
                level,
                transactionId
            )
end
#endif

        Refresh()
end
end