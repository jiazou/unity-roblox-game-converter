-- EscapePlane.lua — End-game plane trigger
-- Derived from: Plane.cs (renamed to avoid Roblox naming confusion)
-- When player with GasCan touches it, triggers win cutscene → restart
-- References: Player, GameManager
-- Bridge: none

local EscapePlane = {}
EscapePlane.__index = EscapePlane

function EscapePlane.new(config)
	config = config or {}
	local self = setmetatable({}, EscapePlane)

	self.model = config.model -- the plane Model in workspace
	self.gameManager = config.gameManager -- GameManager reference
	self.flyingPlanePrefab = config.flyingPlanePrefab -- template in ReplicatedStorage
	self._destroyed = false
	self._connections = {}

	return self
end

function EscapePlane:Init()
	if not self.model then return end

	local parts = {}
	if self.model:IsA("BasePart") then
		table.insert(parts, self.model)
	else
		for _, p in ipairs(self.model:GetDescendants()) do
			if p:IsA("BasePart") then
				table.insert(parts, p)
			end
		end
	end

	for _, part in ipairs(parts) do
		local conn = part.Touched:Connect(function(hit)
			if self._destroyed then return end
			local char = hit:FindFirstAncestorWhichIsA("Model")
			local humanoid = char and char:FindFirstChildWhichIsA("Humanoid")
			if humanoid then
				self:OnPlayerTouch()
			end
		end)
		table.insert(self._connections, conn)
	end
end

function EscapePlane:OnPlayerTouch()
	local Player = require(script.Parent:WaitForChild("Player"))
	if not Player.instance then return end

	-- Check if player has GasCan
	if not Player.instance:HasItem("GasCan") then return end

	self._destroyed = true

	-- Show win message
	local Players = game:GetService("Players")
	local playerGui = Players.LocalPlayer:WaitForChild("PlayerGui")

	local winGui = Instance.new("ScreenGui")
	winGui.Name = "WinScreen"
	winGui.IgnoreGuiInset = true
	winGui.Parent = playerGui

	local bg = Instance.new("Frame")
	bg.Size = UDim2.new(1, 0, 1, 0)
	bg.BackgroundColor3 = Color3.new(0, 0, 0)
	bg.BackgroundTransparency = 0.3
	bg.Parent = winGui

	local label = Instance.new("TextLabel")
	label.AnchorPoint = Vector2.new(0.5, 0.5)
	label.Position = UDim2.new(0.5, 0, 0.4, 0)
	label.Size = UDim2.new(0, 500, 0, 60)
	label.BackgroundTransparency = 1
	label.Text = "YOU ESCAPED!"
	label.TextColor3 = Color3.fromRGB(100, 255, 100)
	label.TextSize = 48
	label.Font = Enum.Font.GothamBold
	label.Parent = winGui

	local sub = Instance.new("TextLabel")
	sub.AnchorPoint = Vector2.new(0.5, 0.5)
	sub.Position = UDim2.new(0.5, 0, 0.55, 0)
	sub.Size = UDim2.new(0, 500, 0, 30)
	sub.BackgroundTransparency = 1
	sub.Text = "Restarting in 5 seconds..."
	sub.TextColor3 = Color3.fromRGB(180, 180, 180)
	sub.TextSize = 20
	sub.Font = Enum.Font.Gotham
	sub.Parent = winGui

	-- Restart after 5 seconds
	if self.gameManager then
		self.gameManager:RestartGame(5)
	end
end

function EscapePlane:Destroy()
	self._destroyed = true
	for _, conn in ipairs(self._connections) do
		conn:Disconnect()
	end
	self._connections = {}
end

return EscapePlane
