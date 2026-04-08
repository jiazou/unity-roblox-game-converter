-- GameBootstrap.lua — Entry point LocalScript (StarterPlayerScripts)
-- Wires all modules together, mirrors Unity's Inspector references
-- Does NOT contain game logic — pure wiring only

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

-- Wait for character
local player = Players.LocalPlayer
local character = player.Character or player.CharacterAdded:Wait()
local humanoid = character:WaitForChild("Humanoid")
local hrp = character:WaitForChild("HumanoidRootPart")

-- ============================================================================
-- Module requires
-- ============================================================================
local scriptsFolder = ReplicatedStorage:WaitForChild("GameScripts")

local Player = require(scriptsFolder:WaitForChild("Player"))
local HudControl = require(scriptsFolder:WaitForChild("HudControl"))
local GameManager = require(scriptsFolder:WaitForChild("GameManager"))
local Turret = require(scriptsFolder:WaitForChild("Turret"))
local Mine = require(scriptsFolder:WaitForChild("Mine"))
local Pickup = require(scriptsFolder:WaitForChild("Pickup"))
local HostilePlane = require(scriptsFolder:WaitForChild("HostilePlane"))
local EscapePlane = require(scriptsFolder:WaitForChild("EscapePlane"))
local Machine = require(scriptsFolder:WaitForChild("Machine"))
local Door = require(scriptsFolder:WaitForChild("Door"))
local SpawnPoint = require(scriptsFolder:WaitForChild("SpawnPoint"))
local Menu = require(scriptsFolder:WaitForChild("Menu"))

-- ============================================================================
-- Helper: find objects in workspace by name pattern
-- ============================================================================
local function findByName(parent, name)
	for _, child in ipairs(parent:GetChildren()) do
		if child.Name == name then
			return child
		end
	end
	-- Recursive search
	return parent:FindFirstChild(name, true)
end

local function findAllByAttribute(parent, attr, value)
	local results = {}
	for _, desc in ipairs(parent:GetDescendants()) do
		if desc:GetAttribute(attr) == value then
			table.insert(results, desc)
		end
	end
	return results
end

local function findAllByName(parent, name)
	local results = {}
	for _, desc in ipairs(parent:GetDescendants()) do
		if desc.Name == name then
			table.insert(results, desc)
		end
	end
	return results
end

-- ============================================================================
-- Game state
-- ============================================================================
local gameStarted = false
local allTurrets = {}
local allPickups = {}
local allMines = {}
local allHostilePlanes = {}
local allSpawnPoints = {}
local allDoors = {}
local heartbeatConn = nil

-- ============================================================================
-- Initialize game systems
-- ============================================================================
local function startGame()
	if gameStarted then return end
	gameStarted = true

	-- 1. First-person camera
	player.CameraMode = Enum.CameraMode.LockFirstPerson
	UserInputService.MouseBehavior = Enum.MouseBehavior.LockCenter

	-- 2. Create core modules
	local gameManager = GameManager.new({})
	gameManager:Init()

	local playerModule = Player.new({
		speed = 6,
		jumpSpeed = 50,
		gravity = 196.2,
		shootRange = 200,
		sensitivity = 200,
		healAmount = 25,
		ammoAmount = 40,
	})
	playerModule:Init()

	local hudControl = HudControl.new({ player = Player })
	hudControl:Init()

	-- 3. Discover and wire scene objects
	-- Turrets
	local turretModels = findAllByName(Workspace, "Turret")
	for _, model in ipairs(turretModels) do
		if model:IsA("Model") or model:IsA("BasePart") then
			local turret = Turret.new({
				model = model,
				sightRadius = 50,
				rotationSpeed = 125,
				shootCooldown = 1,
				maxHealth = 5,
			})
			turret:Init()
			table.insert(allTurrets, turret)
		end
	end

	-- Mines
	local mineModels = findAllByName(Workspace, "Mine")
	for _, m in ipairs(findAllByName(Workspace, "at_mine")) do
		table.insert(mineModels, m)
	end
	for _, model in ipairs(mineModels) do
		local mine = Mine.new({
			model = model,
			damage = 25,
			explodeTime = 1,
		})
		mine:Init()
		table.insert(allMines, mine)
	end

	-- Pickups (items with "Pickup" in name or specific known names)
	local pickupNames = {
		{name = "RiflePickup", item = "Rifle"},
		{name = "KeyPickup", item = "Key"},
		{name = "HealthPickup", item = "Health"},
		{name = "AmmoPickup", item = "Ammo"},
		{name = "BatteryPickup", item = "Battery"},
		{name = "SmallBatteryPickup", item = "SmallBattery"},
		{name = "MediumBatteryPickup", item = "MediumBattery"},
		{name = "GasPickup", item = "GasCan"},
		{name = "BasePickup", item = "Base"},
	}
	for _, def in ipairs(pickupNames) do
		local models = findAllByName(Workspace, def.name)
		for _, model in ipairs(models) do
			local pickup = Pickup.new({
				model = model,
				itemName = def.item,
			})
			pickup:Init()
			table.insert(allPickups, pickup)
		end
	end

	-- Also find any Pickup tagged objects
	for _, desc in ipairs(Workspace:GetDescendants()) do
		if desc:GetAttribute("PickupItem") then
			local pickup = Pickup.new({
				model = desc,
				itemName = desc:GetAttribute("PickupItem"),
			})
			pickup:Init()
			table.insert(allPickups, pickup)
		end
	end

	-- Hostile planes
	local planeModels = findAllByName(Workspace, "HostilePlane")
	for _, model in ipairs(planeModels) do
		if model:IsA("Model") then
			local hp = HostilePlane.new({
				model = model,
				shootTimer = 5,
				bulletDamage = 10,
			})
			hp:Init()
			table.insert(allHostilePlanes, hp)
		end
	end

	-- Spawn points
	local spawnModels = findAllByName(Workspace, "SpawnPoint")
	for _, model in ipairs(spawnModels) do
		local sp = SpawnPoint.new({
			model = model,
		})
		sp:Init()
		table.insert(allSpawnPoints, sp)
	end

	-- Doors
	local doorModels = findAllByName(Workspace, "Door")
	for _, model in ipairs(doorModels) do
		local door = Door.new({
			model = model,
			openOffset = Vector3.new(0, 5, 0),
		})
		door:Init()
		table.insert(allDoors, door)
	end

	-- Machine
	local machineModel = findByName(Workspace, "Machine")
	if machineModel then
		local machine = Machine.new({
			model = machineModel,
			doors = allDoors,
			itemNames = {"Battery", "SmallBattery", "MediumBattery"},
		})
		machine:Init()
	end

	-- Escape Plane
	local planeModel = findByName(Workspace, "Plane") or findByName(Workspace, "PlaneHolder")
	if planeModel then
		local escapePlane = EscapePlane.new({
			model = planeModel,
			gameManager = gameManager,
		})
		escapePlane:Init()
	end

	-- 4. Heartbeat for turret updates
	heartbeatConn = RunService.Heartbeat:Connect(function(dt)
		for _, turret in ipairs(allTurrets) do
			turret:Update(dt)
		end
	end)

	-- 5. Initial HUD state
	hudControl:UpdateHealth(Player.MAX_HEALTH)
	hudControl:UpdateAmmo(0)
end

-- ============================================================================
-- Show menu first, then start game
-- ============================================================================
local menu = Menu.new({
	onStartGame = function()
		startGame()
	end,
})
menu:Init()
