-- Machine.lua — Puzzle machine that collects batteries to open doors
-- Derived from: Machine.cs
-- Collect 3 batteries → opens doors + spawns GasCan
-- References: Player (checks items), Door (opens them)
-- Bridge: none

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Machine = {}
Machine.__index = Machine

function Machine.new(config)
	config = config or {}
	local self = setmetatable({}, Machine)

	self.model = config.model -- Machine model in workspace
	self.itemNames = config.itemNames or {"Battery", "SmallBattery", "MediumBattery"}
	self.doors = config.doors or {} -- List of Door module references
	self.itemSlots = {} -- Transform positions for placed items (child Parts named "Item 1", etc.)
	self.itemPlaced = {false, false, false}
	self.activated = 0
	self.gasCanTemplate = config.gasCanTemplate -- template Model for GasCan
	self._destroyed = false
	self._connections = {}

	return self
end

function Machine:Init()
	if not self.model then return end

	-- Find item placement slots
	for i = 1, 4 do
		local slot = self.model:FindFirstChild("Item " .. i, true)
		if slot then
			self.itemSlots[i] = slot
		end
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
				self:OnPlayerTouch()
			end
		end)
		table.insert(self._connections, conn)
	end
end

function Machine:OnPlayerTouch()
	local Player = require(script.Parent:WaitForChild("Player"))
	if not Player.instance then return end

	for i, name in ipairs(self.itemNames) do
		if Player.instance:HasItem(name) then
			self:PlaceItem(i)
		end
	end
end

function Machine:PlaceItem(number)
	if self.itemPlaced[number] then return end
	self.itemPlaced[number] = true
	self.activated = self.activated + 1

	-- Visual: could clone a battery model into the slot
	-- For now, change slot color to indicate placed
	local slot = self.itemSlots[self.activated]
	if slot and slot:IsA("BasePart") then
		slot.Color = Color3.fromRGB(0, 255, 0)
		slot.Material = Enum.Material.Neon
		slot.Transparency = 0
	end

	-- Open corresponding door
	if number <= #self.doors and self.doors[number] then
		self.doors[number]:ToggleDoor(true)
	end

	-- If all 3 batteries placed, spawn GasCan at slot 4
	if self.activated >= 3 then
		local slot4 = self.itemSlots[4]
		if slot4 and self.gasCanTemplate then
			local clone = self.gasCanTemplate:Clone()
			if slot4:IsA("BasePart") then
				if clone:IsA("Model") then
					clone:PivotTo(slot4.CFrame)
				elseif clone:IsA("BasePart") then
					clone.CFrame = slot4.CFrame
				end
			end
			clone.Parent = game.Workspace
		end
	end
end

function Machine:Destroy()
	self._destroyed = true
	for _, conn in ipairs(self._connections) do
		conn:Disconnect()
	end
	self._connections = {}
end

return Machine
