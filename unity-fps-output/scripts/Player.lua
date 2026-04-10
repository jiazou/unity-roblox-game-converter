-- Player.lua — Core FPS player module
-- Derived from: Player.cs
-- Manages: health, ammo, items, shooting (raycasting), respawn
-- References: HudControl (via events), SpawnPoint (sets respawn)
-- Bridge: none (uses Roblox-native APIs)

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")
local Workspace = game:GetService("Workspace")

local Player = {}
Player.__index = Player

-- Static config
Player.MAX_HEALTH = 100
Player.MAX_AMMO = 250

-- Singleton
Player.instance = nil

-- Event callbacks (set by HudControl)
Player.onHealthUpdate = nil   -- function(curHealth)
Player.onAmmoUpdate = nil     -- function(curAmmo)
Player.onItemUpdate = nil     -- function(itemName)
Player.onPauseEvent = nil     -- function(isPaused)

function Player.new(config)
	config = config or {}
	local self = setmetatable({}, Player)

	-- State
	self.curHealth = Player.MAX_HEALTH
	self.curAmmo = 0
	self.gotItems = {}
	self.gotWeapon = false
	self.gotKey = false
	self.spawnPoint = nil -- CFrame

	-- Config
	self.speed = config.speed or 6
	self.jumpSpeed = config.jumpSpeed or 50
	self.gravity = config.gravity or 196.2
	self.shootRange = config.shootRange or 100
	self.sensitivity = config.sensitivity or 200
	self.healAmount = config.healAmount or 25
	self.ammoAmount = config.ammoAmount or 40
	self.minAngle = config.minAngle or -30
	self.maxAngle = config.maxAngle or 45

	-- Roblox references (set during wiring)
	self.character = nil
	self.humanoid = nil
	self.hrp = nil
	self.camera = nil
	self.localPlayer = nil

	-- Internal
	self._connections = {}
	self._destroyed = false

	Player.instance = self
	return self
end

function Player:Init()
	local player = Players.LocalPlayer
	self.localPlayer = player
	self.character = player.Character or player.CharacterAdded:Wait()
	self.humanoid = self.character:WaitForChild("Humanoid")
	self.hrp = self.character:WaitForChild("HumanoidRootPart")
	self.camera = Workspace.CurrentCamera

	-- First person mode
	player.CameraMode = Enum.CameraMode.LockFirstPerson
	UserInputService.MouseBehavior = Enum.MouseBehavior.LockCenter

	-- Movement config
	self.humanoid.WalkSpeed = self.speed * 3 -- Unity speed to Roblox WalkSpeed
	self.humanoid.JumpPower = self.jumpSpeed
	self.humanoid.MaxHealth = math.huge -- We manage our own health

	-- Set initial spawn point
	self.spawnPoint = self.hrp.CFrame

	-- Wire shooting input
	local shootConn = UserInputService.InputBegan:Connect(function(input, processed)
		if processed then return end
		if input.UserInputType == Enum.UserInputType.MouseButton1 then
			self:Shoot()
		elseif input.KeyCode == Enum.KeyCode.Escape then
			self:TogglePause()
		end
	end)
	table.insert(self._connections, shootConn)

	-- Wire death/respawn
	local diedConn = self.humanoid.Died:Connect(function()
		self:Respawn()
	end)
	table.insert(self._connections, diedConn)
end

function Player:Shoot()
	if not self.gotWeapon then return end

	if self.curAmmo > 0 then
		self.curAmmo = self.curAmmo - 1
		if Player.onAmmoUpdate then
			Player.onAmmoUpdate(self.curAmmo)
		end

		-- Raycast from camera center
		local origin = self.camera.CFrame.Position
		local direction = self.camera.CFrame.LookVector * self.shootRange

		local rayParams = RaycastParams.new()
		rayParams.FilterDescendantsInstances = {self.character}
		rayParams.FilterType = Enum.RaycastFilterType.Exclude

		local result = Workspace:Raycast(origin, direction, rayParams)
		if result then
			local hitPart = result.Instance
			-- Find parent model/object that might have a TakeDamage handler
			local model = hitPart:FindFirstAncestorWhichIsA("Model")
			if model then
				local dmgValue = model:FindFirstChild("TakeDamageEvent")
				if dmgValue then
					dmgValue:Fire()
				end
			end
			-- Also check for tag-based damage
			self:_sendDamageToHit(hitPart)

			-- Hit feedback: brief part flash
			self:_createHitEffect(result.Position)
		end
	else
		-- Dry fire (no ammo) - could play sound
	end
