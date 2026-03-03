local RunService = game:GetService("RunService")

﻿using UnityEngine
AudioSource m_Source
	float m_TimeToDisable
    local k_StartDelay = 0.5f
	local function OnEnable()
	{
		m_Source = :FindFirstChildOfClass<AudioSource>()
		m_TimeToDisable = m_Source.clip.length
        m_Source.PlayDelayed(k_StartDelay)
end
	local function game:GetService('RunService').Heartbeat:Connect(function()
	{
		m_TimeToDisable -= dt
		if (m_TimeToDisable < 0)
			.Parent(false)
end
end