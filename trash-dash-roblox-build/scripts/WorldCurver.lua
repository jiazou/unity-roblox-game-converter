local RunService = game:GetService("RunService")

﻿using UnityEngine
[ExecuteInEditMode]
[Range(-0.1f, 0.1f)]
	local curveStrength = 0.01f
    int m_CurveStrengthID
    local function OnEnable()
    {
        m_CurveStrengthID = Shader.PropertyToID("_CurveStrength")
end
	local function game:GetService('RunService').Heartbeat:Connect(function()
	{
		Shader.SetGlobalFloat(m_CurveStrengthID, curveStrength)
end
end