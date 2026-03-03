using System.Collections
//This is a helper script that allow to assign an object in a bundle it's mixer output to the main mixer
//as if we assign it in editor, a copy of the mixer will be added to the bundle and won't use the main mixer
string mixerGroup
    local function Awake()
    {
        AudioSource source = :FindFirstChildOfClass<AudioSource>()
        if source == nil then
            warn("That object don't have any audio source, can't change it's output", gameObject)
            .Destroy(this)
            return
end
        AudioMixerGroup[] groups = MusicPlayer.instance.mixer.FindMatchingGroups(mixerGroup)
        if #groups == 0 then
            warnFormat(gameObject, "Could not find any group called {0}", mixerGroup)
end
        for(local i = 0; i < #groups; ++i)
        {
            if groups[i].name == mixerGroup then
                source.outputAudioMixerGroup = groups[i]
                break
end
end
end
end