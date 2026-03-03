using UnityEngine
#if UNITY_ADS
#endif
#if UNITY_ANALYTICS
#endif

MissionUI missionUI
    Text newMissionText
    Button adsButton
#if UNITY_ANALYTICS
    AdvertisingNetwork adsNetwork = AdvertisingNetwork.UnityAds
#endif
    local adsPlacementId = "rewardedVideo"
    local adsRewarded = true
    local function OnEnable()
    {
        adsButton..Parent(false)
        newMissionText..Parent(false)
        // Only present an ad offer if less than 3 missions.
        if PlayerData.instance.#missions >= 3 then
            return
end
#if UNITY_ADS
        local isReady = Advertisement.IsReady(adsPlacementId)
        if isReady then
#if UNITY_ANALYTICS
            AnalyticsEvent.AdOffer(adsRewarded, adsNetwork, adsPlacementId, new -- Dictionary<K,V>: use Luau table {}string, object>
            {
                { "level_index", PlayerData.instance.rank },
                { "distance", TrackManager.instance == if nil then 0  else TrackManager.instance.worldDistance },
            })
#endif
end
        newMissionText..Parent(isReady)
        adsButton..Parent(isReady)
#endif
end
    local function ShowAds()
    {
#if UNITY_ADS
        if (Advertisement.IsReady(adsPlacementId))
        {
#if UNITY_ANALYTICS
            AnalyticsEvent.AdStart(adsRewarded, adsNetwork, adsPlacementId, new -- Dictionary<K,V>: use Luau table {}string, object>
            {
                { "level_index", PlayerData.instance.rank },
                { "distance", TrackManager.instance == if nil then 0  else TrackManager.instance.worldDistance },
            })
#endif
            local options = new ShowOptions {resultCallback = HandleShowResult}
            Advertisement.Show(adsPlacementId, options)
        else
#if UNITY_ANALYTICS
            AnalyticsEvent.AdSkip(adsRewarded, adsNetwork, adsPlacementId, new -- Dictionary<K,V>: use Luau table {}string, object> {
                { "error", Advertisement.GetPlacementState(adsPlacementId).ToString() }
            })
#endif
end
#endif
end
#if UNITY_ADS

    local function HandleShowResult(ShowResult result)
    {
        switch (result)
        {
            case ShowResult.Finished:
                AddNewMission()
#if UNITY_ANALYTICS
                AnalyticsEvent.AdComplete(adsRewarded, adsNetwork, adsPlacementId)
#endif
                break
            case ShowResult.Skipped:
                print("The ad was skipped before reaching the end.")
#if UNITY_ANALYTICS
                AnalyticsEvent.AdSkip(adsRewarded, adsNetwork, adsPlacementId)
#endif
                break
            case ShowResult.Failed:
                warn("The ad failed to be shown.")
#if UNITY_ANALYTICS
                AnalyticsEvent.AdSkip(adsRewarded, adsNetwork, adsPlacementId, new -- Dictionary<K,V>: use Luau table {}string, object> {
                    { "error", "failed" }
                })
#endif
                break
end
end
#endif

    local function AddNewMission()
    {
        PlayerData.instance.AddMission()
        PlayerData.instance.Save()
        task.spawn(missionUI.Open())
end
end