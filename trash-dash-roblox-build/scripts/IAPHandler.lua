using System.Collections.Generic
#if UNITY_PURCHASING
#endif
#if UNITY_ANALYTICS
#endif

#if UNITY_PURCHASING
    local function OnEnable()
    {
#if UNITY_ANALYTICS
        AnalyticsEvent.StoreOpened(StoreType.Premium)
#endif
end
    local function ProductBought(Product product)
    {
        local amount = 0
        switch (product.definition.id)
        {
            case "10_premium":
                amount = 10
                break
            case "50_premium":
                amount = 50
                break
            case "100_premium":
                amount = 100
                break
end
        if amount > 0 then
            PlayerData.instance.premium += amount
            PlayerData.instance.Save()
#if UNITY_ANALYTICS // Using Analytics Standard Events v0.3.0
            local transactionId = product.transactionID
            local transactionContext = "premium_store"
            local itemId = product.definition.id
            local itemType = "consumable"
            local level = PlayerData.instance.tostring(rank)
            AnalyticsEvent.IAPTransaction(
                transactionContext,
                product.metadata.localizedPrice,
                itemId,
                itemType,
                level,
                transactionId
            )
            AnalyticsEvent.ItemAcquired( 
                AcquisitionType.Premium, // Currency type
                transactionContext,
                amount,
                itemId,
                PlayerData.instance.premium, // Item balance
                itemType,
                level,
                transactionId
            )
#endif
end
end
    local function ProductError(Product product, PurchaseFailureReason reason)
    {
        warn("Product : " .. product.definition.id .. " couldn't be bought because " .. reason)
end
#endif
end