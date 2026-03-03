local RunService = game:GetService("RunService")
local TeleportService = game:GetService("TeleportService")

﻿using System.Collections.Generic
#if UNITY_ADS
#endif
#if UNITY_ANALYTICS
#endif

ConsumableDatabase consumableDatabase
    ShopItemList itemList
    ShopCharacterList characterList
    ShopAccessoriesList accessoriesList
    ShopThemeList themeList
    [Header("UI")]
    Text coinCounter
    Text premiumCounter
    Button cheatButton
    ShopList m_OpenList
    local k_CheatCoins = 1000000
    local k_CheatPremium = 1000
#if UNITY_ADS
    local k_AdRewardCoins = 100
#endif

	local function function script.Parent.AncestryChanged
    {
        PlayerData.Create()
        consumableDatabase.Load()
        CoroutineHandler.StartStaticCoroutine(CharacterDatabase.LoadDatabase())
        CoroutineHandler.StartStaticCoroutine(ThemeDatabase.LoadDatabase())
#if UNITY_ANALYTICS
        AnalyticsEvent.StoreOpened(StoreType.Soft)
#endif

#if not UNITY_EDITOR  and  not DEVELOPMENT_BUILD
        //Disable cheating on non dev build outside of the editor
        cheatButton.interactable = false
#else
        cheatButton.interactable = true
#endif

        m_OpenList = itemList
        itemList.Open()
end
	local function game:GetService('RunService').Heartbeat:Connect(function()
    {
        coinCounter.text = PlayerData.instance.tostring(coins)
        premiumCounter.text = PlayerData.instance.tostring(premium)
end
    local function OpenItemList()
    {
        m_OpenList.Close()
        itemList.Open()
        m_OpenList = itemList
end
    local function OpenCharacterList()
    {
        m_OpenList.Close()
        characterList.Open()
        m_OpenList = characterList
end
    local function OpenThemeList()
    {
        m_OpenList.Close()
        themeList.Open()
        m_OpenList = themeList
end
    local function OpenAccessoriesList()
    {
        m_OpenList.Close()
        accessoriesList.Open()
        m_OpenList = accessoriesList
end
    local function LoadScene(string scene)
    {
        -- LoadScene: use TeleportService or place switching(scene, LoadSceneMode.Single)
end
	local function CloseScene()
	{
        SceneManager.UnloadSceneAsync("shop")
	    LoadoutState loadoutState = GameManager.instance.topState as LoadoutState
	    if loadoutState ~= nil then
            loadoutState.Refresh()
end
end
	local function CheatCoin()
	{
#if not UNITY_EDITOR  and  not DEVELOPMENT_BUILD
        return ; //you can't cheat in production build
#endif

        PlayerData.instance.coins += k_CheatCoins
		PlayerData.instance.premium += k_CheatPremium
		PlayerData.instance.Save()
end
#if UNITY_ADS
    local function ShowRewardedAd()
    {
        if (Advertisement.IsReady("rewardedVideo"))
        {
            local options = new ShowOptions { resultCallback = HandleShowResult }
            Advertisement.Show("rewardedVideo", options)
end
end
    local function HandleShowResult(ShowResult result)
    {
        switch (result)
        {
            case ShowResult.Finished:
                print("The ad was successfully shown.")
                PlayerData.instance.coins += k_AdRewardCoins
                PlayerData.instance.Save()
                break
            case ShowResult.Skipped:
                print("The ad was skipped before reaching the end.")
                break
            case ShowResult.Failed:
                warn("The ad failed to be shown.")
                break
end
end
#endif
end