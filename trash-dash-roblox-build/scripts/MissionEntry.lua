using UnityEngine
Text descText
    Text rewardText
    Button claimButton
    Text progressText
	Image background
	Color notCompletedColor
	Color completedColor
    local function FillWithMission(MissionBase m, MissionUI owner)
    {
        descText.text = m.GetMissionDesc()
        rewardText.text = m.tostring(reward)
        if m.isComplete then
            claimButton..Parent(true)
            progressText..Parent(false)
			background.color = completedColor
			progressText.color = Color3.new(1, 1, 1)
			descText.color = Color3.new(1, 1, 1)
			rewardText.color = Color3.new(1, 1, 1)
			claimButton.onClick.AddListener(delegate { owner.Claim(m); } )
        else
            claimButton..Parent(false)
            progressText..Parent(true)
			background.color = notCompletedColor
			progressText.color = Color3.new(0, 0, 0)
			descText.color = completedColor
			progressText.text = (m.progress) .. " / " .. (m.max)
end
end
end