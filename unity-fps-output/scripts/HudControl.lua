-- HudControl.lua — HUD/UI management
-- Derived from: HudControl.cs
-- Manages: health bar, ammo display, item checklist, pause menu
-- References: Player (subscribes to events)
-- Bridge: none

local Players = game:GetService("Players")
local StarterGui = game:GetService("StarterGui")

local HudControl = {}
HudControl.__index = HudControl

function HudControl.new(config)
	config = config or {}
	local self = setmetatable({}, HudControl)

	self.player = config.player -- Player module reference
	self.screenGui = nil
	self.healthBar = nil
	self.healthFill = nil
	self.ammoLabel = nil
	self.ammoTotalLabel = nil
	self.itemChecks = {}
	self.pauseFrame = nil
	self.isPaused = false
	self.crosshair = nil

	return self
end

function HudControl:Init()
	local playerGui = Players.LocalPlayer:WaitForChild("PlayerGui")

	-- Create ScreenGui
	self.screenGui = Instance.new("ScreenGui")
	self.screenGui.Name = "FPS_HUD"
	self.screenGui.ResetOnSpawn = false
	self.screenGui.IgnoreGuiInset = true
	self.screenGui.Parent = playerGui

	self:_createCrosshair()
	self:_createHealthBar()
	self:_createAmmoDisplay()
	self:_createItemModule()
	self:_createPauseMenu()

	-- Subscribe to Player events
	local PlayerModule = self.player
	PlayerModule.onHealthUpdate = function(hp)
		self:UpdateHealth(hp)
	end
	PlayerModule.onAmmoUpdate = function(ammo)
		self:UpdateAmmo(ammo)
	end
	PlayerModule.onItemUpdate = function(name)
		self:UpdateItem(name)
	end
	PlayerModule.onPauseEvent = function()
		self:TogglePause()
	end
end

function HudControl:_createCrosshair()
	local crosshair = Instance.new("Frame")
	crosshair.Name = "Crosshair"
	crosshair.AnchorPoint = Vector2.new(0.5, 0.5)
	crosshair.Position = UDim2.new(0.5, 0, 0.5, 0)
	crosshair.Size = UDim2.new(0, 2, 0, 2)
	crosshair.BackgroundColor3 = Color3.new(1, 1, 1)
	crosshair.BorderSizePixel = 0
	crosshair.Parent = self.screenGui

	-- Horizontal line
	local hLine = Instance.new("Frame")
	hLine.AnchorPoint = Vector2.new(0.5, 0.5)
	hLine.Position = UDim2.new(0.5, 0, 0.5, 0)
	hLine.Size = UDim2.new(0, 20, 0, 2)
	hLine.BackgroundColor3 = Color3.new(1, 1, 1)
	hLine.BorderSizePixel = 0
	hLine.Parent = self.screenGui

	-- Vertical line
	local vLine = Instance.new("Frame")
	vLine.AnchorPoint = Vector2.new(0.5, 0.5)
	vLine.Position = UDim2.new(0.5, 0, 0.5, 0)
	vLine.Size = UDim2.new(0, 2, 0, 20)
	vLine.BackgroundColor3 = Color3.new(1, 1, 1)
	vLine.BorderSizePixel = 0
	vLine.Parent = self.screenGui

	self.crosshair = crosshair
end

function HudControl:_createHealthBar()
	local container = Instance.new("Frame")
	container.Name = "HealthContainer"
	container.AnchorPoint = Vector2.new(0, 1)
	container.Position = UDim2.new(0, 20, 1, -20)
	container.Size = UDim2.new(0, 250, 0, 25)
	container.BackgroundColor3 = Color3.fromRGB(40, 40, 40)
	container.BorderSizePixel = 0
	container.Parent = self.screenGui

	local corner = Instance.new("UICorner")
	corner.CornerRadius = UDim.new(0, 4)
	corner.Parent = container

	local fill = Instance.new("Frame")
	fill.Name = "Fill"
	fill.Size = UDim2.new(1, 0, 1, 0)
	fill.BackgroundColor3 = Color3.fromRGB(220, 50, 50)
	fill.BorderSizePixel = 0
	fill.Parent = container

	local fillCorner = Instance.new("UICorner")
	fillCorner.CornerRadius = UDim.new(0, 4)
	fillCorner.Parent = fill

	local label = Instance.new("TextLabel")
	label.Name = "Label"
	label.Size = UDim2.new(1, 0, 1, 0)
	label.BackgroundTransparency = 1
	label.Text = "HEALTH"
	label.TextColor3 = Color3.new(1, 1, 1)
	label.TextSize = 14
	label.Font = Enum.Font.GothamBold
	label.Parent = container

	self.healthBar = container
	self.healthFill = fill
end

