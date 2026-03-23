-- CharacterController (Roblox port of Unity CharacterInputController.cs)
-- Handles lane changes, jumping, sliding, and collision detection.

local ReplicatedStorage = game:GetService("ReplicatedStorage")

return function(config)
	local Input = require(ReplicatedStorage.UnityBridge.Input)
	local Physics = require(ReplicatedStorage.UnityBridge.Physics)

	local CharacterController = {}
	CharacterController.__index = CharacterController

	function CharacterController.new(playerConfig)
		local self = setmetatable({}, CharacterController)

		-- Config (from Unity CharacterInputController inspector)
		self.laneChangeSpeed = playerConfig.laneChangeSpeed or 15
		self.laneOffset = playerConfig.laneOffset or 3
		self.jumpHeight = playerConfig.jumpHeight or 8
		self.jumpDuration = playerConfig.jumpDuration or 0.6
		self.slideLength = playerConfig.slideLength or 0.4

		-- State (from Unity: m_CurrentLane, m_Jumping, m_Sliding, etc.)
		self.currentLane = 1     -- 0=left, 1=center, 2=right (Unity: k_StartingLane=1)
		self.targetX = 0
		self.currentX = 0
		self.currentZ = 0
		self.jumpY = 0

		self.isJumping = false
		self.isSliding = false
		self.jumpTime = 0
		self.slideTime = 0

		self.isRunning = false
		self.alive = true

		-- References
		self.character = nil     -- the Roblox character model
		self.rootPart = nil      -- HumanoidRootPart
		self.trackManager = nil  -- set by game bootstrap

		return self
	end

	function CharacterController:Init(character)
		self.character = character
		self.rootPart = character:WaitForChild("HumanoidRootPart")
		local humanoid = character:WaitForChild("Humanoid")
		humanoid.WalkSpeed = 0
		humanoid.JumpPower = 0
	end

	function CharacterController:StartRunning()
		self.isRunning = true
		self.currentZ = 0
		self.currentLane = 1
		self.targetX = 0
		self.currentX = 0
	end

	function CharacterController:ChangeLane(direction)
		-- Unity: ChangeLane() - clamp to 0..2
		local targetLane = self.currentLane + direction
		if targetLane < 0 or targetLane > 2 then return end
		self.currentLane = targetLane
		-- Unity: m_TargetPosition = new Vector3((m_CurrentLane - 1) * trackManager.laneOffset, 0, 0)
		self.targetX = (self.currentLane - 1) * self.laneOffset
	end

	function CharacterController:Jump()
		if self.isJumping or not self.isRunning then return end
		self.isJumping = true
		self.jumpTime = 0
	end

	function CharacterController:Slide()
		if self.isSliding or self.isJumping or not self.isRunning then return end
		self.isSliding = true
		self.slideTime = 0
	end

	function CharacterController:HandleInput()
		if not self.alive then return end

		-- Keyboard (Unity: Update() input handling)
		if Input.GetKeyDown("A") or Input.GetKeyDown("LeftArrow") then
			self:ChangeLane(1)  -- inverted for camera orientation
		end
		if Input.GetKeyDown("D") or Input.GetKeyDown("RightArrow") then
			self:ChangeLane(-1)
		end
		if Input.GetKeyDown("Space") or Input.GetKeyDown("W") or Input.GetKeyDown("UpArrow") then
			self:Jump()
		end
		if Input.GetKeyDown("S") or Input.GetKeyDown("DownArrow") or Input.GetKeyDown("LeftShift") then
			self:Slide()
		end

		-- Touch/swipe
		local swipe = Input.GetSwipe()
		if swipe == "Left" then self:ChangeLane(1)
		elseif swipe == "Right" then self:ChangeLane(-1)
		elseif swipe == "Up" then self:Jump()
		elseif swipe == "Down" then self:Slide()
		end
	end

	function CharacterController:Update(dt)
		if not self.alive or not self.isRunning then return end
		if not self.rootPart then return end

		local speed = self.trackManager and self.trackManager.speed or 15

		-- Move forward (Unity: TrackManager moves the world, here we move the character)
		self.currentZ = self.currentZ + speed * dt

		-- Lane change (Unity: Vector3.MoveTowards for smooth transition)
		self.currentX = self.currentX + (self.targetX - self.currentX) * math.min(1, self.laneChangeSpeed * dt)

		-- Jump arc (Unity: parabolic jump with jumpLength)
		self.jumpY = 0
		if self.isJumping then
			self.jumpTime = self.jumpTime + dt
			local t = self.jumpTime / self.jumpDuration
			if t >= 1 then
				self.isJumping = false
				self.jumpY = 0
			else
				self.jumpY = self.jumpHeight * math.sin(t * math.pi)
			end
		end

		-- Slide (Unity: reduce collider height for slideLength)
		if self.isSliding then
			self.slideTime = self.slideTime + dt
			if self.slideTime >= self.slideLength then
				self.isSliding = false
			end
		end

		-- Update character position
		local charPos = Vector3.new(self.currentX, self.jumpY + 3, self.currentZ)
		self.rootPart.CFrame = CFrame.new(charPos) * CFrame.Angles(0, math.rad(180), 0)
		self.rootPart.Velocity = Vector3.zero
	end

	function CharacterController:CheckCollisions()
		if not self.alive or self.isJumping then return false end

		local charPos = Vector3.new(self.currentX, 3, self.currentZ)

		-- Check distance to all obstacles (Unity: OnTriggerEnter with obstacle layer)
		for _, obj in ipairs(workspace:GetChildren()) do
			if obj.Name:match("^Obstacle_") then
				local parts = {}
				if obj:IsA("BasePart") then table.insert(parts, obj) end
				for _, d in ipairs(obj:GetDescendants()) do
					if d:IsA("BasePart") then table.insert(parts, d) end
				end
				for _, part in ipairs(parts) do
					local dx = part.Position.X - charPos.X
					local dz = part.Position.Z - charPos.Z
					if math.sqrt(dx*dx + dz*dz) < 2 then
						return true, obj.Name
					end
				end
			end
		end
		return false
	end

	function CharacterController:Die()
		self.alive = false
		self.isRunning = false
	end

	return CharacterController
end
