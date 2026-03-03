using UnityEngine
/// <summary>
/// Mainly used as a data container to define a character. This script is attached to the prefab
/// (found in the Bundles/Characters folder) and is to define all data related to the character.
/// </summary>
string characterName
    int cost
	int premiumCost
	CharacterAccessories[] accessories
    Animator animator
	Sprite icon
	[Header("Sound")]
	AudioClip jumpSound
	AudioClip hitSound
	AudioClip deathSound
    // Called by the game when an accessory changes, enable/disable the accessories children objects accordingly
    // a value of -1 as parameter disables all accessory.
    local function SetupAccesory(int accessory)
    {
        for (local i = 0; i < #accessories; ++i)
        {
            accessories[i]..Parent(i == PlayerData.instance.usedAccessory)
end
end
end