-- Door.lua — Key-activated door
-- Derived from: Door.cs
-- Opens when player with key enters trigger, closes when they leave
-- References: Player (checks hasKey)
-- Bridge: none

local TweenService = game:GetService("TweenService")

local Door = {}
Door.__index = Door

function Door.new(config)
	config = config or {}
	local self = setmetatable({}, Door)

	self.model = config.model -- Door model in workspace (trigger collider)
	self.doorPart = config.doorPart -- The actual moving door part
	self.closeTime = config.closeTime or 5
	self.isOpen = false
	self.openOffset = config.openOffset or Vector3.new(0, 5, 0) -- How far the door slides open
	self._closedCFrame = nil
	self._openCFrame = nil
	self._destroyed = false
	self._connections = {}

	return self
end

function Door:Init()
	if not self.model then return end

	-- Find the door part if not explicitly set
	if not self.doorPart then
		local parent = self.model
		if parent:IsA("BasePart") then
			parent = parent.Parent
		end
		self.doorPart = parent:FindFirstChild("door") or parent:FindFirstChild("Door")
		if self.doorPart and self.doorPart:IsA("Model") then
			self.doorPart = self.doorPart.PrimaryPart or self.doorPart:FindFirstChildWhichIsA("BasePart")
		end
	end

	if self.doorPart and self.doorPart:IsA("BasePart") then
		self._closedCFrame = self.doorPart.CFrame
		self._openCFrame = self.doorPart.CFrame + self.openOffset
	end

	-- Touch detection on trigger
	local triggerParts = {}
	if self.model:IsA("BasePart") then
		table.insert(triggerParts, self.model)
	else
		for _, p in ipairs(self.model:GetDescendants()) do
			if p:IsA("BasePart") then
				table.insert(triggerParts, p)
			end
		end
	end

	for _, part in ipairs(triggerParts) do
		local touchConn = part.Touched:Connect(function(hit)
			if self._destroyed then return end
			local char = hit:FindFirstAncestorWhichIsA("Model")
			local humanoid = char and char:FindFirstChildWhichIsA("Humanoid")
			if humanoid then
				self:OnPlayerEnter()
			end
		end)
		table.insert(self._connections, touchConn)

		local endConn = part.TouchEnded:Connect(function(hit)
			if self._destroyed then return end
			local char = hit:FindFirstAncestorWhichIsA("Model")
			local humanoid = char and char:FindFirstChildWhichIsA("Humanoid")
			if humanoid then
				self:OnPlayerExit()
			end
		end)
		table.insert(self._connections, endConn)
	end
end

function Door:OnPlayerEnter()
	local Player = require(script.Parent:WaitForChild("Player"))
	if not Player.instance then return end
	if Player.instance.gotKey then
		self:ToggleDoor(true)
	end
end

function Door:OnPlayerExit()
	local Player = require(script.Parent:WaitForChild("Player"))
	if not Player.instance then return end
	if Player.instance.gotKey then
		self:ToggleDoor(false)
	end
end

function Door:ToggleDoor(open)
	if not self.doorPart or not self.doorPart:IsA("BasePart") then return end
	if open == self.isOpen then return end
	self.isOpen = open

	local targetCFrame = open and self._openCFrame or self._closedCFrame
	if not targetCFrame then return end

	-- Tween the door
	local info = TweenInfo.new(0.5, Enum.EasingStyle.Quad, Enum.EasingDirection.Out)
	local tween = TweenService:Create(self.doorPart, info, {CFrame = targetCFrame})
	tween:Play()
end

function Door:Destroy()
	self._destroyed = true
	for _, conn in ipairs(self._connections) do
		conn:Disconnect()
	end
	self._connections = {}
end

return Door
