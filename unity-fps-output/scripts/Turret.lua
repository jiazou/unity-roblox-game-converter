-- Turret.lua — Enemy turret AI with 3 states
-- Derived from: Turret.cs
-- States: Default (rotating scan), Engaged (tracking+shooting), Search (waiting)
-- References: TurretBullet (spawns projectiles), Player (target)
-- Bridge: none

local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local Turret = {}
Turret.__index = Turret

-- State enum
Turret.State = {
	Default = "Default",
	Engaged = "Engaged",
	Search = "Search",
}

function Turret.new(config)
	config = config or {}
	local self = setmetatable({}, Turret)

	-- Config
	self.rotate = config.rotate ~= false
	self.rotationSpeed = config.rotationSpeed or 125
	self.engagedSpeed = config.engagedSpeed or 2.5
	self.shootCooldown = config.shootCooldown or 1
	self.maxHealth = config.maxHealth or 5
	self.searchTime = config.searchTime or 3
	self.bulletTemplate = config.bulletTemplate -- Model in ReplicatedStorage

	-- References
	self.model = config.model -- Turret Model in workspace
	self.tBase = nil -- base child
	self.tWeapon = nil -- weapon child of base
	self.tOrigin = nil -- bullet origin child of weapon
	self.sightRadius = config.sightRadius or 30

	-- State
	self.state = Turret.State.Default
	self.health = self.maxHealth
	self.target = nil
	self.rotateDir = if math.random() > 0.5 then 1 else -1
	self._destroyed = false
	self._connections = {}
	self._shootThread = nil

	return self
end

function Turret:Init()
	if not self.model then return end

	-- Find turret sub-parts
	self.tBase = self.model:FindFirstChild("Base") or self.model:FindFirstChildWhichIsA("Model")
	if self.tBase then
		self.tWeapon = self.tBase:FindFirstChild("Weapon") or self.tBase:FindFirstChildWhichIsA("Model")
		if self.tWeapon then
			self.tOrigin = self.tWeapon:FindFirstChild("Origin") or self.tWeapon:FindFirstChildWhichIsA("BasePart")
		end
	end

	-- Mark as damageable
	self.model:SetAttribute("Damageable", true)
	self.model:SetAttribute("Health", self.maxHealth)

	-- Listen for health changes (damage from player raycasts)
	local conn = self.model:GetAttributeChangedSignal("Health"):Connect(function()
		local hp = self.model:GetAttribute("Health")
		if hp ~= self.health then
			self.health = hp
			if self.health <= 0 then
				self:Die()
			end
		end
	end)
	table.insert(self._connections, conn)

	-- Start default rotation behavior
	self:_startDefaultUpdate()

	-- Heartbeat for detection
	local detectConn = RunService.Heartbeat:Connect(function(dt)
		if self._destroyed then return end
		self:_detectPlayer(dt)
	end)
	table.insert(self._connections, detectConn)
end

function Turret:_detectPlayer(dt)
	if self.state == Turret.State.Engaged then return end

	local Player = require(script.Parent:WaitForChild("Player"))
	local playerInst = Player.instance
	if not playerInst or not playerInst.hrp then return end

	local basePos = self:_getBasePosition()
	if not basePos then return end

	local playerPos = playerInst.hrp.Position
	local dir = playerPos - basePos
	local dist = dir.Magnitude

	if dist > self.sightRadius then return end

	-- Angle check (within 55 degrees of forward)
	local baseCF = self:_getBaseCFrame()
	if not baseCF then return end
	local forward = baseCF.LookVector
	local angle = math.deg(math.acos(math.clamp(forward:Dot(dir.Unit), -1, 1)))
	if angle > 55 then return end

	-- Raycast to verify line of sight
	local rayParams = RaycastParams.new()
	rayParams.FilterDescendantsInstances = {self.model}
	rayParams.FilterType = Enum.RaycastFilterType.Exclude

	local result = Workspace:Raycast(basePos, dir.Unit * dist, rayParams)
	if result then
		local hitModel = result.Instance:FindFirstAncestorWhichIsA("Model")
		if hitModel and hitModel == playerInst.character then
			self:_startEngagedUpdate(playerInst)
		end
	end
end

function Turret:_startDefaultUpdate()
	self.state = Turret.State.Default
	self.target = nil
end

