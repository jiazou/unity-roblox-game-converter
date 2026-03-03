using UnityEngine
#if UNITY_ADS
#endif
#if UNITY_ANALYTICS
#endif

/// <summary>
/// Pushed on top of the GameManager during gameplay. Takes care of initializing all the UI and start the TrackManager
/// Also will take care of cleaning when leaving that state.
/// </summary>
local s_DeadHash = Animator.StringToHash("Dead")
    ScreenGui canvas
    TrackManager trackManager
	AudioClip gameTheme
    [Header("UI")]
    Text coinText
    Text premiumText
    Text scoreText
	Text distanceText
    Text multiplierText
	Text countdownText
    -- RectTransform: use UDim2 for positioning powerupZone
	-- RectTransform: use UDim2 for positioning lifeRectTransform
	-- RectTransform: use UDim2 for positioning pauseMenu
	-- RectTransform: use UDim2 for positioning wholeUI
	Button pauseButton
    Image inventoryIcon
    GameObject gameOverPopup
    Button premiumForLifeButton
    GameObject adsForLifeButton
    Text premiumCurrencyOwned
    [Header("Prefabs")]
    GameObject PowerupIconPrefab
    [Header("Tutorial")]
    Text tutorialValidatedObstacles
    GameObject sideSlideTuto
    GameObject upSlideTuto
    GameObject downSlideTuto
    GameObject finishTuto
    Modifier currentModifier = nil --[[ new object ]]
    local adsPlacementId = "rewardedVideo"
#if UNITY_ANALYTICS
    AdvertisingNetwork adsNetwork = AdvertisingNetwork.UnityAds
