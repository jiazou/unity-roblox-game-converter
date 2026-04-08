-- Menu.lua — Main menu UI
-- Derived from: Menu.cs
-- Shows title screen with Play and Controls buttons
-- References: none
-- Bridge: none

local Players = game:GetService("Players")
local UserInputService = game:GetService("UserInputService")

local Menu = {}
Menu.__index = Menu

function Menu.new(config)
	config = config or {}
	local self = setmetatable({}, Menu)

	self.onStartGame = config.onStartGame -- callback when game starts
	self.screenGui = nil
	self.startable = false
	self._destroyed = false
	self._connections = {}

	return self
end

function Menu:Init()
	local playerGui = Players.LocalPlayer:WaitForChild("PlayerGui")

	-- Create menu GUI
	self.screenGui = Instance.new("ScreenGui")
	self.screenGui.Name = "MainMenu"
	self.screenGui.ResetOnSpawn = false
	self.screenGui.IgnoreGuiInset = true
	self.screenGui.Parent = playerGui

	-- Background
	local bg = Instance.new("Frame")
	bg.Name = "Background"
	bg.Size = UDim2.new(1, 0, 1, 0)
	bg.BackgroundColor3 = Color3.fromRGB(20, 20, 30)
	bg.Parent = self.screenGui

	-- Title
	local title = Instance.new("TextLabel")
	title.AnchorPoint = Vector2.new(0.5, 0.5)
	title.Position = UDim2.new(0.5, 0, 0.3, 0)
	title.Size = UDim2.new(0, 500, 0, 80)
	title.BackgroundTransparency = 1
	title.Text = "SIMPLE FPS"
	title.TextColor3 = Color3.new(1, 1, 1)
	title.TextSize = 60
	title.Font = Enum.Font.GothamBold
	title.Parent = bg

	-- Controls button
	local controlsBtn = Instance.new("TextButton")
	controlsBtn.Name = "ControlsBtn"
	controlsBtn.AnchorPoint = Vector2.new(0.5, 0.5)
	controlsBtn.Position = UDim2.new(0.5, 0, 0.5, 0)
	controlsBtn.Size = UDim2.new(0, 200, 0, 50)
	controlsBtn.BackgroundColor3 = Color3.fromRGB(60, 60, 80)
	controlsBtn.Text = "CONTROLS"
	controlsBtn.TextColor3 = Color3.new(1, 1, 1)
	controlsBtn.TextSize = 22
	controlsBtn.Font = Enum.Font.GothamBold
	controlsBtn.Parent = bg

	local btnCorner = Instance.new("UICorner")
	btnCorner.CornerRadius = UDim.new(0, 8)
	btnCorner.Parent = controlsBtn

	-- Controls panel (hidden initially)
	local controlsPanel = Instance.new("Frame")
	controlsPanel.Name = "Controls"
	controlsPanel.AnchorPoint = Vector2.new(0.5, 0.5)
	controlsPanel.Position = UDim2.new(0.5, 0, 0.65, 0)
	controlsPanel.Size = UDim2.new(0, 400, 0, 200)
	controlsPanel.BackgroundColor3 = Color3.fromRGB(40, 40, 50)
	controlsPanel.Visible = false
	controlsPanel.Parent = bg

	local panelCorner = Instance.new("UICorner")
	panelCorner.CornerRadius = UDim.new(0, 8)
	panelCorner.Parent = controlsPanel

	local controlsText = Instance.new("TextLabel")
	controlsText.Size = UDim2.new(1, -20, 1, -20)
	controlsText.Position = UDim2.new(0, 10, 0, 10)
	controlsText.BackgroundTransparency = 1
	controlsText.Text = "WASD - Move\nMouse - Look\nLeft Click - Shoot\nSpace - Jump\nESC - Pause\n\nClick anywhere to start!"
	controlsText.TextColor3 = Color3.new(1, 1, 1)
	controlsText.TextSize = 16
	controlsText.Font = Enum.Font.Gotham
	controlsText.TextYAlignment = Enum.TextYAlignment.Top
	controlsText.Parent = controlsPanel

	-- Wire buttons
	controlsBtn.MouseButton1Click:Connect(function()
		controlsPanel.Visible = true
		self.startable = true
	end)

	-- Start on click when startable
	local inputConn = UserInputService.InputBegan:Connect(function(input, processed)
		if processed then return end
		if self.startable and input.UserInputType == Enum.UserInputType.MouseButton1 then
			self:StartGame()
		end
	end)
	table.insert(self._connections, inputConn)
end

function Menu:StartGame()
	if self._destroyed then return end
	self._destroyed = true

	-- Hide menu
	if self.screenGui then
		self.screenGui:Destroy()
	end

	-- Call start callback
	if self.onStartGame then
		self.onStartGame()
	end
end

function Menu:Destroy()
	self._destroyed = true
	for _, conn in ipairs(self._connections) do
		conn:Disconnect()
	end
	self._connections = {}
	if self.screenGui then
		self.screenGui:Destroy()
	end
end

return Menu
