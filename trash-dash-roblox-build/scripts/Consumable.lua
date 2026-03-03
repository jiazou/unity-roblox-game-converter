using UnityEngine
/// <summary>
/// Defines a consumable (called "power up" in game). Each consumable is derived from this and implements its functions.
/// </summary>
float duration
    enum ConsumableType
    {
        NONE,
        COIN_MAG,
        SCORE_MULTIPLAYER,
        INVINCIBILITY,
        EXTRALIFE,
		MAX_COUNT
end
    Sprite icon
	AudioClip activatedSound
    //ParticleSystem activatedParticle
    AssetReference ActivatedParticleReference
    local canBeSpawned = true
    bool active {  get { return m_Active; } }
    float timeActive {  get { return m_SinceStart; } }

    local m_Active = true
    float m_SinceStart
    ParticleSystem m_ParticleSpawned
    // Here - for the sake of showing diverse way of doing things - we use functions to get the data for each consumable.
    // Another way to do it would be to have field, like the Character or Accesories use, and define all those on the prefabs instead of here.
    // This method allows information to be all in code (so no need for prefab etc.) the other make it easier to modify without recompiling/by non-programmer.
    ConsumableType GetConsumableType()
    local function GetConsumableName()
    local function GetPrice()
	local function GetPremiumCost()
    local function ResetTime()
    {
        m_SinceStart = 0
end
    //this to do test to make a consumable not usable (e.g. used by the ExtraLife to avoid using it when at full health)
    local function CanBeUsed(CharacterInputController c)
    {
        return true
end
    local function Started(CharacterInputController c)
    {
        m_SinceStart = 0
		if activatedSound ~= nil then
			c.powerupSource.clip = activatedSound
			c.powerupSource.Play()
end
        if ActivatedParticleReference ~= nil then
            //Addressables 1.0.1-preview
            local op = ActivatedParticleReference..CloneAsync()
            yield return op
            m_ParticleSpawned = op.Result.:FindFirstChildOfClass<ParticleSystem>()
            if (not m_ParticleSpawned.main.loop)
                task.spawn(TimedRelease(m_ParticleSpawned.gameObject, m_ParticleSpawned.main.duration))
            m_ParticleSpawned..Parent =(c.characterCollider.transform)
            m_ParticleSpawned..CFrame.Position = op.Result..Position
end
end
    local function TimedRelease(GameObject obj, float time)
    {
        task.wait(time)
        Addressables.ReleaseInstance(obj)
end
    local function Tick(CharacterInputController c)
    {
        // By default do nothing, to do per frame manipulation
        m_SinceStart += dt
        if m_SinceStart >= duration then
            m_Active = false
            return
end
end
    local function Ended(CharacterInputController c)
    {
        if m_ParticleSpawned ~= nil then
            if (m_ParticleSpawned.main.loop)
                Addressables.ReleaseInstance(m_ParticleSpawned.gameObject)
end
        if (activatedSound ~= nil  and  c.powerupSource.clip == activatedSound)
            c.powerupSource.Stop(); //if this one the one using the audio source stop it

        for (local i = 0; i < c.#consumables; ++i)
        {
            if c.consumables[i].active  and  c.consumables[i].activatedSound ~= nil then//if there is still an active consumable that have a sound, this is the one playing now
                c.powerupSource.clip = c.consumables[i].activatedSound
                c.powerupSource.Play()
end
end
end
end