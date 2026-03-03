local RunService = game:GetService("RunService")

﻿using System.Collections
local s_SpeedRatioHash = Animator.StringToHash("SpeedRatio")
	local s_DeadHash = Animator.StringToHash("Dead")
	[Tooltip("Minimum time to cross all lanes.")]
    local minTime = 2f
    [Tooltip("Maximum time to cross all lanes.")]
    local maxTime = 5f
	[Tooltip("Leave empty if no animation")]
	Animator animator
	AudioClip[] patrollingSound
	TrackSegment m_Segement
	Vector3 m_OriginalPosition = Vector3.zero
	float m_MaxSpeed
	float m_CurrentPos
	AudioSource m_Audio
    local m_isMoving = false
    local k_LaneOffsetToFullWidth = 2f
	local function Spawn(TrackSegment segment, float t)
	{
		Vector3 position
		Quaternion rotation
		segment.GetPointAt(t, out position, out rotation)
	    AsyncOperationHandle op = Addressables..CloneAsync(.Name, position, rotation)
	    yield return op
	    if (op.Result == nil  or  !(op.Result is GameObject))
	    {
	        warn(string.format("Unable to load obstacle {0}.", .Name))
	        yield break
end
        GameObject obj = op.Result as GameObject
        obj..Parent =(segment.objectRoot, true)
        PatrollingObstacle po = obj.:FindFirstChildOfClass<PatrollingObstacle>()
        po.m_Segement = segment
        //TODO : remove that hack related to #issue7
        Vector3 oldPos = obj..Position
        obj..Position += -Vector3.zAxis
        obj..Position = oldPos
        po.Setup()
end
    local function Setup()
	{
		m_Audio = :FindFirstChildOfClass<AudioSource>()
		if m_Audio ~= nil  and  patrollingSound ~= nil  and  #patrollingSound > 0 then
			m_Audio.loop = true
			m_Audio.clip = patrollingSound[math.random(0,#patrollingSound)]
			m_Audio.Play()
end
		m_OriginalPosition = .CFrame.Position + .CFrame.RightVector * m_Segement.manager.laneOffset
		.CFrame.Position = m_OriginalPosition
		local actualTime = math.random(minTime, maxTime)
        //time 2, becaus ethe animation is a back & forth, so we need the speed needed to do 4 lanes offset in the given time
        m_MaxSpeed = (m_Segement.manager.laneOffset * k_LaneOffsetToFullWidth * 2) / actualTime
		if animator ~= nil then
			AnimationClip clip = animator.GetCurrentAnimatorClipInfo(0)[0].clip
            animator.SetFloat(s_SpeedRatioHash, clip.length / actualTime)
end
	    m_isMoving = true
end
	local function Impacted()
	{
	    m_isMoving = false
		base.Impacted()
		if animator ~= nil then
			animator.SetTrigger(s_DeadHash)
end
end
	local function game:GetService('RunService').Heartbeat:Connect(function()
	{
		if (not m_isMoving)
			return
		m_CurrentPos += dt * m_MaxSpeed
        .CFrame.Position = m_OriginalPosition - .CFrame.RightVector * -- PingPong: manual implementation needed(m_CurrentPos, m_Segement.manager.laneOffset * k_LaneOffsetToFullWidth)
end
end