function HudControl:_createAmmoDisplay()
	local container = Instance.new("Frame")
	container.Name = "AmmoContainer"
	container.AnchorPoint = Vector2.new(1, 1)
	container.Position = UDim2.new(1, -20, 1, -20)
	container.Size = UDim2.new(0, 150, 0, 50)
	container.BackgroundColor3 = Color3.fromRGB(40, 40, 40)
	container.BackgroundTransparency = 0.3
	container.BorderSizePixel = 0
	container.Parent = self.screenGui

	local corner = Instance.new("UICorner")
	corner.CornerRadius = UDim.new(0, 4)
	corner.Parent = container

	local cur = Instance.new("TextLabel")
	cur.Name = "Current"
	cur.Size = UDim2.new(0.6, 0, 1, 0)
	cur.BackgroundTransparency = 1
	cur.Text = "0"
	cur.TextColor3 = Color3.new(1, 1, 1)
	cur.TextSize = 28
	cur.Font = Enum.Font.GothamBold
	cur.TextXAlignment = Enum.TextXAlignment.Right
	cur.Parent = container

	local sep = Instance.new("TextLabel")
	sep.Name = "Sep"
	sep.Position = UDim2.new(0.6, 0, 0, 0)
	sep.Size = UDim2.new(0.1, 0, 1, 0)
	sep.BackgroundTransparency = 1
	sep.Text = "/"
	sep.TextColor3 = Color3.fromRGB(150, 150, 150)
	sep.TextSize = 20
	sep.Font = Enum.Font.Gotham
	sep.Parent = container

	local total = Instance.new("TextLabel")
	total.Name = "Total"
	total.Position = UDim2.new(0.7, 0, 0, 0)
	total.Size = UDim2.new(0.3, 0, 1, 0)
	total.BackgroundTransparency = 1
	total.Text = tostring(250) -- MAX_AMMO
	total.TextColor3 = Color3.fromRGB(150, 150, 150)
	total.TextSize = 16
	total.Font = Enum.Font.Gotham
	total.TextXAlignment = Enum.TextXAlignment.Left
	total.Parent = container

	self.ammoLabel = cur
	self.ammoTotalLabel = total
end

function HudControl:_createItemModule()
	local container = Instance.new("Frame")
	container.Name = "ItemModule"
	container.AnchorPoint = Vector2.new(1, 0)
	container.Position = UDim2.new(1, -20, 0, 20)
	container.Size = UDim2.new(0, 180, 0, 130)
	container.BackgroundColor3 = Color3.fromRGB(40, 40, 40)
	container.BackgroundTransparency = 0.3
	container.BorderSizePixel = 0
	container.Parent = self.screenGui

	local corner = Instance.new("UICorner")
	corner.CornerRadius = UDim.new(0, 4)
	corner.Parent = container

	local title = Instance.new("TextLabel")
	title.Size = UDim2.new(1, 0, 0, 25)
	title.BackgroundTransparency = 1
	title.Text = "ITEMS"
	title.TextColor3 = Color3.new(1, 1, 1)
	title.TextSize = 14
	title.Font = Enum.Font.GothamBold
	title.Parent = container

	local items = {"Battery", "SmallBattery", "MediumBattery", "GasCan", "Key"}
	for i, name in ipairs(items) do
		local row = Instance.new("TextLabel")
		row.Name = name
		row.Position = UDim2.new(0, 10, 0, 20 + (i - 1) * 20)
		row.Size = UDim2.new(1, -20, 0, 18)
		row.BackgroundTransparency = 1
		row.Text = "[ ] " .. name
		row.TextColor3 = Color3.fromRGB(150, 150, 150)
		row.TextSize = 13
		row.Font = Enum.Font.Gotham
		row.TextXAlignment = Enum.TextXAlignment.Left
		row.Parent = container
		self.itemChecks[name] = row
	end
end

function HudControl:_createPauseMenu()
	local frame = Instance.new("Frame")
	frame.Name = "PauseMenu"
	frame.Size = UDim2.new(1, 0, 1, 0)
	frame.BackgroundColor3 = Color3.new(0, 0, 0)
	frame.BackgroundTransparency = 0.5
	frame.Visible = false
	frame.Parent = self.screenGui

	local label = Instance.new("TextLabel")
	label.AnchorPoint = Vector2.new(0.5, 0.5)
	label.Position = UDim2.new(0.5, 0, 0.4, 0)
	label.Size = UDim2.new(0, 300, 0, 50)
	label.BackgroundTransparency = 1
	label.Text = "PAUSED"
	label.TextColor3 = Color3.new(1, 1, 1)
	label.TextSize = 36
	label.Font = Enum.Font.GothamBold
	label.Parent = frame

	local hint = Instance.new("TextLabel")
	hint.AnchorPoint = Vector2.new(0.5, 0.5)
	hint.Position = UDim2.new(0.5, 0, 0.55, 0)
	hint.Size = UDim2.new(0, 300, 0, 30)
	hint.BackgroundTransparency = 1
	hint.Text = "Press ESC to resume"
	hint.TextColor3 = Color3.fromRGB(180, 180, 180)
	hint.TextSize = 18
	hint.Font = Enum.Font.Gotham
	hint.Parent = frame

	self.pauseFrame = frame
end

function HudControl:UpdateHealth(curHealth)
	local pct = curHealth / 100
	self.healthFill.Size = UDim2.new(math.clamp(pct, 0, 1), 0, 1, 0)
	if pct < 0.3 then
		self.healthFill.BackgroundColor3 = Color3.fromRGB(255, 50, 50)
	elseif pct < 0.6 then
		self.healthFill.BackgroundColor3 = Color3.fromRGB(255, 165, 0)
	else
		self.healthFill.BackgroundColor3 = Color3.fromRGB(220, 50, 50)
	end
end

function HudControl:UpdateAmmo(curAmmo)
	self.ammoLabel.Text = tostring(curAmmo)
end

function HudControl:UpdateItem(itemName)
	local check = self.itemChecks[itemName]
	if check then
		check.Text = "[x] " .. itemName
		check.TextColor3 = Color3.fromRGB(100, 255, 100)
	end
end

function HudControl:TogglePause()
	self.isPaused = not self.isPaused
	self.pauseFrame.Visible = self.isPaused
	-- Note: Roblox doesn't have Time.timeScale, we handle pause in game loop
end

function HudControl:Destroy()
	if self.screenGui then
		self.screenGui:Destroy()
	end
end

return HudControl
