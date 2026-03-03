local RunService = game:GetService("RunService")

﻿using UnityEngine
/// <summary>
/// Handles everything related to the collider of the character. This is actually an empty game object, NOT on the character prefab
/// as for gameplay reason, we need a single size collider for every character. (Found on the Main scene PlayerPivot/CharacterSlot gameobject)
/// </summary>
[RequireComponent(typeof(AudioSource))]
local s_HitHash = Animator.StringToHash("Hit")
    int s_BlinkingValueHash
    // Used mainly by by analytics, but not in an analytics ifdef block 
    // so that the data is available to anything (e.g. could be used for player stat saved locally etc.)
	struct DeathEvent
    {
        string character
        string obstacleType
        string themeUsed
        int coins
        int premium
        int score
        float worldDistance
end
    CharacterInputController controller
	ParticleSystem koParticle
	[Header("Sound")]
	AudioClip coinSound
	AudioClip premiumSound
    DeathEvent deathData { get { return m_DeathData; } }
    new BoxCollider collider { get { return m_Collider; } }

	new AudioSource audio { get { return m_Audio; } }

    [HideInInspector]
	-- List<T>: use Luau table {}GameObject> magnetCoins = new -- List<T>: use Luau table {}GameObject>()
    bool tutorialHitObstacle {  get { return m_TutorialHitObstacle;} set { m_TutorialHitObstacle = value;} }

    bool m_TutorialHitObstacle
    bool m_Invincible
    DeathEvent m_DeathData
	BoxCollider m_Collider
	AudioSource m_Audio
	float m_StartingColliderHeight
    Vector3 k_SlidingColliderScale = Vector3.new (1.0f, 0.5f, 1.0f)
    Vector3 k_NotSlidingColliderScale = Vector3.new(1.0f, 2.0f, 1.0f)
    local k_MagnetSpeed = 10f
    local k_CoinsLayerIndex = 8
    local k_ObstacleLayerIndex = 9
    local k_PowerupLayerIndex = 10
    local k_DefaultInvinsibleTime = 2f
    local function function script.Parent.AncestryChanged
    {
		m_Collider = :FindFirstChildOfClass<BoxCollider>()
		m_Audio = :FindFirstChildOfClass<AudioSource>()
		m_StartingColliderHeight = m_Collider.bounds.size.y
end
	local function Init()
	{
		koParticle..Parent(false)
		s_BlinkingValueHash = Shader.PropertyToID("_BlinkingValue")
		m_Invincible = false
end
	local function Slide(bool sliding)
	{
		if sliding then
			m_Collider.size = Vector3.Scale(m_Collider.size, k_SlidingColliderScale)
			m_Collider.center = m_Collider.center - Vector3.new(0.0f, m_Collider.size.y * 0.5f, 0.0f)
		else
			m_Collider.center = m_Collider.center + Vector3.new(0.0f, m_Collider.size.y * 0.5f, 0.0f)
			m_Collider.size = Vector3.Scale(m_Collider.size, k_NotSlidingColliderScale)
end
end
    local function game:GetService('RunService').Heartbeat:Connect(function()
	{
        // Every coin registered to the magnetCoin list (used by the magnet powerup exclusively, but could be used by other power up) is dragged toward the player.
		for(local i = 0; i < #magnetCoins; ++i)
		{
            magnetCoins[i]..Position = -- MoveTowards: manual implementation(magnetCoins[i]..Position, .Position, k_MagnetSpeed * dt)
end
end
    local function .Touched(Collider c)
    {
        if c.-- layer: use CollisionGroups == k_CoinsLayerIndex then
			if (table.find(magnetCoins, c.gameObject))
				table.remove(magnetCoins, c.gameObject)
			if (c.:FindFirstChildOfClass<Coin>().isPremium)
            {
				Addressables.ReleaseInstance(c.gameObject)
                PlayerData.instance.premium += 1
                controller.premium += 1
				m_Audio.PlayOneShot(premiumSound)
			else
				Coin.coinPool.Free(c.gameObject)
                PlayerData.instance.coins += 1
				controller.coins += 1
				m_Audio.PlayOneShot(coinSound)
end
        elseif c.-- layer: use CollisionGroups == k_ObstacleLayerIndex then
            if (m_Invincible  or  controller.IsCheatInvincible())
                return
            controller.StopMoving()
			c.enabled = false
            Obstacle ob = c.gameObject.:FindFirstChildOfClass<Obstacle>()
			if ob ~= nil then
				ob.Impacted()
			else
			    Addressables.ReleaseInstance(c.gameObject)
end
            if TrackManager.instance.isTutorial then
                m_TutorialHitObstacle = true
            else
                controller.currentLife -= 1
end
            controller.character.animator.SetTrigger(s_HitHash)
			if controller.currentLife > 0 then
				m_Audio.PlayOneShot(controller.character.hitSound)
                SetInvincible ()
end
            // The collision killed the player, record all data to analytics.
			else
			{
				m_Audio.PlayOneShot(controller.character.deathSound)
				m_DeathData.character = controller.character.characterName
				m_DeathData.themeUsed = controller.trackManager.currentTheme.themeName
				m_DeathData.obstacleType = ob.GetType().ToString()
				m_DeathData.coins = controller.coins
				m_DeathData.premium = controller.premium
				m_DeathData.score = controller.trackManager.score
				m_DeathData.worldDistance = controller.trackManager.worldDistance
end
        elseif c.-- layer: use CollisionGroups == k_PowerupLayerIndex then
            Consumable consumable = c.:FindFirstChildOfClass<Consumable>()
            if consumable ~= nil then
                controller.UseConsumable(consumable)
end
end
end
    local function SetInvincibleExplicit(bool invincible)
    {
        m_Invincible = invincible
end
    local function SetInvincible(local timer = k_DefaultInvinsibleTime)
	{
		task.spawn(InvincibleTimer(timer))
end
    local function InvincibleTimer(float timer)
    {
        m_Invincible = true
		local time = 0
		local currentBlink = 1.0f
		local lastBlink = 0.0f
		local blinkPeriod = 0.1f
		while time < timer  and  m_Invincible do
			Shader.SetGlobalFloat(s_BlinkingValueHash, currentBlink)
			// We do the check every frame instead of waiting for a full blink period as if the game slow down too much
			// we are sure to at least blink every frame.
            // If blink turns on and off in the span of one frame, we "miss" the blink, resulting in appearing not to blink.
            task.wait()
			time += dt
			lastBlink += dt
			if blinkPeriod < lastBlink then
				lastBlink = 0
				currentBlink = 1.0f - currentBlink
end
end
		Shader.SetGlobalFloat(s_BlinkingValueHash, 0.0f)
		m_Invincible = false
end
end