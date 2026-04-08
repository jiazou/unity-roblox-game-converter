-- HostilePlane.lua — Enemy plane that periodically shoots at the player
-- Derived from: HostilePlane.cs
-- References: Player (target), PlaneBullet (spawns projectiles)
-- Bridge: none

local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local HostilePlane = {}
HostilePlane.__index = HostilePlane

function HostilePlane.new(config)
	config = config or {}
	local self = setmetatable({}, HostilePlane)

	self.shootTimer = config.shootTimer or 5
	self.bulletSpeed = config.bulletSpeed or 200
	self.bulletDamage = config.bulletDamage or 10
	self.model = config.model -- Model in workspace
	self.origin = nil -- origin part (child named "Origin")

	self._destroyed = false
	self._connections = {}

	return self
end

function HostilePlane:Init()
	if not self.model then return end

	-- Find the origin point for bullets
	self.origin = self.model:FindFirstChild("Origin", true)

	-- Start shooting loop
	task.spawn(function()
		while not self._destroyed do
			task.wait(self.shootTimer)
			if self._destroyed then break end
			self:Shoot()
		end
	end)

	-- Aim at player each frame
	local aimConn = RunService.Heartbeat:Connect(function(dt)
		if self._destroyed then return end
		self:AimAtPlayer()
	end)
	table.insert(self._connections, aimConn)
end

function HostilePlane:AimAtPlayer()
	if not self.origin or not self.origin:IsA("BasePart") then return end

	local Player = require(script.Parent:WaitForChild("Player"))
	if not Player.instance or not Player.instance.hrp then return end

	local targetPos = Player.instance.hrp.Position + Vector3.new(0, 2, 0)
	self.origin.CFrame = CFrame.lookAt(self.origin.Position, targetPos)
end

function HostilePlane:Shoot()
	if not self.origin or not self.origin:IsA("BasePart") then return end

	local Player = require(script.Parent:WaitForChild("Player"))
	if not Player.instance or not Player.instance.hrp then return end

	local originCF = self.origin.CFrame

	-- Create bullet
	local bullet = Instance.new("Part")
	bullet.Name = "PlaneBullet"
	bullet.Size = Vector3.new(0.5, 0.5, 1.5)
	bullet.CFrame = originCF
	bullet.Color = Color3.fromRGB(255, 50, 50)
	bullet.Material = Enum.Material.Neon
	bullet.Anchored = false
	bullet.CanCollide = true
	bullet.Parent = Workspace

	local velocity = Instance.new("BodyVelocity")
	velocity.Velocity = originCF.LookVector * self.bulletSpeed
	velocity.MaxForce = Vector3.new(math.huge, math.huge, math.huge)
	velocity.Parent = bullet

	-- On collision: area explosion
	bullet.Touched:Connect(function(hit)
		if hit:IsDescendantOf(self.model) then return end
		self:_bulletExplode(bullet)
	end)

	-- Auto-destroy after fade time
	task.delay(6, function()
		if bullet and bullet.Parent then
			bullet:Destroy()
		end
	end)
end

function HostilePlane:_bulletExplode(bullet)
	if not bullet or not bullet.Parent then return end
	local pos = bullet.Position

	-- Visual explosion
	local explosion = Instance.new("Explosion")
	explosion.Position = pos
	explosion.BlastRadius = 8
	explosion.BlastPressure = 0
	explosion.Parent = Workspace

	-- Damage player if nearby
	local Player = require(script.Parent:WaitForChild("Player"))
	if Player.instance and Player.instance.hrp then
		local dist = (Player.instance.hrp.Position - pos).Magnitude
		if dist <= 8 then
			Player.instance:TakeDamage(self.bulletDamage)
		end
	end

	bullet:Destroy()
end

function HostilePlane:Destroy()
	self._destroyed = true
	for _, conn in ipairs(self._connections) do
		conn:Disconnect()
	end
	self._connections = {}
end

return HostilePlane
