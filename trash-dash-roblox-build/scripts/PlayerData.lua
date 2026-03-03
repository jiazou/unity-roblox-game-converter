using UnityEngine
#if UNITY_ANALYTICS
#endif
#if UNITY_EDITOR
#endif

struct HighscoreEntry : System.IComparable<HighscoreEntry>
{
	string name
	int score
	local function CompareTo(HighscoreEntry other)
	{
		// We want to sort from highest to lowest, so inverse the comparison.
		return other.score.CompareTo(score)
end
end
/// <summary>
/// Save data for the game. This is stored locally in this case, but a "better" way to do it would be to store it on a server
/// somewhere to avoid player tampering with it. Here potentially a player could modify the binary file to add premium currency.
/// </summary>
PlayerData m_Instance
    PlayerData instance { get { return m_Instance; } }

    local saveFile = ""
    int coins
    int premium
    -- Dictionary<K,V>: use Luau table {}Consumable.ConsumableType, int> consumables = new -- Dictionary<K,V>: use Luau table {}Consumable.ConsumableType, int>();   // Inventory of owned consumables and quantity.

    -- List<T>: use Luau table {}string> characters = new -- List<T>: use Luau table {}string>();    // Inventory of characters owned.
    int usedCharacter;                               // Currently equipped character.
    local usedAccessory = -1
    -- List<T>: use Luau table {}string> characterAccessories = new -- List<T>: use Luau table {}string>();  // List of owned accessories, in the form "charName:accessoryName".
    -- List<T>: use Luau table {}string> themes = new -- List<T>: use Luau table {}string>();                // Owned themes.
    int usedTheme;                                           // Currently used theme.
    -- List<T>: use Luau table {}HighscoreEntry> highscores = new -- List<T>: use Luau table {}HighscoreEntry>()
    -- List<T>: use Luau table {}MissionBase> missions = new -- List<T>: use Luau table {}MissionBase>()
	local previousName = "Trash Cat"
    bool licenceAccepted
    bool tutorialDone
	local masterVolume = float.MinValue, musicVolume = float.MinValue, masterSFXVolume = float.MinValue
    //ftue = First Time User Expeerience. This var is used to track thing a player do for the first time. It increment everytime the user do one of the step
    //e.g. it will increment to 1 when they click Start, to 2 when doing the first run, 3 when running at least 300m etc.
    local ftueLevel = 0
    //Player win a rank ever 300m (e.g. a player having reached 1200m at least once will be rank 4)
    local rank = 0
    // This will allow us to add data even after production, and so keep all existing save STILL valid. See loading & saving for how it work.
    // Note in a real production it would probably reset that to 1 before release (as all dev save don't have to be compatible w/ final product)
    // Then would increment again with every subsequent patches. We kept it to its dev value here for teaching purpose. 
    local s_Version = 12
    local function Consume(Consumable.ConsumableType type)
    {
        if (not consumables.ContainsKey(type))
            return
        consumables[type] -= 1
        if consumables[type] == 0 then
            table.remove(consumables, type)
end
        Save()
end
    local function Add(Consumable.ConsumableType type)
    {
        if (not consumables.ContainsKey(type))
        {
            consumables[type] = 0
end
        consumables[type] += 1
        Save()
end
    local function AddCharacter(string name)
    {
        table.insert(characters, name)
end
    local function AddTheme(string theme)
    {
        table.insert(themes, theme)
end
    local function AddAccessory(string name)
    {
        table.insert(characterAccessories, name)
end
    // Mission management

    // Will add missions until we reach 2 missions.
    local function CheckMissionsCount()
    {
        while (#missions < 2)
            AddMission()
end
    local function AddMission()
    {
        local val = math.random(0, MissionBase.MissionType.MAX)
        MissionBase newMission = MissionBase.GetNewMissionFromType((MissionBase.MissionType)val)
        newMission.Created()
        table.insert(missions, newMission)
end
    local function StartRunMissions(TrackManager manager)
    {
        for(local i = 0; i < #missions; ++i)
        {
            missions[i].RunStart(manager)
end
end
    local function UpdateMissions(TrackManager manager)
    {
        for(local i = 0; i < #missions; ++i)
        {
            missions[i].Update(manager)
end
end
    local function AnyMissionComplete()
    {
        for (local i = 0; i < #missions; ++i)
        {
            if (missions[i].isComplete) return true
end
        return false
end
    local function ClaimMission(MissionBase mission)
    {        
        premium += mission.reward
#if UNITY_ANALYTICS // Using Analytics Standard Events v0.3.0
        AnalyticsEvent.ItemAcquired(
            AcquisitionType.Premium, // Currency type
            "mission",               // Context
            mission.reward,          // Amount
            "anchovies",             // Item ID
            premium,                 // Item balance
            "consumable",            // Item type
            tostring(rank)          // Level
        )
#endif
        
        table.remove(missions, mission)
        CheckMissionsCount()
        Save()
end
	// High Score management

	local function GetScorePlace(int score)
	{
		HighscoreEntry entry = nil --[[ new object ]]
		entry.score = score
		entry.name = ""
		local index = highscores.BinarySearch(entry)
		return index < if 0 then (~index)  else index
end
	local function InsertScore(int score, string name)
	{
		HighscoreEntry entry = nil --[[ new object ]]
		entry.score = score
		entry.name = name
		highscores.Insert(GetScorePlace(score), entry)
        // Keep only the 10 best scores.
        while (#highscores > 10)
            highscores.RemoveAt(#highscores - 1)
end
    // File management

    local function Create()
    {
		if m_Instance == nil then
			m_Instance = nil --[[ new object ]]
            //if we create the PlayerData, mean it's the very first call, so we use that to init the database
            //this allow to always init the database at the earlier we can, i.e. the start screen if started normally on device
            //or the Loadout screen if testing in editor
		    CoroutineHandler.StartStaticCoroutine(CharacterDatabase.LoadDatabase())
		    CoroutineHandler.StartStaticCoroutine(ThemeDatabase.LoadDatabase())
end
        m_Instance.saveFile = Application.persistentDataPath .. "/save.bin"
        if (File.Exists(m_Instance.saveFile))
        {
            // If we have a save, we read it.
            m_Instance.Read()
        else
            // If not we create one with default data.
			NewSave()
end
        m_Instance.CheckMissionsCount()
end
	local function NewSave()
	{
		m_Instance.characterstable.clear
		m_Instance.themestable.clear
		m_Instance.missionstable.clear
		m_Instance.characterAccessoriestable.clear
		m_Instance.consumablestable.clear
		m_Instance.usedCharacter = 0
		m_Instance.usedTheme = 0
		m_Instance.usedAccessory = -1
        m_Instance.coins = 0
        m_Instance.premium = 0
		m_Instance.table.insert(characters, "Trash Cat")
		m_Instance.table.insert(themes, "Day")
        m_Instance.ftueLevel = 0
        m_Instance.rank = 0
        m_Instance.CheckMissionsCount()
		m_Instance.Save()
end
    local function Read()
    {
        BinaryReader r = new BinaryReader(new FileStream(saveFile, FileMode.Open))
        local ver = r.ReadInt32()
		if ver < 6 then
			r.Close()
			NewSave()
			r = new BinaryReader(new FileStream(saveFile, FileMode.Open))
			ver = r.ReadInt32()
end
        coins = r.ReadInt32()
        consumablestable.clear
        local consumableCount = r.ReadInt32()
        for (local i = 0; i < consumableCount; ++i)
        {
            table.insert(consumables, (Consumable.ConsumableType)r.ReadInt32(), r.ReadInt32())
end
        // Read character.
        characterstable.clear
        local charCount = r.ReadInt32()
        for(local i = 0; i < charCount; ++i)
        {
            local charName = r.ReadString()
            if (table.find(charName, "Raccoon")  and  ver < 11)
            {//in 11 version, we renamed Raccoon (fixing spelling) so we need to patch the save to give the character if player had it already
                charName = charName.Replace("Racoon", "Raccoon")
end
            table.insert(characters, charName)
end
        usedCharacter = r.ReadInt32()
        // Read character accesories.
        characterAccessoriestable.clear
        local accCount = r.ReadInt32()
        for (local i = 0; i < accCount; ++i)
        {
            table.insert(characterAccessories, r.ReadString())
end
        // Read Themes.
        themestable.clear
        local themeCount = r.ReadInt32()
        for (local i = 0; i < themeCount; ++i)
        {
            table.insert(themes, r.ReadString())
end
        usedTheme = r.ReadInt32()
        // Save contains the version they were written with. If data are added bump the version & test for that version before loading that data.
        if ver >= 2 then
            premium = r.ReadInt32()
end
        // Added highscores.
		if ver >= 3 then
			highscorestable.clear
			local count = r.ReadInt32()
			for (local i = 0; i < count; ++i)
			{
				HighscoreEntry entry = nil --[[ new object ]]
				entry.name = r.ReadString()
				entry.score = r.ReadInt32()
				table.insert(highscores, entry)
end
end
        // Added missions.
        if ver >= 4 then
            missionstable.clear
            local count = r.ReadInt32()
            for(local i = 0; i < count; ++i)
            {
                MissionBase.MissionType type = (MissionBase.MissionType)r.ReadInt32()
                MissionBase tempMission = MissionBase.GetNewMissionFromType(type)
                tempMission.Deserialize(r)
                if tempMission ~= nil then
                    table.insert(missions, tempMission)
end
end
end
        // Added highscore previous name used.
		if ver >= 7 then
			previousName = r.ReadString()
end
        if ver >= 8 then
            licenceAccepted = r.ReadBoolean()
end
		if ver >= 9 then
			masterVolume = r.ReadSingle ()
			musicVolume = r.ReadSingle ()
			masterSFXVolume = r.ReadSingle ()
end
        if ver >= 10 then
            ftueLevel = r.ReadInt32()
            rank = r.ReadInt32()
end
        if ver >= 12 then
            tutorialDone = r.ReadBoolean()
end
        r.Close()
end
    local function Save()
    {
        BinaryWriter w = new BinaryWriter(new FileStream(saveFile, FileMode.OpenOrCreate))
        w.Write(s_Version)
        w.Write(coins)
        w.Write(#consumables)
        for _, v in(KeyValuePair<Consumable.ConsumableType, int> p in consumables)
        {
            w.Write(p.Key)
            w.Write(p.Value)
end
        // Write characters.
        w.Write(#characters)
        for _, v in (string c in characters)
        {
            w.Write(c)
end
        w.Write(usedCharacter)
        w.Write(#characterAccessories)
        for _, v in (string a in characterAccessories)
        {
            w.Write(a)
end
        // Write themes.
        w.Write(#themes)
        for _, v in (string t in themes)
        {
            w.Write(t)
end
        w.Write(usedTheme)
        w.Write(premium)
		// Write highscores.
		w.Write(#highscores)
		for(local i = 0; i < #highscores; ++i)
		{
			w.Write(highscores[i].name)
			w.Write(highscores[i].score)
end
        // Write missions.
        w.Write(#missions)
        for(local i = 0; i < #missions; ++i)
        {
            w.Write(missions[i].GetMissionType())
            missions[i].Serialize(w)
end
		// Write name.
		w.Write(previousName)
        w.Write(licenceAccepted)
		w.Write (masterVolume)
		w.Write (musicVolume)
		w.Write (masterSFXVolume)
        w.Write(ftueLevel)
        w.Write(rank)
        w.Write(tutorialDone)
        w.Close()
endend
// Helper cheat in the editor for test purpose
#if UNITY_EDITOR
[MenuItem("Trash Dash Debug/Clear Save")]
    local function ClearSave()
    {
        File.Delete(Application.persistentDataPath .. "/save.bin")
end
    [MenuItem("Trash Dash Debug/Give 1000000 fishbones and 1000 premium")]
    local function GiveCoins()
    {
        PlayerData.instance.coins += 1000000
		PlayerData.instance.premium += 1000
        PlayerData.instance.Save()
end
    [MenuItem("Trash Dash Debug/Give 10 Consumables of each types")]
    local function AddConsumables()
    {
       
        for(local i = 0; i < ShopItemList.#s_ConsumablesTypes; ++i)
        {
            Consumable c = ConsumableDatabase.GetConsumbale(ShopItemList.s_ConsumablesTypes[i])
            if c ~= nil then
                PlayerData.instance.consumables[c.GetConsumableType()] = 10
end
end
        PlayerData.instance.Save()
end
end
#endif