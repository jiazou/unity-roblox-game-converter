-- GameBootstrap (Roblox port of Unity GameManager state machine)
-- Wires TrackManager + CharacterController + UI + game flow.
-- This is a LocalScript placed in StarterPlayerScripts.

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Input = require(ReplicatedStorage.UnityBridge.Input)
local Time = require(ReplicatedStorage.UnityBridge.Time)

local player = Players.LocalPlayer
local camera = workspace.CurrentCamera

-- Wait for character to load
player.CharacterAdded:Wait()
local character = player.Character
local humanoid = character:WaitForChild("Humanoid")
local rootPart = character:WaitForChild("HumanoidRootPart")

-- Disable default Roblox movement
humanoid.WalkSpeed = 0
humanoid.JumpPower = 0

-- Scale character down to match track
for _, scaleName in ipairs({"BodyDepthScale", "BodyHeightScale", "BodyWidthScale", "HeadScale"}) do
	local scale = humanoid:FindFirstChild(scaleName)
	if scale then scale.Value = 0.5 end
end

---------------------------------------------------------------------------
-- Game State (from Unity GameManager state machine)
---------------------------------------------------------------------------
local GameState = {
	LOADING = "Loading",
	RUNNING = "Running",
	DEAD = "Dead",
	FINISHED = "Finished",
}

local state = GameState.LOADING
local score = 0
local lives = 1

-- Character controller state (inline, using bridge patterns)
local LANE_OFFSET = 3
local currentLane = 1
local targetX = 0
local currentX = 0
local currentZ = 0
local currentSpeed = 15
local MIN_SPEED = 15
local MAX_SPEED = 40
local ACCELERATION = 0.5

local isJumping = false
local jumpTime = 0
local JUMP_HEIGHT = 8
local JUMP_DURATION = 0.6

---------------------------------------------------------------------------
-- UI (from Unity GameState UI references)
---------------------------------------------------------------------------
local screenGui = Instance.new("ScreenGui")
screenGui.ResetOnSpawn = false
screenGui.Parent = player.PlayerGui

local scoreLabel = Instance.new("TextLabel")
scoreLabel.Size = UDim2.new(0, 200, 0, 50)
scoreLabel.Position = UDim2.new(0.5, -100, 0, 10)
scoreLabel.BackgroundTransparency = 0.5
scoreLabel.BackgroundColor3 = Color3.new(0, 0, 0)
scoreLabel.TextColor3 = Color3.new(1, 1, 1)
scoreLabel.TextSize = 28
scoreLabel.Font = Enum.Font.GothamBold
scoreLabel.Text = "Loading track..."
scoreLabel.Parent = screenGui

local infoLabel = Instance.new("TextLabel")
infoLabel.Size = UDim2.new(0, 300, 0, 30)
infoLabel.Position = UDim2.new(0.5, -150, 0, 65)
infoLabel.BackgroundTransparency = 0.7
infoLabel.BackgroundColor3 = Color3.new(0, 0, 0)
infoLabel.TextColor3 = Color3.new(0.5, 1, 0.5)
infoLabel.TextSize = 16
infoLabel.Font = Enum.Font.Gotham
infoLabel.Text = "A/D = lanes | Space = jump | R = restart"
infoLabel.Parent = screenGui

---------------------------------------------------------------------------
-- Input (from Unity CharacterInputController.Update)
---------------------------------------------------------------------------
local function changeLane(dir)
	local target = currentLane + dir
	if target < 0 or target > 2 then return end
	currentLane = target
	targetX = (currentLane - 1) * LANE_OFFSET
end

local function jump()
	if isJumping then return end
	isJumping = true
	jumpTime = 0
end

local function restart()
	state = GameState.RUNNING
	currentZ = 0
	currentX = 0
	targetX = 0
	currentLane = 1
	currentSpeed = MIN_SPEED
	isJumping = false
	jumpTime = 0
	score = 0
	lives = 1
	scoreLabel.TextColor3 = Color3.new(1, 1, 1)
end

-- Keyboard
local UIS = game:GetService("UserInputService")
UIS.InputBegan:Connect(function(input, processed)
	if processed then return end

	if state == GameState.DEAD or state == GameState.FINISHED then
		if input.KeyCode == Enum.KeyCode.R then
			restart()
		end
		return
	end

	if state ~= GameState.RUNNING then return end

	if input.KeyCode == Enum.KeyCode.A or input.KeyCode == Enum.KeyCode.Left then
		changeLane(1)
	elseif input.KeyCode == Enum.KeyCode.D or input.KeyCode == Enum.KeyCode.Right then
		changeLane(-1)
	elseif input.KeyCode == Enum.KeyCode.Space or input.KeyCode == Enum.KeyCode.W or input.KeyCode == Enum.KeyCode.Up then
		jump()
	end
end)

