local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")

﻿using UnityEngine
/// <summary>
/// Handle everything related to controlling the character. Interact with both the Character (visual, animation) and CharacterCollider
/// </summary>
local s_DeadHash = Animator.StringToHash ("Dead")
	local s_RunStartHash = Animator.StringToHash("runStart")
	local s_MovingHash = Animator.StringToHash("Moving")
	local s_JumpingHash = Animator.StringToHash("Jumping")
	local s_JumpingSpeedHash = Animator.StringToHash("JumpSpeed")
	local s_SlidingHash = Animator.StringToHash("Sliding")
	TrackManager trackManager
	Character character
	CharacterCollider characterCollider
	GameObject blobShadow
	local laneChangeSpeed = 1.0f
	local maxLife = 3
	Consumable inventory
	int coins { get { return m_Coins; } set { m_Coins = value; } }
	int premium { get { return m_Premium; } set { m_Premium = value; } }
	int currentLife { get { return m_CurrentLife; } set { m_CurrentLife = value; } }
	-- List<T>: use Luau table {}Consumable> consumables { get { return m_ActiveConsumables; } }
	bool isJumping { get { return m_Jumping; } }
	bool isSliding { get { return m_Sliding; } }

	[Header("Controls")]
	local jumpLength = 2.0f;     // Distance jumped
	local jumpHeight = 1.2f
	local slideLength = 2.0f
	[Header("Sounds")]
	AudioClip slideSound
	AudioClip powerUpUseSound
	AudioSource powerupSource
    [HideInInspector] int currentTutorialLevel
    [HideInInspector] bool tutorialWaitingForValidation
    int m_Coins
    int m_Premium
    int m_CurrentLife
    -- List<T>: use Luau table {}Consumable> m_ActiveConsumables = new -- List<T>: use Luau table {}Consumable>()
    int m_ObstacleLayer
	bool m_IsInvincible
	bool m_IsRunning
    float m_JumpStart
    bool m_Jumping
	bool m_Sliding
	float m_SlideStart
	AudioSource m_Audio
    local m_CurrentLane = k_StartingLane
    Vector3 m_TargetPosition = Vector3.zero
    Vector3 k_StartingPosition = Vector3.zAxis * 2f
    local k_StartingLane = 1
    local k_GroundingSpeed = 80f
    local k_ShadowRaycastDistance = 100f
    local k_ShadowGroundOffset = 0.01f
    local k_TrackSpeedToJumpAnimSpeedRatio = 0.6f
    local k_TrackSpeedToSlideAnimSpeedRatio = 0.9f
    local function Awake()
    {
        m_Premium = 0
        m_CurrentLife = 0
        m_Sliding = false
        m_SlideStart = 0.0f
	    m_IsRunning = false
end
#if not UNITY_STANDALONE
    Vector2 m_StartingTouch
	local m_IsSwiping = false
#endif

    // Cheating functions, use for testing
	local function CheatInvincible(bool invincible)
	{
		m_IsInvincible = invincible
end
	local function IsCheatInvincible()
	{
		return m_IsInvincible
end
    local function Init()
    {
        .Position = k_StartingPosition
		m_TargetPosition = Vector3.zero
		m_CurrentLane = k_StartingLane
		characterCollider..CFrame.Position = Vector3.zero
        currentLife = maxLife
		m_Audio = :FindFirstChildOfClass<AudioSource>()
		m_ObstacleLayer = 1 << LayerMask.NameToLayer("Obstacle")
end
	// Called at the beginning of a run or rerun
	local function Begin()
	{
		m_IsRunning = false
        character.animator.SetBool(s_DeadHash, false)
		characterCollider.Init ()
		m_ActiveConsumablestable.clear
end
	local function End()
	{
        CleanConsumable()
end
    local function CleanConsumable()
    {
        for (local i = 0; i < #m_ActiveConsumables; ++i)
        {
            m_ActiveConsumables[i].Ended(this)
            Addressables.ReleaseInstance(m_ActiveConsumables[i].gameObject)
end
        m_ActiveConsumablestable.clear
end
    local function StartRunning()
    {   
	    StartMoving()
        if character.animator then
            character.animator.Play(s_RunStartHash)
            character.animator.SetBool(s_MovingHash, true)
end
end
	local function StartMoving()
	{
		m_IsRunning = true
end
    local function StopMoving()
    {
	    m_IsRunning = false
        trackManager.StopMove()
        if character.animator then
            character.animator.SetBool(s_MovingHash, false)
end
end
    local function TutorialMoveCheck(int tutorialLevel)
    {
        tutorialWaitingForValidation = currentTutorialLevel ~= tutorialLevel
        return (not TrackManager.instance.isTutorial  or  currentTutorialLevel >= tutorialLevel)
end
	local function game:GetService('RunService').Heartbeat:Connect(function()
    {
#if UNITY_EDITOR  or  UNITY_STANDALONE
        // Use key input in editor or standalone
        // disabled if it's tutorial and not thecurrent right tutorial level (see func TutorialMoveCheck)

        if (UserInputService.InputBegan(KeyCode.LeftArrow)  and  TutorialMoveCheck(0))
        {
            ChangeLane(-1)
end
        else if(UserInputService.InputBegan(KeyCode.RightArrow)  and  TutorialMoveCheck(0))
        {
            ChangeLane(1)
end
        else if(UserInputService.InputBegan(KeyCode.UpArrow)  and  TutorialMoveCheck(1))
        {
            Jump()
end
		else if (UserInputService.InputBegan(KeyCode.DownArrow)  and  TutorialMoveCheck(2))
		{
			if(not m_Sliding)
				Slide()
end
#else
        // Use touch input on mobile
        if Input.touchCount == 1 then
			if m_IsSwiping then
				Vector2 diff = UserInputService.TouchStarted(0).position - m_StartingTouch
				// Put difference in Screen ratio, but using only width, so the ratio is the same on both
                // axes (otherwise we would have to swipe more vertically...)
				diff = Vector2.new(diff.x/Screen.width, diff.y/Screen.width)
				if(diff.magnitude > 0.01f) //we set the swip distance to trigger movement to 1% of the screen width
				{
					if(math.abs(diff.y) > math.abs(diff.x))
					{
						if(TutorialMoveCheck(2)  and  diff.y < 0)
						{
							Slide()
end
						else if(TutorialMoveCheck(1))
						{
							Jump()
end
end
					else if(TutorialMoveCheck(0))
					{
						if diff.x < 0 then
							ChangeLane(-1)
						else
							ChangeLane(1)
end
end
					m_IsSwiping = false
end
end
        	// Input check is AFTER the swip test, that way if TouchPhase.Ended happen a single frame after the Began Phase
			// a swipe can still be registered (otherwise, m_IsSwiping will be set to false and the test wouldn't happen for that began-Ended pair)
			if(UserInputService.TouchStarted(0).phase == TouchPhase.Began)
			{
				m_StartingTouch = UserInputService.TouchStarted(0).position
				m_IsSwiping = true
end
			else if(UserInputService.TouchStarted(0).phase == TouchPhase.Ended)
			{
				m_IsSwiping = false
end
end
#endif

        Vector3 verticalTargetPosition = m_TargetPosition
		if m_Sliding then
            // Slide time isn't constant but the slide length is (even if slightly modified by speed, to slide slightly further when faster).
            // This is for gameplay reason, we don't want the character to drasticly slide farther when at max speed.
			local correctSlideLength = slideLength * (1.0f + trackManager.speedRatio)
			local ratio = (trackManager.worldDistance - m_SlideStart) / correctSlideLength
			if ratio >= 1.0f then
                // We slid to (or past) the required length, go back to running
				StopSliding()
end
end
        if m_Jumping then
			if trackManager.isMoving then
                // Same as with the sliding, we want a fixed jump LENGTH not fixed jump TIME. Also, just as with sliding,
                // we slightly modify length with speed to make it more playable.
				local correctJumpLength = jumpLength * (1.0f + trackManager.speedRatio)
				local ratio = (trackManager.worldDistance - m_JumpStart) / correctJumpLength
				if ratio >= 1.0f then
					m_Jumping = false
					character.animator.SetBool(s_JumpingHash, false)
				else
					verticalTargetPosition.y = math.sin(ratio * math.pi) * jumpHeight
end
end
			else if(not AudioListener.pause)//use AudioListener.pause as it is an easily accessible singleton & it is set when the app is in pause too
			{
			    verticalTargetPosition.y = -- MoveTowards: manual impl a + sign(b-a) * min(abs(b-a), maxDelta) (verticalTargetPosition.y, 0, k_GroundingSpeed * dt)
				if (Mathf.Approximately(verticalTargetPosition.y, 0f))
				{
					character.animator.SetBool(s_JumpingHash, false)
					m_Jumping = false
end
end
end
        characterCollider..CFrame.Position = -- MoveTowards: manual implementation(characterCollider..CFrame.Position, verticalTargetPosition, laneChangeSpeed * dt)
        // Put blob shadow under the character.
        RaycastHit hit
        if(workspace:Raycast(characterCollider..Position + Vector3.yAxis, -Vector3.yAxis, out hit, k_ShadowRaycastDistance, m_ObstacleLayer))
        {
            blobShadow..Position = hit.point + Vector3.yAxis * k_ShadowGroundOffset
        else
            Vector3 shadowPosition = characterCollider..Position
            shadowPosition.y = k_ShadowGroundOffset
            blobShadow..Position = shadowPosition
end
end
    local function Jump()
    {
	    if (not m_IsRunning)
		    return
        if not m_Jumping then
			if (m_Sliding)
				StopSliding()
			local correctJumpLength = jumpLength * (1.0f + trackManager.speedRatio)
			m_JumpStart = trackManager.worldDistance
            local animSpeed = k_TrackSpeedToJumpAnimSpeedRatio * (trackManager.speed / correctJumpLength)
            character.animator.SetFloat(s_JumpingSpeedHash, animSpeed)
            character.animator.SetBool(s_JumpingHash, true)
			m_Audio.PlayOneShot(character.jumpSound)
			m_Jumping = true
end
end
    local function StopJumping()
    {
        if m_Jumping then
            character.animator.SetBool(s_JumpingHash, false)
            m_Jumping = false
end
end
	local function Slide()
	{
		if (not m_IsRunning)
			return
		if not m_Sliding then

		    if (m_Jumping)
		        StopJumping()
            local correctSlideLength = slideLength * (1.0f + trackManager.speedRatio)
			m_SlideStart = trackManager.worldDistance
            local animSpeed = k_TrackSpeedToJumpAnimSpeedRatio * (trackManager.speed / correctSlideLength)
			character.animator.SetFloat(s_JumpingSpeedHash, animSpeed)
			character.animator.SetBool(s_SlidingHash, true)
			m_Audio.PlayOneShot(slideSound)
			m_Sliding = true
			characterCollider.Slide(true)
end
end
	local function StopSliding()
	{
		if m_Sliding then
			character.animator.SetBool(s_SlidingHash, false)
			m_Sliding = false
			characterCollider.Slide(false)
end
end
	local function ChangeLane(int direction)
    {
		if (not m_IsRunning)
			return
        local targetLane = m_CurrentLane + direction
        if (targetLane < 0  or  targetLane > 2)
            // Ignore, we are on the borders.
            return
        m_CurrentLane = targetLane
        m_TargetPosition = Vector3.new((m_CurrentLane - 1) * trackManager.laneOffset, 0, 0)
end
    local function UseInventory()
    {
        if(inventory ~= nil  and  inventory.CanBeUsed(this))
        {
            UseConsumable(inventory)
            inventory = nil
end
end
    local function UseConsumable(Consumable c)
    {
		characterCollider.audio.PlayOneShot(powerUpUseSound)
        for(local i = 0; i < #m_ActiveConsumables; ++i)
        {
            if(m_ActiveConsumables[i].GetType() == c.GetType())
            {
				// If we already have an active consumable of that type, we just reset the time
                m_ActiveConsumables[i].ResetTime()
                Addressables.ReleaseInstance(c.gameObject)
                return
end
end
        // If we didn't had one, activate that one 
        c..Parent =(transform, false)
        c..Parent(false)
        table.insert(m_ActiveConsumables, c)
        task.spawn(c.Started(this))
end
end