-- GameManager.lua — Game state and restart management
-- Derived from: GameManager.cs
-- Handles game restart via teleport service or respawn
-- References: none
-- Bridge: none

local Players = game:GetService("Players")
local TeleportService = game:GetService("TeleportService")

local GameManager = {}
GameManager.__index = GameManager

function GameManager.new(config)
	config = config or {}
	local self = setmetatable({}, GameManager)

	self.placeId = config.placeId or game.PlaceId
	self._destroyed = false

	return self
end

function GameManager:Init()
	-- Lock cursor for FPS
	local UserInputService = game:GetService("UserInputService")
	UserInputService.MouseBehavior = Enum.MouseBehavior.LockCenter
end

function GameManager:RestartGame(delayTime)
	delayTime = delayTime or 5

	task.spawn(function()
		task.wait(delayTime)
		if self._destroyed then return end

		-- Respawn player character
		local player = Players.LocalPlayer
		if player then
			local character = player.Character
			if character then
				local humanoid = character:FindFirstChildWhichIsA("Humanoid")
				if humanoid then
					humanoid.Health = 0
				end
			end
		end
	end)
end

function GameManager:Destroy()
	self._destroyed = true
end

return GameManager