end

function Player:_sendDamageToHit(hitPart)
	-- Walk up hierarchy looking for a "Damageable" attribute or script
	local current = hitPart
	for _ = 1, 5 do
		if current == nil then break end
		if current:GetAttribute("Damageable") then
			local dmg = current:GetAttribute("Health")
			if dmg then
				current:SetAttribute("Health", dmg - 1)
			end
			break
		end
		current = current.Parent
	end
end

function Player:_createHitEffect(position)
	-- Simple hit marker: small part that fades
	local part = Instance.new("Part")
	part.Size = Vector3.new(0.3, 0.3, 0.3)
	part.Position = position
	part.Anchored = true
	part.CanCollide = false
	part.BrickColor = BrickColor.new("Bright yellow")
	part.Material = Enum.Material.Neon
	part.Parent = Workspace
	task.delay(0.15, function()
		if part and part.Parent then
			part:Destroy()
		end
	end)
end

function Player:TakeDamage(amount)
	self.curHealth = self.curHealth - amount
	if self.curHealth <= 0 then
		self:Respawn()
		self.curHealth = Player.MAX_HEALTH
	end
	if Player.onHealthUpdate then
		Player.onHealthUpdate(self.curHealth)
	end
end

function Player:Respawn()
	if self.spawnPoint and self.hrp then
		self.hrp.CFrame = self.spawnPoint
	end
	self.curHealth = Player.MAX_HEALTH
	if Player.onHealthUpdate then
		Player.onHealthUpdate(self.curHealth)
	end
end

function Player:UpdateSpawnpoint(cf)
	self.spawnPoint = cf
end

function Player:RecoverHealth()
	if self.curHealth >= Player.MAX_HEALTH then return end
	self.curHealth = math.min(self.curHealth + self.healAmount, Player.MAX_HEALTH)
	if Player.onHealthUpdate then
		Player.onHealthUpdate(self.curHealth)
	end
end

function Player:TakeAmmo(amount)
	self.curAmmo = math.min(self.curAmmo + amount, Player.MAX_AMMO)
	if Player.onAmmoUpdate then
		Player.onAmmoUpdate(self.curAmmo)
	end
end

function Player:GetRifle()
	self.gotWeapon = true
	self:TakeAmmo(20)
	-- Visual: could attach a weapon model to camera, skipped for now
end

function Player:GetItem(itemName)
	if itemName == "Key" then
		self.gotKey = true
	elseif itemName == "Rifle" then
		self:GetRifle()
		return
	elseif itemName == "Health" then
		self:RecoverHealth()
		return
	elseif itemName == "Ammo" then
		self:TakeAmmo(self.ammoAmount)
		return
	else
		table.insert(self.gotItems, itemName)
		if Player.onItemUpdate then
			Player.onItemUpdate(itemName)
		end
		return
	end
	-- For Key
	if Player.onItemUpdate then
		Player.onItemUpdate(itemName)
	end
end

function Player:HasItem(itemName)
	for _, v in ipairs(self.gotItems) do
		if v == itemName then return true end
	end
	return false
end

function Player:TogglePause()
	if Player.onPauseEvent then
		Player.onPauseEvent(true) -- HudControl handles toggle logic
	end
end

function Player:Destroy()
	self._destroyed = true
	for _, conn in ipairs(self._connections) do
		conn:Disconnect()
	end
	self._connections = {}
	Player.instance = nil
end

return Player
