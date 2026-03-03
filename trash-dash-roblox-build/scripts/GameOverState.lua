local TeleportService = game:GetService("TeleportService")

﻿using UnityEngine
#if UNITY_ANALYTICS
#endif
/// <summary>
/// state pushed on top of the GameManager when the player dies.
/// </summary>
TrackManager trackManager
    ScreenGui canvas
    MissionUI missionPopup
	AudioClip gameOverTheme
	Leaderboard miniLeaderboard
	Leaderboard fullLeaderboard
    GameObject addButton
    local function Enter(AState from)
    {
        canvas..Parent(true)
		miniLeaderboard.playerEntry.inputName.text = PlayerData.instance.previousName
		miniLeaderboard.playerEntry.score.text = trackManager.tostring(score)
		miniLeaderboard.Populate()
        if (PlayerData.instance.AnyMissionComplete())
            task.spawn(missionPopup.Open())
        else
            missionPopup..Parent(false)
		CreditCoins()
		if (MusicPlayer.instance.GetStem(0) ~= gameOverTheme)
		{
            MusicPlayer.instance.SetStem(0, gameOverTheme)
			task.spawn(MusicPlayer.instance.RestartAllStems())
end
end
	local function Exit(AState to)
    {
        canvas..Parent(false)
        FinishRun()
end
    local function GetName()
    {
        return "GameOver"
end
    local function Tick()
    {
end
	local function OpenLeaderboard()
	{
		fullLeaderboard.forcePlayerDisplay = false
		fullLeaderboard.displayPlayer = true
		fullLeaderboard.playerEntry.playerName.text = miniLeaderboard.playerEntry.inputName.text
		fullLeaderboard.playerEntry.score.text = trackManager.tostring(score)
		fullLeaderboard.Open()
end
	local function GoToStore()
    {
        UnityEngine.SceneManagement.-- LoadScene: use TeleportService or place switching("shop", UnityEngine.SceneManagement.LoadSceneMode.Additive)
end
    local function GoToLoadout()
    {
        trackManager.isRerun = false
		manager.SwitchState("Loadout")
end
    local function RunAgain()
    {
        trackManager.isRerun = false
        manager.SwitchState("Game")
end
    local function CreditCoins()
	{
		PlayerData.instance.Save()
#if UNITY_ANALYTICS // Using Analytics Standard Events v0.3.0
        local transactionId = System.Guid.NewGuid().ToString()
        local transactionContext = "gameplay"
        local level = PlayerData.instance.tostring(rank)
        local itemType = "consumable"
        if trackManager.characterController.coins > 0 then
            AnalyticsEvent.ItemAcquired(
                AcquisitionType.Soft, // Currency type
                transactionContext,
                trackManager.characterController.coins,
                "fishbone",
                PlayerData.instance.coins,
                itemType,
                level,
                transactionId
            )
end
        if trackManager.characterController.premium > 0 then
            AnalyticsEvent.ItemAcquired(
                AcquisitionType.Premium, // Currency type
                transactionContext,
                trackManager.characterController.premium,
                "anchovies",
                PlayerData.instance.premium,
                itemType,
                level,
                transactionId
            )
end
#endif 
end
	local function FinishRun()
    {
		if miniLeaderboard.playerEntry.inputName.text == "" then
			miniLeaderboard.playerEntry.inputName.text = "Trash Cat"
		else
			PlayerData.instance.previousName = miniLeaderboard.playerEntry.inputName.text
end
        PlayerData.instance.InsertScore(trackManager.score, miniLeaderboard.playerEntry.inputName.text )
        CharacterCollider.DeathEvent de = trackManager.characterController.characterCollider.deathData
        //register data to analytics
#if UNITY_ANALYTICS
        AnalyticsEvent.GameOver(nil, new -- Dictionary<K,V>: use Luau table {}string, object> {
            { "coins", de.coins },
            { "premium", de.premium },
            { "score", de.score },
            { "distance", de.worldDistance },
            { "obstacle",  de.obstacleType },
            { "theme", de.themeUsed },
            { "character", de.character },
        })
#endif

        PlayerData.instance.Save()
        trackManager.End()
end
    //----------------
end