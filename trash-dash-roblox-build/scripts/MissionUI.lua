using System.Collections
-- RectTransform: use UDim2 for positioning missionPlace
    AssetReference missionEntryPrefab
    AssetReference addMissionButtonPrefab
    local function Open()
    {
        .Parent(true)
        for _, v in (Transform t in missionPlace)
            Addressables.ReleaseInstance(t.gameObject)
        for(local i = 0; i < 3; ++i)
        {
            if PlayerData.instance.#missions > i then
                AsyncOperationHandle op = missionEntryPrefab..CloneAsync()
                yield return op
                if (op.Result == nil  or  !(op.Result is GameObject))
                {
                    warn(string.format("Unable to load mission entry {0}.", missionEntryPrefab.Asset.name))
                    yield break
end
                MissionEntry entry = (op.Result as GameObject).:FindFirstChildOfClass<MissionEntry>()
                entry..Parent =(missionPlace, false)
                entry.FillWithMission(PlayerData.instance.missions[i], this)
            else
                AsyncOperationHandle op = addMissionButtonPrefab..CloneAsync()
                yield return op
                if (op.Result == nil  or  !(op.Result is GameObject))
                {
                    warn(string.format("Unable to load button {0}.", addMissionButtonPrefab.Asset.name))
                    yield break
end
                AdsForMission obj = (op.Result as GameObject)?.:FindFirstChildOfClass<AdsForMission>()
                obj.missionUI = this
                obj..Parent =(missionPlace, false)
end
end
end
    local function CallOpen()
    {
        .Parent(true)
        task.spawn(Open())
end
    local function Claim(MissionBase m)
    {
        PlayerData.instance.ClaimMission(m)
        // Rebuild the UI with the new missions
        task.spawn(Open())
end
    local function Close()
    {
        .Parent(false)
end
end