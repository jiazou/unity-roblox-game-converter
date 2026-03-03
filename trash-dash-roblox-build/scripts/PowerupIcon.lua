local RunService = game:GetService("RunService")

﻿using UnityEngine
[HideInInspector]
    Consumable linkedConsumable
    Image icon
    Slider slider
	local function function script.Parent.AncestryChanged
    { 
        icon.sprite = linkedConsumable.icon
end
    local function game:GetService('RunService').Heartbeat:Connect(function()
    {
        slider.value = 1.0f - linkedConsumable.timeActive / linkedConsumable.duration
end
end