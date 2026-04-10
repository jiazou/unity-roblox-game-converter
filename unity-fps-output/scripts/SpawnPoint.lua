-- SpawnPoint.lua — Checkpoint respawn system
-- Derived from: SpawnPoint.cs
-- Updates player spawn point when touched, optionally activates linked objects
-- References: Player (updates spawnpoint)
-- Bridge: none

local SpawnPoint = {}
SpawnPoint.__index = SpawnPoint

function SpawnPoint.new(config)
	config = config or {}
	local self = setmetatable({}, SpawnPoint)

	self.model = config.model -- BasePart or Model in workspace
	self.activateOnSpawn = config.activateOnSpawn -- Optional object to make visible
	self.triggered = false
	self._destroyed = false
	self._connections = {}

	return self
end

function SpawnPoint:Init()
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
			if self.triggered or self._destroyed then return end
			local char = hit:FindFirstAncestorWhichIsA("Model")
			local humanoid = char and char:FindFirstChildWhichIsA("Humanoid")
			if humanoid then
				self:OnPlayerEnter(part)
			end
		end)
		table.insert(self._connections, conn)
	end
end

function SpawnPoint:OnPlayerEnter(part)
	if self.triggered then return end
	self.triggered = true

	local Player = require(script.Parent:WaitForChild("Player"))
	if Player.instance then
		Player.instance:UpdateSpawnpoint(part.CFrame)
	end

	-- Activate linked object if any
	if self.activateOnSpawn then
		if self.activateOnSpawn:IsA("BasePart") then
			self.activateOnSpawn.Transparency = 0
			self.activateOnSpawn.CanCollide = true
		elseif self.activateOnSpawn:IsA("Model") then
			for _, desc in ipairs(self.activateOnSpawn:GetDescendants()) do
				if desc:IsA("BasePart") then
					desc.Transparency = 0
					desc.CanCollide = true
				end
			end
		end
	end

	self:Destroy()
end

function SpawnPoint:Destroy()
	self._destroyed = true
	for _, conn in ipairs(self._connections) do
		conn:Disconnect()
	end
	self._connections = {}
end

return SpawnPoint
