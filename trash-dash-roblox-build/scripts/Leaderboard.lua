using UnityEngine
// Prefill the info on the player data, as they will be used to populate the leadboard.
-- RectTransform: use UDim2 for positioning entriesRoot
	int entriesCount
	HighscoreUI playerEntry
	bool forcePlayerDisplay
	local displayPlayer = true
	local function Open()
	{
		.Parent(true)
		Populate()
end
	local function Close()
	{
		.Parent(false)
end
	local function Populate()
	{
		// Start by making all entries enabled & putting player entry last again.
		playerEntry.transform.SetAsLastSibling()
		for(local i = 0; i < entriesCount; ++i)
		{
			entriesRoot.GetChild(i)..Parent(true)
end
		// Find all index in local page space.
		local localStart = 0
		local place = -1
		local localPlace = -1
		if displayPlayer then
			place = PlayerData.instance.GetScorePlace(int.Parse(playerEntry.score.text))
			localPlace = place - localStart
end
		if localPlace >= 0  and  localPlace < entriesCount  and  displayPlayer then
			playerEntry..Parent(true)
			playerEntry.transform.SetSiblingIndex(localPlace)
end
		if (not forcePlayerDisplay  or  PlayerData.instance.#highscores < entriesCount)
			entriesRoot.GetChild(entriesRoot.:GetChildren() - 1)..Parent(false)
		local currentHighScore = localStart
		for (local i = 0; i < entriesCount; ++i)
		{
			HighscoreUI hs = entriesRoot.GetChild(i).:FindFirstChildOfClass<HighscoreUI>()
            if hs == playerEntry  or  hs == nil then
				// We skip the player entry.
				continue
end
		    if PlayerData.instance.#highscores > currentHighScore then
		        hs..Parent(true)
		        hs.playerName.text = PlayerData.instance.highscores[currentHighScore].name
		        hs.number.text = (localStart + i + 1).ToString()
		        hs.score.text = PlayerData.instance.highscores[currentHighScore].tostring(score)
		        currentHighScore++
end
		    else
		        hs..Parent(false)
end
		// If we force the player to be displayed, we enable it even if it was disabled from elsewhere
		if (forcePlayerDisplay) 
			playerEntry..Parent(true)
		playerEntry.number.text = (place + 1).ToString()
end
end