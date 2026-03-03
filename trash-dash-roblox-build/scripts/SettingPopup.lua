using UnityEngine
AudioMixer mixer
    Slider masterSlider
    Slider musicSlider
    Slider masterSFXSlider
    LoadoutState loadoutState
    DataDeleteConfirmation confirmationPopup
    float m_MasterVolume
    float m_MusicVolume
    float m_MasterSFXVolume
    local k_MinVolume = -80f
    local k_MasterVolumeFloatName = "MasterVolume"
    local k_MusicVolumeFloatName = "MusicVolume"
    local k_MasterSFXVolumeFloatName = "MasterSFXVolume"
    local function Open()
    {
        .Parent(true)
        UpdateUI()
end
    local function Close()
    {
		PlayerData.instance.Save ()
        .Parent(false)
end
    local function UpdateUI()
    {
        mixer.GetFloat(k_MasterVolumeFloatName, out m_MasterVolume)
        mixer.GetFloat(k_MusicVolumeFloatName, out m_MusicVolume)
        mixer.GetFloat(k_MasterSFXVolumeFloatName, out m_MasterSFXVolume)
        masterSlider.value = 1.0f - (m_MasterVolume / k_MinVolume)
        musicSlider.value = 1.0f - (m_MusicVolume / k_MinVolume)
        masterSFXSlider.value = 1.0f - (m_MasterSFXVolume / k_MinVolume)
end
    local function DeleteData()
    {
        confirmationPopup.Open(loadoutState)
end
    local function MasterVolumeChangeValue(float value)
    {
        m_MasterVolume = k_MinVolume * (1.0f - value)
        mixer.SetFloat(k_MasterVolumeFloatName, m_MasterVolume)
		PlayerData.instance.masterVolume = m_MasterVolume
end
    local function MusicVolumeChangeValue(float value)
    {
        m_MusicVolume = k_MinVolume * (1.0f - value)
        mixer.SetFloat(k_MusicVolumeFloatName, m_MusicVolume)
		PlayerData.instance.musicVolume = m_MusicVolume
end
    local function MasterSFXVolumeChangeValue(float value)
    {
        m_MasterSFXVolume = k_MinVolume * (1.0f - value)
        mixer.SetFloat(k_MasterSFXVolumeFloatName, m_MasterSFXVolume)
		PlayerData.instance.masterSFXVolume = m_MasterSFXVolume
end
end