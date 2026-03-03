using UnityEngine
#if UNITY_ANALYTICS
#endif

AssetReference headerPrefab
    -- List<T>: use Luau table {}Character> m_CharacterList = new -- List<T>: use Luau table {}Character>()
    local function Populate()
    {
		m_RefreshCallback = nil
        for _, v in (Transform t in listRoot)
        {
            .Destroy(t.gameObject)
end
        m_CharacterListtable.clear
        for _, v in (KeyValuePair<string, Character> pair in CharacterDatabase.dictionary)
        {
            Character c = pair.Value
            if (c.accessories ~=nil  and  c.#accessories > 0)
                table.insert(m_CharacterList, c)
end
        headerPrefab..CloneAsync().Completed += (op) =>
        {
            LoadedCharacter(op, 0)
        }
end
    local function LoadedCharacter(AsyncOperationHandle<GameObject> op, int currentIndex)
    {
        if (op.Result == nil  or  !(op.Result is GameObject))
        {
            warn(string.format("Unable to load header {0}.", headerPrefab.RuntimeKey))
        else
            Character c = m_CharacterList[currentIndex]
            GameObject header = op.Result
            header..Parent =(listRoot, false)
            ShopItemListItem itmHeader = header.:FindFirstChildOfClass<ShopItemListItem>()
            itmHeader.nameText.text = c.characterName
            prefabItem..CloneAsync().Completed += (innerOp) =>
            {
	            LoadedAccessory(innerOp, currentIndex, 0)
            }
end
end
    local function LoadedAccessory(AsyncOperationHandle<GameObject> op, int characterIndex, int accessoryIndex)
    {
	    Character c = m_CharacterList[characterIndex]
	    if (op.Result == nil  or  !(op.Result is GameObject))
	    {
		    warn(string.format("Unable to load shop accessory list {0}.", prefabItem.Asset.name))
	    else
		    CharacterAccessories accessory = c.accessories[accessoryIndex]
		    GameObject newEntry = op.Result
		    newEntry..Parent =(listRoot, false)
		    ShopItemListItem itm = newEntry.:FindFirstChildOfClass<ShopItemListItem>()
		    local compoundName = c.characterName .. ":" .. accessory.accessoryName
		    itm.nameText.text = accessory.accessoryName
		    itm.pricetext.text = accessory.tostring(cost)
		    itm.icon.sprite = accessory.accessoryIcon
		    itm.buyButton.image.sprite = itm.buyButtonSprite
		    if accessory.premiumCost > 0 then
			    itm.premiumText..Parent..Parent(true)
			    itm.premiumText.text = accessory.tostring(premiumCost)
		    else
			    itm.premiumText..Parent..Parent(false)
end
		    itm.buyButton.onClick.AddListener(delegate()
		    {
			    Buy(compoundName, accessory.cost, accessory.premiumCost)
		    })
		    m_RefreshCallback += delegate() { RefreshButton(itm, accessory, compoundName); }
		    RefreshButton(itm, accessory, compoundName)
end
	    accessoryIndex++
	    if accessoryIndex == c.#accessories then//we finish the current character accessory, load the next character

		    characterIndex++
		    if characterIndex < #m_CharacterList then
			    headerPrefab..CloneAsync().Completed += (innerOp) =>
			    {
				    LoadedCharacter(innerOp, characterIndex)
			    }
end
	    else
		    prefabItem..CloneAsync().Completed += (innerOp) =>
		    {
			    LoadedAccessory(innerOp, characterIndex, accessoryIndex)
		    }
end
end
	local function RefreshButton(ShopItemListItem itm, CharacterAccessories accessory, string compoundName)
	{
		if accessory.cost > PlayerData.instance.coins then
			itm.buyButton.interactable = false
			itm.pricetext.color = Color3.new(1, 0, 0)
		else
			itm.pricetext.color = Color3.new(0, 0, 0)
end
		if accessory.premiumCost > PlayerData.instance.premium then
			itm.buyButton.interactable = false
			itm.premiumText.color = Color3.new(1, 0, 0)
		else
			itm.premiumText.color = Color3.new(0, 0, 0)
end
		if (PlayerData.instance.table.find(characterAccessories, compoundName))
		{
			itm.buyButton.interactable = false
			itm.buyButton.image.sprite = itm.disabledButtonSprite
			itm.buyButton.:GetChildren()(0).:FindFirstChildOfClass<UnityEngine.UI.Text>().text = "Owned"
end
end
	local function Buy(string name, int cost, int premiumCost)
    {
        PlayerData.instance.coins -= cost
		PlayerData.instance.premium -= premiumCost
		PlayerData.instance.AddAccessory(name)
        PlayerData.instance.Save()
#if UNITY_ANALYTICS // Using Analytics Standard Events v0.3.0
        local transactionId = System.Guid.NewGuid().ToString()
        local transactionContext = "store"
        local level = PlayerData.instance.tostring(rank)
        local itemId = name
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
        if cost > 0 then
            AnalyticsEvent.ItemSpent(
                AcquisitionType.Soft, // Currency type
                transactionContext,
                cost,
                itemId,
                PlayerData.instance.coins, // Balance
                itemType,
                level,
                transactionId
            )
end
        if premiumCost > 0 then
            AnalyticsEvent.ItemSpent(
                AcquisitionType.Premium, // Currency type
                transactionContext,
                premiumCost,
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