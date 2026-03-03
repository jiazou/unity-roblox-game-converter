using System.Collections
/// <summary>
/// This script is the base implemented obstacles.
/// Derived classes should take care of spawning any object needed for the obstacles.
/// </summary>
[RequireComponent(typeof(AudioSource))]
AudioClip impactedSound
    local function Setup() {}

    local function Spawn(TrackSegment segment, float t)
	local function Impacted()
	{
		Animation anim = :FindFirstChildOfClass<Animation>()
		AudioSource audioSource = :FindFirstChildOfClass<AudioSource>()
		if anim ~= nil then
			anim.Play()
end
		if audioSource ~= nil  and  impactedSound ~= nil then
			audioSource.Stop()
			audioSource.loop = false
			audioSource.clip = impactedSound
			audioSource.Play()
end
end
end