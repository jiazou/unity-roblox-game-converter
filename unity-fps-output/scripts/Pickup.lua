-- Pickup.lua — Collectible item with bobbing animation
-- Derived from: Pickup.cs
-- Bobbing up/down + spinning, triggers GetItem on player touch
-- References: Player (sends GetItem)
-- Bridge: none

local RunService = game:GetService("RunService")

local Pickup = {}
Pickup.__index = Pickup

function Pickup.new(config)
	config = config or {}
	local self = setmetatable({}, Pickup)

	self.itemName = config.itemName or "Item"
	self.rotationSpeed = config.rotationSpeed or 100
	self.model = config.model -- BasePart or Model in workspace
	self.bobSpeed = 0.5
	self.bobHeight = 0.5

	self._baseY = nil
	self._time = 0
	self._destroyed = false
	self._connections = {}

	return self
end

function Pickup:Init()
	if not self.model then return end

	-- Get base position
	local pos = self:_getPosition()
	if pos then
		self._baseY = pos.Y
	end

	-- Touch detection
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
				self:OnPickup()
			end
		end)
		table.insert(self._connections, conn)
	end

	-- Animation update
	local updateConn = RunService.Heartbeat:Connect(function(dt)
		if self._destroyed then return end
		self:Update(dt)
	end)
	table.insert(self._connections, updateConn)
end

function Pickup:Update(dt)
	if not self.model or not self.model.Parent then
		self:Destroy()
		return
	end

	self._time = self._time + dt

	-- Bob up and down
	local bobOffset = math.sin(self._time * math.pi * self.bobSpeed) * self.bobHeight

	-- Rotate
	local part = self:_getPrimaryPart()
	if part then
		local pos = part.Position
		local newY = (self._baseY or pos.Y) + bobOffset
		part.CFrame = CFrame.new(pos.X, newY, pos.Z) * CFrame.Angles(0, math.rad(self.rotationSpeed * self._time), 0)
	end
end

function Pickup:OnPickup()
	if self._destroyed then return end

	local Player = require(script.Parent:WaitForChild("Player"))
	if Player.instance then
		Player.instance:GetItem(self.itemName)
	end

	if self.model and self.model.Parent then
		self.model:Destroy()
	end
	self:Destroy()
end

function Pickup:_getPosition()
	local part = self:_getPrimaryPart()
	return part and part.Position
end

function Pickup:_getPrimaryPart()
	if self.model:IsA("BasePart") then
		return self.model
	elseif self.model:IsA("Model") then
		return self.model.PrimaryPart or self.model:FindFirstChildWhichIsA("BasePart")
	end
	return nil
end

function Pickup:Destroy()
	self._destroyed = true
	for _, conn in ipairs(self._connections) do
		conn:Disconnect()
	end
	self._connections = {}
end

return Pickup
