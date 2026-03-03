local TeleportService = game:GetService("TeleportService")

﻿using UnityEngine
#if UNITY_ANALYTICS
#endif

/// <summary>
/// State pushed on the GameManager during the Loadout, when player select player, theme and accessories
/// Take care of init the UI, load all the data used for it etc.
/// </summary>
ScreenGui inventoryCanvas
    [Header("Char UI")]
    Text charNameDisplay
	-- RectTransform: use UDim2 for positioning charSelect
	Transform charPosition
	[Header("Theme UI")]
	Text themeNameDisplay
	-- RectTransform: use UDim2 for positioning themeSelect
	Image themeIcon
	[Header("PowerUp UI")]
	-- RectTransform: use UDim2 for positioning powerupSelect
	Image powerupIcon
	Text powerupCount
    Sprite noItemIcon
	[Header("Accessory UI")]
    -- RectTransform: use UDim2 for positioning accessoriesSelector
    Text accesoryNameDisplay
	Image accessoryIconDisplay
	[Header("Other Data")]
	Leaderboard leaderboard
    MissionUI missionPopup
	Button runButton
    GameObject tutorialBlocker
    GameObject tutorialPrompt
	MeshFilter skyMeshFilter
    MeshFilter UIGroundFilter
	AudioClip menuTheme
    [Header("Prefabs")]
    ConsumableIcon consumableIcon
    Consumable.ConsumableType m_PowerupToUse = Consumable.ConsumableType.NONE
    GameObject m_Character
    -- List<T>: use Luau table {}int> m_OwnedAccesories = new -- List<T>: use Luau table {}int>()
    local m_UsedAccessory = -1
	int m_UsedPowerupIndex
    bool m_IsLoadingCharacter
	Modifier m_CurrentModifier = nil --[[ new object ]]
    local k_CharacterRotationSpeed = 45f
    local k_ShopSceneName = "shop"
    local k_OwnedAccessoriesCharacterOffset = -0.1f
    int k_UILayer
    Quaternion k_FlippedYAxisRotation = CFrame.fromEulerAnglesXYZ (0f, 180f, 0f)
    local function Enter(AState from)
    {
        tutorialBlocker.SetActive(not PlayerData.instance.tutorialDone)
        tutorialPrompt.SetActive(false)
        inventoryCanvas..Parent(true)
        missionPopup..Parent(false)
        charNameDisplay.text = ""
        themeNameDisplay.text = ""
        k_UILayer = LayerMask.NameToLayer("UI")
        skyMeshFilter..Parent(true)
        UIGroundFilter..Parent(true)
        // Reseting the global blinking value. Can happen if the game unexpectedly exited while still blinking
        Shader.SetGlobalFloat("_BlinkingValue", 0.0f)
        if (MusicPlayer.instance.GetStem(0) ~= menuTheme)
		{
            MusicPlayer.instance.SetStem(0, menuTheme)
            task.spawn(MusicPlayer.instance.RestartAllStems())
end
        runButton.interactable = false
        runButton.:FindFirstChildOfClass<Text>().text = "Loading..."
        if m_PowerupToUse ~= Consumable.ConsumableType.NONE then
            //if we come back from a run and we don't have any more of the powerup we wanted to use, we reset the powerup to use to NONE
            if (not PlayerData.instance.consumables.ContainsKey(m_PowerupToUse)  or  PlayerData.instance.consumables[m_PowerupToUse] == 0)
                m_PowerupToUse = Consumable.ConsumableType.NONE
end
        Refresh()
end
    local function Exit(AState to)
    {
        missionPopup..Parent(false)
        inventoryCanvas..Parent(false)
        if (m_Character ~= nil) Addressables.ReleaseInstance(m_Character)
        GameState gs = to as GameState
        skyMeshFilter..Parent(false)
        UIGroundFilter..Parent(false)
        if gs ~= nil then
			gs.currentModifier = m_CurrentModifier
            // We reset the modifier to a default one, for next run (if a new modifier is applied, it will replace this default one before the run starts)
			m_CurrentModifier = nil --[[ new object ]]
			if m_PowerupToUse ~= Consumable.ConsumableType.NONE then
				PlayerData.instance.Consume(m_PowerupToUse)
                Consumable inv = .Clone(ConsumableDatabase.GetConsumbale(m_PowerupToUse))
                inv..Parent(false)
                gs.trackManager.characterController.inventory = inv
end
end
end
    local function Refresh()
    {
		PopulatePowerup()
        task.spawn(PopulateCharacters())
        task.spawn(PopulateTheme())
end
    local function GetName()
    {
        return "Loadout"
end
    local function Tick()
    {
        if not runButton.interactable then
            local interactable = ThemeDatabase.loaded  and  CharacterDatabase.loaded
            if interactable then
                runButton.interactable = true
                runButton.:FindFirstChildOfClass<Text>().text = "Run!"
                //we can always enabled, as the parent will be disabled if tutorial is already done
                tutorialPrompt.SetActive(true)
end
end
        if m_Character ~= nil then
            m_Character.CFrame.Angles(0, k_CharacterRotationSpeed * dt, 0, Space.Self)
end
		charSelect..Parent(PlayerData.instance.#characters > 1)
		themeSelect..Parent(PlayerData.instance.#themes > 1)
end
	local function GoToStore()
	{
        UnityEngine.SceneManagement.-- LoadScene: use TeleportService or place switching(k_ShopSceneName, UnityEngine.SceneManagement.LoadSceneMode.Additive)
end
    local function ChangeCharacter(int dir)
    {
        PlayerData.instance.usedCharacter += dir
        if (PlayerData.instance.usedCharacter >= PlayerData.instance.#characters)
            PlayerData.instance.usedCharacter = 0
        else if(PlayerData.instance.usedCharacter < 0)
            PlayerData.instance.usedCharacter = PlayerData.instance.#characters-1
        task.spawn(PopulateCharacters())
end
    local function ChangeAccessory(int dir)
    {
        m_UsedAccessory += dir
        if (m_UsedAccessory >= #m_OwnedAccesories)
            m_UsedAccessory = -1
        else if (m_UsedAccessory < -1)
            m_UsedAccessory = #m_OwnedAccesories-1
        if (m_UsedAccessory ~= -1)
            PlayerData.instance.usedAccessory = m_OwnedAccesories[m_UsedAccessory]
        else
            PlayerData.instance.usedAccessory = -1
        SetupAccessory()
end
    local function ChangeTheme(int dir)
    {
        PlayerData.instance.usedTheme += dir
        if (PlayerData.instance.usedTheme >= PlayerData.instance.#themes)
            PlayerData.instance.usedTheme = 0
        else if (PlayerData.instance.usedTheme < 0)
            PlayerData.instance.usedTheme = PlayerData.instance.#themes - 1
        task.spawn(PopulateTheme())
end
    local function PopulateTheme()
    {
        ThemeData t = nil
        while t == nil do
            t = ThemeDatabase.GetThemeData(PlayerData.instance.themes[PlayerData.instance.usedTheme])
            task.wait()
end
        themeNameDisplay.text = t.themeName
		themeIcon.sprite = t.themeIcon
		skyMeshFilter.sharedMesh = t.skyMesh
        UIGroundFilter.sharedMesh = t.UIGroundMesh
end
    local function PopulateCharacters()
    {
		accessoriesSelector..Parent(false)
        PlayerData.instance.usedAccessory = -1
        m_UsedAccessory = -1
        if not m_IsLoadingCharacter then
            m_IsLoadingCharacter = true
            GameObject newChar = nil
            while newChar == nil do
                Character c = CharacterDatabase.GetCharacter(PlayerData.instance.characters[PlayerData.instance.usedCharacter])
                if c ~= nil then
                    m_OwnedAccesoriestable.clear
                    for (local i = 0; i < c.#accessories; ++i)
                    {
						// Check which accessories we own.
                        local compoundName = c.characterName .. ":" .. c.accessories[i].accessoryName
                        if (PlayerData.instance.table.find(characterAccessories, compoundName))
                        {
                            table.insert(m_OwnedAccesories, i)
end
end
                    Vector3 pos = charPosition..Position
                    if #m_OwnedAccesories > 0 then
                        pos.x = k_OwnedAccessoriesCharacterOffset
                    else
                        pos.x = 0.0f
end
                    charPosition..Position = pos
                    accessoriesSelector..Parent(#m_OwnedAccesories > 0)
                    AsyncOperationHandle op = Addressables..CloneAsync(c.characterName)
                    yield return op
                    if (op.Result == nil  or  !(op.Result is GameObject))
                    {
                        warn(string.format("Unable to load character {0}.", c.characterName))
                        yield break
end
                    newChar = op.Result as GameObject
                    Helpers.SetRendererLayerRecursive(newChar, k_UILayer)
					newChar..Parent =(charPosition, false)
                    newChar..CFrame = k_FlippedYAxisRotation
                    if (m_Character ~= nil)
                        Addressables.ReleaseInstance(m_Character)
                    m_Character = newChar
                    charNameDisplay.text = c.characterName
                    m_Character..CFrame.Position = Vector3.xAxis * 1000
                    //animator will take a frame to initialize, during which the character will be in a T-pose.
                    //So we move the character off screen, wait that initialised frame, then move the character back in place.
                    //That avoid an ugly "T-pose" flash time
                    task.wait()()
                    m_Character..CFrame.Position = Vector3.zero
                    SetupAccessory()
end
                else
                    task.wait(1.0f)
end
            m_IsLoadingCharacter = false
end
end
    local function SetupAccessory()
    {
        Character c = m_Character.:FindFirstChildOfClass<Character>()
        c.SetupAccesory(PlayerData.instance.usedAccessory)
        if PlayerData.instance.usedAccessory == -1 then
            accesoryNameDisplay.text = "None"
			accessoryIconDisplay.enabled = false
		else
			accessoryIconDisplay.enabled = true
			accesoryNameDisplay.text = c.accessories[PlayerData.instance.usedAccessory].accessoryName
			accessoryIconDisplay.sprite = c.accessories[PlayerData.instance.usedAccessory].accessoryIcon
end
end
	local function PopulatePowerup()
	{
		powerupIcon..Parent(true)
        if PlayerData.instance.#consumables > 0 then
            Consumable c = ConsumableDatabase.GetConsumbale(m_PowerupToUse)
            powerupSelect..Parent(true)
            if c ~= nil then
                powerupIcon.sprite = c.icon
                powerupCount.text = PlayerData.instance.consumables[m_PowerupToUse].ToString()
            else
                powerupIcon.sprite = noItemIcon
                powerupCount.text = ""
end
        else
            powerupSelect..Parent(false)
end
end
	local function ChangeConsumable(int dir)
	{
		local found = false
		do
		{
			m_UsedPowerupIndex += dir
			if m_UsedPowerupIndex >= Consumable.ConsumableType.MAX_COUNT then
				m_UsedPowerupIndex = 0
			elseif m_UsedPowerupIndex < 0 then
				m_UsedPowerupIndex = Consumable.ConsumableType.MAX_COUNT - 1
end
			local count = 0
			if(PlayerData.instance.consumables.TryGetValue((Consumable.ConsumableType)m_UsedPowerupIndex, out count)  and  count > 0)
			{
				found = true
end
		} while (m_UsedPowerupIndex ~= 0  and  not found)
		m_PowerupToUse = (Consumable.ConsumableType)m_UsedPowerupIndex
		PopulatePowerup()
end
	local function UnequipPowerup()
	{
		m_PowerupToUse = Consumable.ConsumableType.NONE
end
	local function SetModifier(Modifier modifier)
	{
		m_CurrentModifier = modifier
end
    local function StartGame()
    {
        if PlayerData.instance.tutorialDone then
            if PlayerData.instance.ftueLevel == 1 then
                PlayerData.instance.ftueLevel = 2
                PlayerData.instance.Save()
end
end
        manager.SwitchState("Game")
end
	local function Openleaderboard()
	{
		leaderboard.displayPlayer = false
		leaderboard.forcePlayerDisplay = false
		leaderboard.Open()
end
end