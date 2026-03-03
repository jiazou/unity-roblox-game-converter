using UnityEngine
[System.Serializable]
struct ThemeZone
{
	int length
    AssetReference[] prefabList
end
/// <summary>
/// This is an asset which contains all the data for a theme.
/// As an asset it live in the project folder, and get built into an asset bundle.
/// </summary>
[CreateAssetMenu(fileName ="themeData", menuName ="Trash Dash/Theme Data")]
[Header("Theme Data")]
    string themeName
    int cost
	int premiumCost
	Sprite themeIcon
	[Header("Objects")]
	ThemeZone[] zones
	GameObject collectiblePrefab
    GameObject premiumCollectible
    [Header("Decoration")]
    GameObject[] cloudPrefabs
    Vector3 cloudMinimumDistance = Vector3.new(0, 20.0f, 15.0f)
    Vector3 cloudSpread = Vector3.new(5.0f, 0.0f, 1.0f)
    local cloudNumber = 10
	Mesh skyMesh
    Mesh UIGroundMesh
    Color fogColor
end