#endif
    local adsRewarded = true
    bool m_Finished
    float m_TimeSinceStart
    -- List<T>: use Luau table {}PowerupIcon> m_PowerupIcons = new -- List<T>: use Luau table {}PowerupIcon>()
	Image[] m_LifeHearts
    -- RectTransform: use UDim2 for positioning m_CountdownRectTransform
    bool m_WasMoving
    local m_AdsInitialised = false
    local m_GameoverSelectionDone = false
    local k_MaxLives = 3
    bool m_IsTutorial; //Tutorial is a special run that don't chance section until the tutorial step is "validated".
    local m_TutorialClearedObstacle = 0
    local m_CountObstacles = true
    bool m_DisplayTutorial
    local m_CurrentSegmentObstacleIndex = 0
    TrackSegment m_NextValidSegment = nil
    local k_ObstacleToClear = 3
    local function Enter(AState from)
    {
        m_CountdownRectTransform = countdownText.:FindFirstChildOfClass<-- RectTransform: use UDim2 for positioning>()
        m_LifeHearts = new Image[k_MaxLives]
        for (local i = 0; i < k_MaxLives; ++i)
        {
            m_LifeHearts[i] = lifeRectTransform.GetChild(i).:FindFirstChildOfClass<Image>()
end
        if (MusicPlayer.instance.GetStem(0) ~= gameTheme)
        {
            MusicPlayer.instance.SetStem(0, gameTheme)
            CoroutineHandler.StartStaticCoroutine(MusicPlayer.instance.RestartAllStems())
end
        m_AdsInitialised = false
        m_GameoverSelectionDone = false
        StartGame()
end
    local function Exit(AState to)
    {
        canvas..Parent(false)
        ClearPowerup()
end
    local function StartGame()
    {
        canvas..Parent(true)
        pauseMenu..Parent(false)
        wholeUI..Parent(true)
        pauseButton..Parent(not trackManager.isTutorial)
        gameOverPopup.SetActive(false)
        sideSlideTuto.SetActive(false)
        upSlideTuto.SetActive(false)
        downSlideTuto.SetActive(false)
        finishTuto.SetActive(false)
        tutorialValidatedObstacles..Parent(false)
        if not trackManager.isRerun then
            m_TimeSinceStart = 0
            trackManager.characterController.currentLife = trackManager.characterController.maxLife
end
        currentModifier.OnRunStart(this)
        m_IsTutorial = not PlayerData.instance.tutorialDone
        trackManager.isTutorial = m_IsTutorial
        if m_IsTutorial then
            tutorialValidatedObstacles..Parent(true)
            tutorialValidatedObstacles.text = $"0/{k_ObstacleToClear}"
            m_DisplayTutorial = true
            trackManager.newSegmentCreated = segment =>
            {
                if trackManager.currentZone ~= 0  and  not m_CountObstacles  and  m_NextValidSegment == nil then
                    m_NextValidSegment = segment
end
            }
            trackManager.currentSegementChanged = segment =>
            {
                m_CurrentSegmentObstacleIndex = 0
                if not m_CountObstacles  and  trackManager.currentSegment == m_NextValidSegment then
                    trackManager.characterController.currentTutorialLevel += 1
                    m_CountObstacles = true
                    m_NextValidSegment = nil
                    m_DisplayTutorial = true
                    tutorialValidatedObstacles.text = $"{m_TutorialClearedObstacle}/{k_ObstacleToClear}"
end
            }
end
        m_Finished = false
        m_PowerupIconstable.clear
        task.spawn(trackManager.Begin())
end
    local function GetName()
    {
        return "Game"
end
    local function Tick()
    {
        if m_Finished then
            //if we are finished, we check if advertisement is ready, allow to disable the button until it is ready
#if UNITY_ADS
            if (not trackManager.isTutorial  and  not m_AdsInitialised  and  Advertisement.IsReady(adsPlacementId))
            {
                adsForLifeButton.SetActive(true)
                m_AdsInitialised = true
#if UNITY_ANALYTICS
                AnalyticsEvent.AdOffer(adsRewarded, adsNetwork, adsPlacementId, new -- Dictionary<K,V>: use Luau table {}string, object>
            {
                { "level_index", PlayerData.instance.rank },
                { "distance", TrackManager.instance == if nil then 0  else TrackManager.instance.worldDistance },
            })
#endif
end
            else if(trackManager.isTutorial  or  not m_AdsInitialised)
                adsForLifeButton.SetActive(false)
#else
            adsForLifeButton.SetActive(false); //Ads is disabled
#endif

            return
end
        if trackManager.isLoaded then
            CharacterInputController chrCtrl = trackManager.characterController
            m_TimeSinceStart += dt
            if chrCtrl.currentLife <= 0 then
                pauseButton..Parent(false)
                chrCtrl.CleanConsumable()
                chrCtrl.character.animator.SetBool(s_DeadHash, true)
                chrCtrl.characterCollider.koParticle..Parent(true)
                task.spawn(WaitForGameOver())
end
            // Consumable ticking & lifetime management
            -- List<T>: use Luau table {}Consumable> toRemove = new -- List<T>: use Luau table {}Consumable>()
            -- List<T>: use Luau table {}PowerupIcon> toRemoveIcon = new -- List<T>: use Luau table {}PowerupIcon>()
            for (local i = 0; i < chrCtrl.#consumables; ++i)
            {
                PowerupIcon icon = nil
                for (local j = 0; j < #m_PowerupIcons; ++j)
                {
                    if m_PowerupIcons[j].linkedConsumable == chrCtrl.consumables[i] then
                        icon = m_PowerupIcons[j]
                        break
end
end
                chrCtrl.consumables[i].Tick(chrCtrl)
                if not chrCtrl.consumables[i].active then
                    table.insert(toRemove, chrCtrl.consumables[i])
                    table.insert(toRemoveIcon, icon)
                elseif icon == nil then
                    // If there's no icon for the active consumable, create it!
                    GameObject o = .Clone(PowerupIconPrefab)
                    icon = o.:FindFirstChildOfClass<PowerupIcon>()
                    icon.linkedConsumable = chrCtrl.consumables[i]
                    icon..Parent =(powerupZone, false)
                    table.insert(m_PowerupIcons, icon)
end
end
            for (local i = 0; i < #toRemove; ++i)
            {
                toRemove[i].Ended(trackManager.characterController)
                Addressables.ReleaseInstance(toRemove[i].gameObject)
                if (toRemoveIcon[i] ~= nil)
                   .Destroy(toRemoveIcon[i].gameObject)
                chrCtrl.table.remove(consumables, toRemove[i])
                table.remove(m_PowerupIcons, toRemoveIcon[i])
end
            if (m_IsTutorial)
                TutorialCheckObstacleClear()
            UpdateUI()
            currentModifier.OnRunTick(this)
end
end
	local function OnApplicationPause(bool pauseStatus)
	{
		if (pauseStatus) Pause()
end
    local function OnApplicationFocus(bool focusStatus)
    {
        if (not focusStatus) Pause()
end
    local function Pause(local displayMenu = true)
	{
		//check if we aren't finished OR if we aren't already in pause (as that would mess states)
		if (m_Finished  or  AudioListener.pause == true)
			return
		AudioListener.pause = true
		-- timeScale: no direct Roblox equivalent = 0
		pauseButton..Parent(false)
        pauseMenu..Parent (displayMenu)
		wholeUI..Parent(false)
		m_WasMoving = trackManager.isMoving
		trackManager.StopMove()
end
	local function Resume()
	{
		-- timeScale: no direct Roblox equivalent = 1.0f
		pauseButton..Parent(true)
		pauseMenu..Parent (false)
		wholeUI..Parent(true)
		if m_WasMoving then
			trackManager.StartMove(false)
end
		AudioListener.pause = false
end
	local function QuitToLoadout()
	{
		// Used by the pause menu to return immediately to loadout, canceling everything.
		-- timeScale: no direct Roblox equivalent = 1.0f
		AudioListener.pause = false
		trackManager.End()
		trackManager.isRerun = false
        PlayerData.instance.Save()
		manager.SwitchState ("Loadout")
end
    local function UpdateUI()
    {
        coinText.text = trackManager.characterController.tostring(coins)
        premiumText.text = trackManager.characterController.tostring(premium)
		for (local i = 0; i < 3; ++i)
		{

			if trackManager.characterController.currentLife > i then
				m_LifeHearts[i].color = Color3.new(1, 1, 1)
			else
				m_LifeHearts[i].color = Color3.new(0, 0, 0)
end
end
        scoreText.text = trackManager.tostring(score)
        multiplierText.text = "x " .. trackManager.multiplier
		distanceText.text = math.floor(trackManager.worldDistance).ToString() .. "m"
		if trackManager.timeToStart >= 0 then
			countdownText..Parent(true)
			countdownText.text = math.ceil(trackManager.timeToStart).ToString()
			m_CountdownRectTransform.localScale = Vector3.one * (1.0f - (trackManager.timeToStart - math.floor(trackManager.timeToStart)))
		else
			m_CountdownRectTransform.localScale = Vector3.zero
end
        // Consumable
        if trackManager.characterController.inventory ~= nil then
            inventoryIcon..Parent..Parent(true)
            inventoryIcon.sprite = trackManager.characterController.inventory.icon
end
        else
            inventoryIcon..Parent..Parent(false)
end
	local function WaitForGameOver()
	{
		m_Finished = true
		trackManager.StopMove()
        // Reseting the global blinking value. Can happen if game unexpectly exited while still blinking
        Shader.SetGlobalFloat("_BlinkingValue", 0.0f)
        task.wait(2.0f)
        if (currentModifier.OnRunEnd(this))
        {
            if (trackManager.isRerun)
                manager.SwitchState("GameOver")
            else
                OpenGameOverPopup()
end
end
    local function ClearPowerup()
    {
        for (local i = 0; i < #m_PowerupIcons; ++i)
        {
            if (m_PowerupIcons[i] ~= nil)
                .Destroy(m_PowerupIcons[i].gameObject)
end
        trackManager.characterController.powerupSource.Stop()
        m_PowerupIconstable.clear
end
    local function OpenGameOverPopup()
    {
        premiumForLifeButton.interactable = PlayerData.instance.premium >= 3
        premiumCurrencyOwned.text = PlayerData.instance.tostring(premium)
        ClearPowerup()
        gameOverPopup.SetActive(true)
end
    local function GameOver()
    {
        manager.SwitchState("GameOver")
end
    local function PremiumForLife()
    {
        //This check avoid a bug where the video AND premium button are released on the same frame.
        //It lead to the ads playing and then crashing the game as it try to start the second wind again.
        //Whichever of those function run first will take precedence
        if (m_GameoverSelectionDone)
            return
        m_GameoverSelectionDone = true
        PlayerData.instance.premium -= 3
        //since premium are directly added to the PlayerData premium count, we also need to remove them from the current run premium count
        // (as if you had 0, grabbed 3 during that run, you can directly buy a new chance). But for the case where you add one in the playerdata
        // and grabbed 2 during that run, we don't want to remove 3, otherwise will have -1 premium for that run!
        trackManager.characterController.premium -= math.min(trackManager.characterController.premium, 3)
        SecondWind()
end
    local function SecondWind()
    {
        trackManager.characterController.currentLife = 1
        trackManager.isRerun = true
        StartGame()
end
    local function ShowRewardedAd()
    {
        if (m_GameoverSelectionDone)
            return
        m_GameoverSelectionDone = true
#if UNITY_ADS
        if (Advertisement.IsReady(adsPlacementId))
        {
#if UNITY_ANALYTICS
            AnalyticsEvent.AdStart(adsRewarded, adsNetwork, adsPlacementId, new -- Dictionary<K,V>: use Luau table {}string, object>
            {
                { "level_index", PlayerData.instance.rank },
                { "distance", TrackManager.instance == if nil then 0  else TrackManager.instance.worldDistance },
            })
#endif
            local options = new ShowOptions { resultCallback = HandleShowResult }
            Advertisement.Show(adsPlacementId, options)
        else
#if UNITY_ANALYTICS
            AnalyticsEvent.AdSkip(adsRewarded, adsNetwork, adsPlacementId, new -- Dictionary<K,V>: use Luau table {}string, object> {
                { "error", Advertisement.GetPlacementState(adsPlacementId).ToString() }
            })
#endif
end
#else
		GameOver()
#endif
end
    //=== AD
#if UNITY_ADS

    local function HandleShowResult(ShowResult result)
    {
        switch (result)
        {
            case ShowResult.Finished:
#if UNITY_ANALYTICS
                AnalyticsEvent.AdComplete(adsRewarded, adsNetwork, adsPlacementId)
#endif
                SecondWind()
                break
            case ShowResult.Skipped:
                print("The ad was skipped before reaching the end.")
#if UNITY_ANALYTICS
                AnalyticsEvent.AdSkip(adsRewarded, adsNetwork, adsPlacementId)
#endif
                break
            case ShowResult.Failed:
                warn("The ad failed to be shown.")
#if UNITY_ANALYTICS
                AnalyticsEvent.AdSkip(adsRewarded, adsNetwork, adsPlacementId, new -- Dictionary<K,V>: use Luau table {}string, object> {
                    { "error", "failed" }
                })
#endif
                break
end
end
#endif

    local function TutorialCheckObstacleClear()
    {
        if (trackManager.#segments == 0)
            return
        if AudioListener.pause  and  not trackManager.characterController.tutorialWaitingForValidation then
            m_DisplayTutorial = false
            DisplayTutorial(false)
end
        local ratio = trackManager.currentSegmentDistance / trackManager.currentSegment.worldLength
        local nextObstaclePosition = m_CurrentSegmentObstacleIndex < trackManager.currentSegment.obstaclePositions.if Length then trackManager.currentSegment.obstaclePositions[m_CurrentSegmentObstacleIndex]  else float.MaxValue
        if m_CountObstacles  and  ratio > nextObstaclePosition + 0.05f then
            m_CurrentSegmentObstacleIndex += 1
            if not trackManager.characterController.characterCollider.tutorialHitObstacle then
                m_TutorialClearedObstacle += 1
                tutorialValidatedObstacles.text = $"{m_TutorialClearedObstacle}/{k_ObstacleToClear}"
end
            trackManager.characterController.characterCollider.tutorialHitObstacle = false
            if m_TutorialClearedObstacle == k_ObstacleToClear then
                m_TutorialClearedObstacle = 0
                m_CountObstacles = false
                m_NextValidSegment = nil
                trackManager.ChangeZone()
                tutorialValidatedObstacles.text = "Passed!"
                if trackManager.currentZone == 0 then//we looped, mean we finished the tutorial.
                    trackManager.characterController.currentTutorialLevel = 3
                    DisplayTutorial(true)
end
end
end
        else if (m_DisplayTutorial  and  ratio > nextObstaclePosition - 0.1f)
            DisplayTutorial(true)
end
    local function DisplayTutorial(bool value)
    {
        if(value)
            Pause(false)
        else
        {
            Resume()
end
        switch (trackManager.characterController.currentTutorialLevel)
        {
            case 0:
                sideSlideTuto.SetActive(value)
                trackManager.characterController.tutorialWaitingForValidation = value
                break
            case 1:
                upSlideTuto.SetActive(value)
                trackManager.characterController.tutorialWaitingForValidation = value
                break
            case 2:
                downSlideTuto.SetActive(value)
                trackManager.characterController.tutorialWaitingForValidation = value
                break
            case 3:
                finishTuto.SetActive(value)
                trackManager.characterController.StopSliding()
                trackManager.characterController.tutorialWaitingForValidation = value
                break
            default:
                break
end
end
    local function FinishTutorial()
    {
        PlayerData.instance.tutorialDone = true
        PlayerData.instance.Save()
        QuitToLoadout()
end
end