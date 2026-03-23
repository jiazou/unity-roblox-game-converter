-- TrackManager (Roblox port of Unity TrackManager.cs)
-- Uses UnityBridge modules. Manages track generation, speed, and obstacle spawning.

local ReplicatedStorage = game:GetService("ReplicatedStorage")

return function(config)
	local GO = require(ReplicatedStorage.UnityBridge.GameObjectUtil)

	local TrackManager = {}
	TrackManager.__index = TrackManager

	function TrackManager.new(trackConfig)
		local self = setmetatable({}, TrackManager)

		-- Config from Unity (TrackManager inspector values)
		self.minSpeed = trackConfig.minSpeed or 15
		self.maxSpeed = trackConfig.maxSpeed or 40
		self.acceleration = trackConfig.acceleration or 0.5
		self.laneOffset = trackConfig.laneOffset or 3
		self.laneCount = 3

		-- Track segment asset IDs (from uploaded GLBs)
		self.segmentAssets = trackConfig.segmentAssets or {}
		self.obstacleAssets = trackConfig.obstacleAssets or {}

		-- Runtime state
		self.speed = self.minSpeed
		self.totalDistance = 0
		self.isMoving = false
		self.segments = {}       -- active track segments
		self.obstacles = {}      -- active obstacles

		-- Track generation
		self.nextSegmentZ = 0
		self.segmentLength = 18  -- Entry(-4.5) to Exit(13.5)
		self.desiredSegmentCount = 10

		return self
	end

	function TrackManager:Start()
		-- Pre-generate initial track segments
		for i = 1, self.desiredSegmentCount do
			self:SpawnNextSegment()
		end
	end

	function TrackManager:SpawnNextSegment()
		if #self.segmentAssets == 0 then return end

		-- Pick a random segment (Unity: Random.Range on zone prefabList)
		local idx = math.random(1, #self.segmentAssets)
		local asset = self.segmentAssets[idx]

		-- Load segment meshes at the correct z position
		-- Each segment's meshes are offset from the segment origin
		if asset.meshes then
			for _, mesh in ipairs(asset.meshes) do
				local worldPos = Vector3.new(
					mesh.pos[1],
					mesh.pos[2],
					mesh.pos[3] + self.nextSegmentZ
				)
				local obj = GO.InstantiateFromAsset(mesh.id, worldPos)
				if obj then
					-- Anchor all parts
					for _, d in ipairs(obj:GetDescendants()) do
						if d:IsA("BasePart") then
							d.Anchored = true
							d.CanCollide = false
						end
					end
					table.insert(self.segments, obj)
				end
			end
		end

		-- Spawn obstacle on this segment (Unity: SpawnObstacle)
		if #self.obstacleAssets > 0 and math.random() > 0.3 then
			local obsIdx = math.random(1, #self.obstacleAssets)
			local obsAsset = self.obstacleAssets[obsIdx]
			local lane = math.random(0, 2)
			local laneX = (lane - 1) * self.laneOffset
			local obsZ = self.nextSegmentZ + self.segmentLength * 0.5
			local obj = GO.InstantiateFromAsset(obsAsset.id, Vector3.new(laneX, 0.5, obsZ))
			if obj then
				obj.Name = "Obstacle_" .. #self.obstacles
				for _, d in ipairs(obj:GetDescendants()) do
					if d:IsA("BasePart") then
						d.Anchored = true
						d.CanCollide = true
					end
				end
				table.insert(self.obstacles, { instance = obj, z = obsZ, lane = lane })
			end
		end

		self.nextSegmentZ = self.nextSegmentZ + self.segmentLength
	end

	function TrackManager:Update(dt)
		if not self.isMoving then return end

		-- Accelerate (Unity: k_Acceleration)
		if self.speed < self.maxSpeed then
			self.speed = self.speed + self.acceleration * dt
		end

		self.totalDistance = self.totalDistance + self.speed * dt
	end

	function TrackManager:GetSpeedRatio()
		return (self.speed - self.minSpeed) / (self.maxSpeed - self.minSpeed)
	end

	function TrackManager:StartMoving()
		self.isMoving = true
		self.speed = self.minSpeed
	end

	function TrackManager:StopMoving()
		self.isMoving = false
	end

	return TrackManager
end