-- Touch/swipe
local touchStart = nil
UIS.TouchStarted:Connect(function(touch)
	touchStart = touch.Position
end)
UIS.TouchEnded:Connect(function(touch)
	if not touchStart then return end
	if state == GameState.DEAD or state == GameState.FINISHED then
		restart()
		touchStart = nil
		return
	end
	if state ~= GameState.RUNNING then touchStart = nil return end
	local delta = touch.Position - touchStart
	if math.abs(delta.X) > math.abs(delta.Y) then
		if delta.X > 40 then changeLane(-1)
		elseif delta.X < -40 then changeLane(1) end
	else
		if delta.Y < -40 then jump() end
	end
	touchStart = nil
end)

---------------------------------------------------------------------------
-- Wait for track to load
---------------------------------------------------------------------------
-- The MeshLoader server script loads track meshes via InsertService.
-- Wait until obstacles appear in workspace.
local waitStart = os.clock()
while os.clock() - waitStart < 30 do
	local hasObstacles = false
	for _, obj in ipairs(workspace:GetChildren()) do
		if obj.Name:match("^Obstacle_") then
			hasObstacles = true
			break
		end
	end
	if hasObstacles then break end
	scoreLabel.Text = "Loading track..."
	task.wait(0.5)
end

---------------------------------------------------------------------------
-- TRACK_LENGTH is injected by the generator
---------------------------------------------------------------------------
local TRACK_LENGTH = --TRACK_LENGTH_PLACEHOLDER--

---------------------------------------------------------------------------
-- Start running
---------------------------------------------------------------------------
state = GameState.RUNNING
camera.CameraType = Enum.CameraType.Scriptable

---------------------------------------------------------------------------
-- Game loop (from Unity TrackManager.Update + CharacterInputController.Update)
---------------------------------------------------------------------------
RunService.Heartbeat:Connect(function(dt)
	if state ~= GameState.RUNNING then return end

	-- Forward movement (Unity: TrackManager.Update scaledSpeed)
	currentZ = currentZ + currentSpeed * dt

	-- Accelerate (Unity: k_Acceleration)
	if currentSpeed < MAX_SPEED then
		currentSpeed = currentSpeed + ACCELERATION * dt
	end

	-- Lane change smooth (Unity: Vector3.MoveTowards)
	currentX = currentX + (targetX - currentX) * math.min(1, 15 * dt)

	-- Jump (Unity: parabolic arc)
	local jumpY = 0
	if isJumping then
		jumpTime = jumpTime + dt
		local t = jumpTime / JUMP_DURATION
		if t >= 1 then
			isJumping = false
		else
			jumpY = JUMP_HEIGHT * math.sin(t * math.pi)
		end
	end

	-- Position character
	local charPos = Vector3.new(currentX, jumpY + 3, currentZ)
	rootPart.CFrame = CFrame.new(charPos) * CFrame.Angles(0, math.rad(180), 0)
	rootPart.Velocity = Vector3.zero

	-- Camera (Unity: Camera.main follows characterController.transform)
	camera.CFrame = CFrame.lookAt(
		charPos + Vector3.new(0, 8, -12),
		charPos + Vector3.new(0, 2, 10)
	)

	-- Collision (Unity: CharacterCollider.OnTriggerEnter)
	if not isJumping then
		for _, obj in ipairs(workspace:GetChildren()) do
			if obj.Name:match("^Obstacle_") then
				for _, d in ipairs(obj:GetDescendants()) do
					if d:IsA("BasePart") then
						local dx = d.Position.X - charPos.X
						local dz = d.Position.Z - charPos.Z
						if math.sqrt(dx*dx + dz*dz) < 2 then
							-- Hit! (Unity: controller.currentLife -= 1)
							lives = lives - 1
							if lives <= 0 then
								state = GameState.DEAD
								currentSpeed = 0
								scoreLabel.Text = "CRASHED! Score: " .. score
								scoreLabel.TextColor3 = Color3.new(1, 0.3, 0.3)
								infoLabel.Text = "Press R to restart"
							end
							break
						end
					end
				end
				if state == GameState.DEAD then break end
			end
		end
	end

	-- Score (Unity: m_ScoreAccum)
	score = math.floor(currentZ)
	if state == GameState.RUNNING then
		scoreLabel.Text = "Score: " .. score
		infoLabel.Text = string.format("Speed: %.0f | A/D = lanes | Space = jump", currentSpeed)
	end

	-- End of track
	if currentZ > TRACK_LENGTH then
		state = GameState.FINISHED
		scoreLabel.Text = "FINISHED! Score: " .. score
		scoreLabel.TextColor3 = Color3.new(0.3, 1, 0.3)
		infoLabel.Text = "Track complete! Press R to restart"
	end

	-- Clear per-frame input state
	Input._EndFrame()
end)

print("[GameBootstrap] Trash Dash running!")
