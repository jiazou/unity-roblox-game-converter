-- Mine.lua — Proximity mine with delayed explosion
-- Derived from: Mine.cs
-- Triggers when player enters radius, explodes after delay
-- References: Player (damage target)
-- Bridge: none

local Workspace = game:GetService("Workspace")

local Mine = {}
Mine.__index = Mine

function Mine.new(config)
	config = config or {}
	local self = setmetatable({}, Mine)

	self.explodeTime = config.explodeTime or 1
	self.damage = config.damage or 10
	self.blastRadius = config.blastRadius or 8 -- 2 Unity units * ~4 studs
	self.model = config.model -- BasePart or Model in workspace
	self.triggered = false
	self._destroyed = false
	self._connections = {}

	return self
end

function Mine:Init()
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
				self:Trigger()
			end
		end)
		table.insert(self._connections, conn)
	end
end

function Mine:Trigger()
	if self.triggered then return end
	self.triggered = true

	task.delay(self.explodeTime, function()
		self:Explode()
	end)
end

function Mine:Explode()
	if self._destroyed then return end

	local pos = nil
	if self.model:IsA("BasePart") then
		pos = self.model.Position
	elseif self.model:IsA("Model") and self.model.PrimaryPart then
		pos = self.model.PrimaryPart.Position
	else
		local firstPart = self.model:FindFirstChildWhichIsA("BasePart", true)
		pos = firstPart and firstPart.Position
	end

	if not pos then
		self:Destroy()
		return
	end

	-- Visual explosion
	local explosion = Instance.new("Explosion")
	explosion.Position = pos
	explosion.BlastRadius = self.blastRadius
	explosion.BlastPressure = 0
	explosion.Parent = Workspace

	-- Damage player if in range
	local Player = require(script.Parent:WaitForChild("Player"))
	if Player.instance and Player.instance.hrp then
		local dist = (Player.instance.hrp.Position - pos).Magnitude
		if dist <= self.blastRadius then
			Player.instance:TakeDamage(self.damage)
		end
	end

	-- Destroy the mine
	if self.model and self.model.Parent then
		self.model:Destroy()
	end
	self:Destroy()
end

function Mine:Destroy()
	self._destroyed = true
	for _, conn in ipairs(self._connections) do
		conn:Disconnect()
	end
	self._connections = {}
end

return Mine
