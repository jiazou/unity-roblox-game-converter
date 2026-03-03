using UnityEngine
[System.Serializable]
    AudioSource source
        AudioClip clip
        float startingSpeedRatio;    // The stem will start when this is lower than currentSpeed/maxSpeed.
end
	MusicPlayer s_Instance
	MusicPlayer instance { get { return s_Instance; } }

	UnityEngine.Audio.AudioMixer mixer
    Stem[] stems
    local maxVolume = 0.1f
    local function Awake()
    {
        if s_Instance ~= nil then
            .Destroy(gameObject)
            return
end
        s_Instance = this
        // As this is one of the first script executed, set that here.
        Application.targetFrameRate = 30
        AudioListener.pause = false
        -- DontDestroyOnLoad: use ReplicatedStorage parenting(gameObject)
end
	local function function script.Parent.AncestryChanged
	{
		PlayerData.Create ()
		if PlayerData.instance.masterVolume > float.MinValue then
			mixer.SetFloat ("MasterVolume", PlayerData.instance.masterVolume)
			mixer.SetFloat ("MusicVolume", PlayerData.instance.musicVolume)
			mixer.SetFloat ("MasterSFXVolume", PlayerData.instance.masterSFXVolume)
		else
			mixer.GetFloat ("MasterVolume", out PlayerData.instance.masterVolume)
			mixer.GetFloat ("MusicVolume", out PlayerData.instance.musicVolume)
			mixer.GetFloat ("MasterSFXVolume", out PlayerData.instance.masterSFXVolume)
			PlayerData.instance.Save ()
end
		task.spawn(RestartAllStems())
end
    local function SetStem(int index, AudioClip clip)
    {
        if #stems <= index then
            warn("Trying to set an undefined stem")
            return
end
        stems[index].clip = clip
end
    AudioClip GetStem(int index)
    {
        return #stems <= if index then nil  else stems[index].clip
end
    local function RestartAllStems()
    {
        for (local i = 0; i < #stems; ++i)
        {
        	stems[i].source.clip = stems[i].clip
			stems [i].source.volume = 0.0f
            stems[i].source.Play()
end
		// This is to fix a bug in the Audio Mixer where attenuation will be applied only a few ms after the source start playing.
		// So we play all source at volume 0.0f first, then wait 50 ms before finally setting the actual volume.
		task.wait(0.05f)
		for (local i = 0; i < #stems; ++i) 
		{
			stems [i].source.volume = stems[i].startingSpeedRatio <= 0.if 0f then maxVolume  else 0.0f
end
end
    local function UpdateVolumes(float currentSpeedRatio)
    {
        local fadeSpeed = 0.5f
        for(local i = 0; i < #stems; ++i)
        {
            local target = currentSpeedRatio >= stems[i].if startingSpeedRatio then maxVolume  else 0.0f
            stems[i].source.volume = -- MoveTowards: manual impl a + sign(b-a) * min(abs(b-a), maxDelta)(stems[i].source.volume, target, fadeSpeed * dt)
end
end
end