function Turret:_startEngagedUpdate(playerRef)
	self.state = Turret.State.Engaged
	self.target = playerRef

	-- Start shooting loop
	self._shootThread = task.spawn(function()
		task.wait(self.shootCooldown)
		while self.state == Turret.State.Engaged and not self._destroyed do
			self:_fireBullet()
			task.wait(self.shootCooldown)
		end
	end)
end

function Turret:_startSearchUpdate()
	self.state = Turret.State.Search
	self.target = nil

	task.spawn(function()
		local elapsed = 0
		while self.state == Turret.State.Search and elapsed < self.searchTime and not self._destroyed do
			elapsed = elapsed + task.wait()
		end
		if self.state == Turret.State.Search and not self._destroyed then
			self:_startDefaultUpdate()
		end
	end)
end

function Turret:Update(dt)
	if self._destroyed then return end

	if self.state == Turret.State.Default then
		if self.rotate and self.tBase then
			local basePart = self:_getBasePrimaryPart()
			if basePart then
				basePart.CFrame = basePart.CFrame * CFrame.Angles(0, math.rad(self.rotateDir * self.rotationSpeed * dt), 0)
			end
		end
	elseif self.state == Turret.State.Engaged then
		if self.target and self.target.hrp and self.tBase then
			local basePos = self:_getBasePosition()
			local targetPos = self.target.hrp.Position
			if basePos then
				local dir = (targetPos - basePos).Unit
				local lookCF = CFrame.lookAt(basePos, basePos + dir)
				local basePart = self:_getBasePrimaryPart()
				if basePart then
					basePart.CFrame = basePart.CFrame:Lerp(lookCF, dt * self.engagedSpeed)
				end
			end
		else
			-- Lost target
			self:_startSearchUpdate()
		end
	end
end

function Turret:_fireBullet()
	if not self.bulletTemplate or not self.tOrigin then return end

	local origin = if self.tOrigin:IsA("BasePart") then self.tOrigin.CFrame
		else self:_getBaseCFrame()
	if not origin then return end

	-- Create a simple projectile
	local bullet = Instance.new("Part")
	bullet.Name = "TurretBullet"
	bullet.Size = Vector3.new(0.3, 0.3, 1)
	bullet.CFrame = origin
	bullet.Color = Color3.fromRGB(255, 100, 0)
	bullet.Material = Enum.Material.Neon
	bullet.Anchored = false
	bullet.CanCollide = true
	bullet.Parent = Workspace

	local velocity = Instance.new("BodyVelocity")
	velocity.Velocity = origin.LookVector * 60
	velocity.MaxForce = Vector3.new(math.huge, math.huge, math.huge)
	velocity.Parent = bullet

	-- Collision detection
	bullet.Touched:Connect(function(hit)
		if hit:IsDescendantOf(self.model) then return end
		local char = hit:FindFirstAncestorWhichIsA("Model")
		local humanoid = char and char:FindFirstChildWhichIsA("Humanoid")
		if humanoid then
			local Player = require(script.Parent:WaitForChild("Player"))
			if Player.instance then
				Player.instance:TakeDamage(10)
			end
		end
		bullet:Destroy()
	end)

	-- Auto-destroy after 3 seconds
	task.delay(3, function()
		if bullet and bullet.Parent then
			bullet:Destroy()
		end
	end)
end

function Turret:Die()
	self._destroyed = true
	-- Simple explosion effect
	local pos = self:_getBasePosition()
	if pos then
		local explosion = Instance.new("Explosion")
		explosion.Position = pos
		explosion.BlastRadius = 5
		explosion.BlastPressure = 0 -- Visual only
		explosion.Parent = Workspace
	end
	if self.model then
		self.model:Destroy()
	end
	self:Destroy()
end

function Turret:_getBasePrimaryPart(  )
	if self.tBase and self.tBase:IsA("Model") then
		return self.tBase.PrimaryPart or self.tBase:FindFirstChildWhichIsA("BasePart")
	elseif self.tBase and self.tBase:IsA("BasePart") then
		return self.tBase
	end
	return nil
end

function Turret:_getBasePosition()
	local part = self:_getBasePrimaryPart()
	return part and part.Position
end

function Turret:_getBaseCFrame()
	local part = self:_getBasePrimaryPart()
	return part and part.CFrame
end

function Turret:Destroy()
	self._destroyed = true
	for _, conn in ipairs(self._connections) do
		conn:Disconnect()
	end
	self._connections = {}
end

return Turret
