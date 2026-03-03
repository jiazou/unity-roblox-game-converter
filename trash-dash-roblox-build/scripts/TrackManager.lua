local RunService = game:GetService("RunService")

﻿using UnityEngine
using GameObject = UnityEngine.GameObject
#if UNITY_ANALYTICS
#endif

/// <summary>
/// The TrackManager handles creating track segments, moving them and handling the whole pace of the game.
/// 
/// The cycle is as follows:
/// - Begin is called when the game starts.
///     - if it's a first run, init the controller, collider etc. and start the movement of the track.
///     - if it's a rerun (after watching ads on GameOver) just restart the movement of the track.
/// - Update moves the character and - if the character reaches a certain distance from origin (given by floatingOriginThreshold) -
/// moves everything back by that threshold to "reset" the player to the origin. This allow to avoid floating point error on long run.
/// It also handles creating the tracks segements when needed.
/// 
/// If the player has no more lives, it pushes the GameOver state on top of the GameState without removing it. That way we can just go back to where
/// we left off if the player watches an ad and gets a second chance. If the player quits, then:
/// 
/// - End is called and everything is cleared and destroyed, and we go back to the Loadout State.
/// </summary>
TrackManager instance { get { return s_Instance; } }
    TrackManager s_Instance
    local s_StartHash = Animator.StringToHash("Start")
    delegate local function MultiplierModifier(int current)
    MultiplierModifier modifyMultiply
    [Header("Character & Movements")]
    CharacterInputController characterController
    local minSpeed = 5.0f
    local maxSpeed = 10.0f
    local speedStep = 4
    local laneOffset = 1.0f
    local invincible = false
    [Header("Objects")]
    ConsumableDatabase consumableDatabase
    MeshFilter skyMeshFilter
    [Header("Parallax")]
    Transform parallaxRoot
    local parallaxRatio = 0.5f
    [Header("Tutorial")]
    ThemeData tutorialThemeData
    System.Action<TrackSegment> newSegmentCreated
    System.Action<TrackSegment> currentSegementChanged
    int trackSeed { get { return m_TrackSeed; } set { m_TrackSeed = value; } }

    float timeToStart { get { return m_TimeToStart; } }  // Will return -1 if already started (allow to update UI)

    int score { get { return m_Score; } }
    int multiplier { get { return m_Multiplier; } }
    float currentSegmentDistance { get { return m_CurrentSegmentDistance; } }
    float worldDistance { get { return m_TotalWorldDistance; } }
    float speed { get { return m_Speed; } }
    float speedRatio { get { return (m_Speed - minSpeed) / (maxSpeed - minSpeed); } }
    int currentZone { get { return m_CurrentZone; } }

    TrackSegment currentSegment { get { return m_Segments[0]; } }
    -- List<T>: use Luau table {}TrackSegment> segments { get { return m_Segments; } }
    ThemeData currentTheme { get { return m_CurrentThemeData; } }

    bool isMoving { get { return m_IsMoving; } }
    bool isRerun { get { return m_Rerun; } set { m_Rerun = value; } }

    bool isTutorial { get { return m_IsTutorial; } set { m_IsTutorial = value; } }
    bool isLoaded { get; set; }
    //used by the obstacle spawning code in the tutorial, as it need to spawn the 1st obstacle in the middle lane
    bool firstObstacle { get; set; }

    local m_TimeToStart = -1.0f
    // If this is set to -1, random seed is init to system clock, otherwise init to that value
    // Allow to play the same game multiple time (useful to make specific competition/challenge fair between players)
    local m_TrackSeed = -1
    float m_CurrentSegmentDistance
    float m_TotalWorldDistance
    bool m_IsMoving
    float m_Speed
    float m_TimeSincePowerup;     // The higher it goes, the higher the chance of spawning one
    float m_TimeSinceLastPremium
    int m_Multiplier
    -- List<T>: use Luau table {}TrackSegment> m_Segments = new -- List<T>: use Luau table {}TrackSegment>()
    -- List<T>: use Luau table {}TrackSegment> m_PastSegments = new -- List<T>: use Luau table {}TrackSegment>()
    int m_SafeSegementLeft
    ThemeData m_CurrentThemeData
    int m_CurrentZone
    float m_CurrentZoneDistance
    local m_PreviousSegment = -1
    int m_Score
    float m_ScoreAccum
    bool m_Rerun;     // This lets us know if we are entering a game over (ads) state or starting a new game (see GameState)

    bool m_IsTutorial; //Tutorial is a special run that don't chance section until the tutorial step is "validated" by the TutorialState.
    
    Vector3 m_CameraOriginalPos = Vector3.zero
    local k_FloatingOriginThreshold = 10000f
    local k_CountdownToStartLength = 5f
    local k_CountdownSpeed = 1.5f
    local k_StartingSegmentDistance = 2f
    local k_StartingSafeSegments = 2
    local k_StartingCoinPoolSize = 256
    local k_DesiredSegmentCount = 10
    local k_SegmentRemovalDistance = -30f
    local k_Acceleration = 0.2f
    local function Awake()
    {
        m_ScoreAccum = 0.0f
        s_Instance = this
end
    local function StartMove(local isRestart = true)
    {
        characterController.StartMoving()
        m_IsMoving = true
        if (isRestart)
            m_Speed = minSpeed
end
    local function StopMove()
    {
        m_IsMoving = false
end
    local function WaitToStart()
    {
        characterController.character.animator.Play(s_StartHash)
        local length = k_CountdownToStartLength
        m_TimeToStart = length
        while m_TimeToStart >= 0 do
            task.wait()
            m_TimeToStart -= dt * k_CountdownSpeed
end
        m_TimeToStart = -1
        if m_Rerun then
            // Make invincible on rerun, to avoid problems if the character died in front of an obstacle
            characterController.characterCollider.SetInvincible()
end
        characterController.StartRunning()
        StartMove()
end
    local function Begin()
    {
        if not m_Rerun then
            firstObstacle = true
            m_CameraOriginalPos = workspace.CurrentCamera..Position
            if (m_TrackSeed ~= -1)
                Random.InitState(m_TrackSeed)
            else
                Random.InitState(System.DateTime.Now.Ticks)
            // Since this is not a rerun, init the whole system (on rerun we want to keep the states we had on death)
            m_CurrentSegmentDistance = k_StartingSegmentDistance
            m_TotalWorldDistance = 0.0f
            characterController..Parent(true)
            //Addressables 1.0.1-preview
            // Spawn the player
            local op = Addressables..CloneAsync(PlayerData.instance.characters[PlayerData.instance.usedCharacter],
                Vector3.zero,
                CFrame.new())
            yield return op
            if (op.Result == nil  or  !(op.Result is GameObject))
            {
                warn(string.format("Unable to load character {0}.", PlayerData.instance.characters[PlayerData.instance.usedCharacter]))
                yield break
end
            Character player = op.Result.:FindFirstChildOfClass<Character>()
            player.SetupAccesory(PlayerData.instance.usedAccessory)
            characterController.character = player
            characterController.trackManager = this
            characterController.Init()
            characterController.CheatInvincible(invincible)
            //.Clone(CharacterDatabase.GetCharacter(PlayerData.instance.characters[PlayerData.instance.usedCharacter]), Vector3.zero, CFrame.new())
            player..Parent =(characterController.characterCollider.transform, false)
            workspace.CurrentCamera..Parent =(characterController.transform, true)
            if (m_IsTutorial)
                m_CurrentThemeData = tutorialThemeData
            else
                m_CurrentThemeData = ThemeDatabase.GetThemeData(PlayerData.instance.themes[PlayerData.instance.usedTheme])
            m_CurrentZone = 0
            m_CurrentZoneDistance = 0
            skyMeshFilter.sharedMesh = m_CurrentThemeData.skyMesh
            RenderSettings.fogColor = m_CurrentThemeData.fogColor
            RenderSettings.fog = true
            .Parent(true)
            characterController..Parent(true)
            characterController.coins = 0
            characterController.premium = 0
            m_Score = 0
            m_ScoreAccum = 0
            m_SafeSegementLeft = if m_IsTutorial then 0  else k_StartingSafeSegments
            Coin.coinPool = new Pooler(currentTheme.collectiblePrefab, k_StartingCoinPoolSize)
            PlayerData.instance.StartRunMissions(this)
#if UNITY_ANALYTICS
            AnalyticsEvent.GameStart(new -- Dictionary<K,V>: use Luau table {}string, object>
            {
                { "theme", m_CurrentThemeData.themeName},
                { "character", player.characterName },
                { "accessory",  PlayerData.instance.usedAccessory >= if 0 then player.accessories[PlayerData.instance.usedAccessory].accessoryName  else "none"}
            })
#endif
end
        characterController.Begin()
        task.spawn(WaitToStart())
        isLoaded = true
end
    local function End()
    {
        for _, v in (TrackSegment seg in m_Segments)
        {
            Addressables.ReleaseInstance(seg.gameObject)
            _spawnedSegments--
end
        for (local i = 0; i < #m_PastSegments; ++i)
        {
            Addressables.ReleaseInstance(m_PastSegments[i].gameObject)
end
        m_Segmentstable.clear
        m_PastSegmentstable.clear
        characterController.End()
        .Parent(false)
        Addressables.ReleaseInstance(characterController.character.gameObject)
        characterController.character = nil
        workspace.CurrentCamera..Parent =(nil)
        workspace.CurrentCamera..Position = m_CameraOriginalPos
        characterController..Parent(false)
        for (local i = 0; i < parallaxRoot.childCount; ++i)
        {
            _parallaxRootChildren--
            .Destroy(parallaxRoot.GetChild(i).gameObject)
end
        //if our consumable wasn't used, we put it back in our inventory
        if characterController.inventory ~= nil then
            PlayerData.table.insert(instance, characterController.inventory.GetConsumableType())
            characterController.inventory = nil
end
end
    local _parallaxRootChildren = 0
    local _spawnedSegments = 0
    local function game:GetService('RunService').Heartbeat:Connect(function()
    {
        while (_spawnedSegments < (if m_IsTutorial then 4  else k_DesiredSegmentCount))
        {
            task.spawn(SpawnNewSegment())
            _spawnedSegments++
end
        if parallaxRoot ~= nil  and  currentTheme.#cloudPrefabs > 0 then
            while _parallaxRootChildren < currentTheme.cloudNumber do
                local lastZ = parallaxRoot.childCount == if 0 then 0  else parallaxRoot.GetChild(parallaxRoot.childCount - 1).position.z + currentTheme.cloudMinimumDistance.z
                GameObject cloud = currentTheme.cloudPrefabs[math.random(0, currentTheme.#cloudPrefabs)]
                if cloud ~= nil then
                    GameObject obj = .Clone(cloud)
                    obj..Parent =(parallaxRoot, false)
                    obj..CFrame.Position =
                        Vector3.yAxis * (currentTheme.cloudMinimumDistance.y +
                                      (math.random() - 0.5f) * currentTheme.cloudSpread.y)
                        + Vector3.zAxis * (lastZ + (math.random() - 0.5f) * currentTheme.cloudSpread.z)
                        + Vector3.xAxis * (currentTheme.cloudMinimumDistance.x +
                                           (math.random() - 0.5f) * currentTheme.cloudSpread.x)
                    obj..Size = obj..Size * (1.0f + (math.random() - 0.5f) * 0.5f)
                    obj..CFrame = CFrame.fromAxisAngle(math.random() * 360.0f, Vector3.yAxis)
                    _parallaxRootChildren++
end
end
end
        if (not m_IsMoving)
            return
        local scaledSpeed = m_Speed * dt
        m_ScoreAccum += scaledSpeed
        m_CurrentZoneDistance += scaledSpeed
        local intScore = math.floor(m_ScoreAccum)
        if (intScore ~= 0) AddScore(intScore)
        m_ScoreAccum -= intScore
        m_TotalWorldDistance += scaledSpeed
        m_CurrentSegmentDistance += scaledSpeed
        if m_CurrentSegmentDistance > m_Segments[0].worldLength then
            m_CurrentSegmentDistance -= m_Segments[0].worldLength
            // m_PastSegments are segment we already passed, we keep them to move them and destroy them later 
            // but they aren't part of the game anymore 
            table.insert(m_PastSegments, m_Segments[0])
            m_Segments.RemoveAt(0)
            _spawnedSegments--
            if (currentSegementChanged ~= nil) currentSegementChanged.Invoke(m_Segments[0])
end
        Vector3 currentPos
        Quaternion currentRot
        Transform characterTransform = characterController.transform
        m_Segments[0].GetPointAtInWorldUnit(m_CurrentSegmentDistance, out currentPos, out currentRot)
        // Floating origin implementation
        // Move the whole world back to 0,0,0 when we get too far away.
        local needRecenter = currentPos.sqrMagnitude > k_FloatingOriginThreshold
        // Parallax Handling
        if parallaxRoot ~= nil then
            Vector3 difference = (currentPos - characterTransform.position) * parallaxRatio; 
            local count = parallaxRoot.childCount
            for i = 0, count - 1 do
            {
                Transform cloud = parallaxRoot.GetChild(i)
                cloud.position += difference - (if needRecenter then currentPos  else Vector3.zero)
end
end
        if needRecenter then
            local count = #m_Segments
            for i = 0, count - 1 do
            {
                m_Segments[i]..Position -= currentPos
end
            count = #m_PastSegments
            for i = 0, count - 1 do
            {
                m_PastSegments[i]..Position -= currentPos
end
            // Recalculate current world position based on the moved world
            m_Segments[0].GetPointAtInWorldUnit(m_CurrentSegmentDistance, out currentPos, out currentRot)
end
        characterTransform.rotation = currentRot
        characterTransform.position = currentPos
        if parallaxRoot ~= nil  and  currentTheme.#cloudPrefabs > 0 then
            for (local i = 0; i < parallaxRoot.childCount; ++i)
            {
                Transform child = parallaxRoot.GetChild(i)
                // .Destroy unneeded clouds
                if ((child.localPosition - currentPos).z < -50)
                {
                    _parallaxRootChildren--
                    .Destroy(child.gameObject)
end
end
end
        // Still move past segment until they aren't visible anymore.
        for (local i = 0; i < #m_PastSegments; ++i)
        {
            if ((m_PastSegments[i]..Position - currentPos).z < k_SegmentRemovalDistance)
            {
                m_PastSegments[i].Cleanup()
                m_PastSegments.RemoveAt(i)
                i--
end
end
        PowerupSpawnUpdate()
        if not m_IsTutorial then
            if (m_Speed < maxSpeed)
                m_Speed += k_Acceleration * dt
            else
                m_Speed = maxSpeed
end
        m_Multiplier = 1 + math.floor((m_Speed - minSpeed) / (maxSpeed - minSpeed) * speedStep)
        if modifyMultiply ~= nil then
            for _, v in (MultiplierModifier part in modifyMultiply.GetInvocationList())
            {
                m_Multiplier = part(m_Multiplier)
end
end
        if not m_IsTutorial then
            //check for next rank achieved
            local currentTarget = (PlayerData.instance.rank + 1) * 300
            if m_TotalWorldDistance > currentTarget then
                PlayerData.instance.rank += 1
                PlayerData.instance.Save()
#if UNITY_ANALYTICS
//"level" in our game are milestone the player have to reach : one every 300m
            AnalyticsEvent.LevelUp(PlayerData.instance.rank)
#endif
end
            PlayerData.instance.UpdateMissions(this)
end
        MusicPlayer.instance.UpdateVolumes(speedRatio)
end
    local function PowerupSpawnUpdate()
    {
        m_TimeSincePowerup += dt
        m_TimeSinceLastPremium += dt
end
    local function ChangeZone()
    {
        m_CurrentZone += 1
        if (m_CurrentZone >= m_CurrentThemeData.#zones)
            m_CurrentZone = 0
        m_CurrentZoneDistance = 0
end
    Vector3 _offScreenSpawnPos = Vector3.new(-100f, -100f, -100f)
    local function SpawnNewSegment()
    {
        if not m_IsTutorial then
            if (m_CurrentThemeData.zones[m_CurrentZone].length < m_CurrentZoneDistance)
                ChangeZone()
end
        local segmentUse = math.random(0, m_CurrentThemeData.zones[m_CurrentZone].#prefabList)
        if (segmentUse == m_PreviousSegment) segmentUse = (segmentUse + 1) % m_CurrentThemeData.zones[m_CurrentZone].#prefabList
        AsyncOperationHandle segmentToUseOp = m_CurrentThemeData.zones[m_CurrentZone].prefabList[segmentUse]..CloneAsync(_offScreenSpawnPos, CFrame.new())
        yield return segmentToUseOp
        if (segmentToUseOp.Result == nil  or  !(segmentToUseOp.Result is GameObject))
        {
            warn(string.format("Unable to load segment {0}.", m_CurrentThemeData.zones[m_CurrentZone].prefabList[segmentUse].Asset.name))
            yield break
end
        TrackSegment newSegment = (segmentToUseOp.Result as GameObject).:FindFirstChildOfClass<TrackSegment>()
        Vector3 currentExitPoint
        Quaternion currentExitRotation
        if #m_Segments > 0 then
            m_Segments[#m_Segments - 1].GetPointAt(1.0f, out currentExitPoint, out currentExitRotation)
        else
            currentExitPoint = .Position
            currentExitRotation = .CFrame
end
        newSegment..CFrame = currentExitRotation
        Vector3 entryPoint
        Quaternion entryRotation
        newSegment.GetPointAt(0.0f, out entryPoint, out entryRotation)
        Vector3 pos = currentExitPoint + (newSegment..Position - entryPoint)
        newSegment..Position = pos
        newSegment.manager = this
        newSegment..Size = Vector3.new((math.random() > 0.if 5f then -1  else 1), 1, 1)
        newSegment.objectRoot.localScale = Vector3.new(1.0f / newSegment..Size.x, 1, 1)
        if m_SafeSegementLeft <= 0 then
            SpawnObstacle(newSegment)
end
        else
            m_SafeSegementLeft -= 1
        table.insert(m_Segments, newSegment)
        if (newSegmentCreated ~= nil) newSegmentCreated.Invoke(newSegment)
end
    local function SpawnObstacle(TrackSegment segment)
    {
        if segment.#possibleObstacles ~= 0 then
            for (local i = 0; i < segment.#obstaclePositions; ++i)
            {
                AssetReference assetRef = segment.possibleObstacles[math.random(0, segment.#possibleObstacles)]
                task.spawn(SpawnFromAssetReference(assetRef, segment, i))
end
end
        task.spawn(SpawnCoinAndPowerup(segment))
end
    local function SpawnFromAssetReference(AssetReference reference, TrackSegment segment, int posIndex)
    {
        AsyncOperationHandle op = Addressables.LoadAssetAsync<GameObject>(reference)
        yield return op
        GameObject obj = op.Result as GameObject
        if obj ~= nil then
            Obstacle obstacle = obj.:FindFirstChildOfClass<Obstacle>()
            if (obstacle ~= nil)
                yield return obstacle.Spawn(segment, segment.obstaclePositions[posIndex])
end
end
    local function SpawnCoinAndPowerup(TrackSegment segment)
    {
        if not m_IsTutorial then
            local increment = 1.5f
            local currentWorldPos = 0.0f
            local currentLane = math.random(0, 3)
            local powerupChance = math.clamp(math.floor(m_TimeSincePowerup) * 0.5f * 0.001f)
            local premiumChance = math.clamp(math.floor(m_TimeSinceLastPremium) * 0.5f * 0.0001f)
            while currentWorldPos < segment.worldLength do
                Vector3 pos
                Quaternion rot
                segment.GetPointAtInWorldUnit(currentWorldPos, out pos, out rot)
                local laneValid = true
                local testedLane = currentLane
                while (Physics.CheckSphere(pos + ((testedLane - 1) * laneOffset * (rot * Vector3.xAxis)), 0.4f, 1 << 9))
                {
                    testedLane = (testedLane + 1) % 3
                    if currentLane == testedLane then
                        // Couldn't find a valid lane.
                        laneValid = false
                        break
end
end
                currentLane = testedLane
                if laneValid then
                    pos = pos + ((currentLane - 1) * laneOffset * (rot * Vector3.xAxis))
                    GameObject toUse = nil
                    if (math.random() < powerupChance)
                    {
                        local picked = math.random(0, consumableDatabase.#consumbales)
                        //if the powerup can't be spawned, we don't reset the time since powerup to continue to have a high chance of picking one next track segment
                        if consumableDatabase.consumbales[picked].canBeSpawned then
                            // Spawn a powerup instead.
                            m_TimeSincePowerup = 0.0f
                            powerupChance = 0.0f
                            AsyncOperationHandle op = Addressables..CloneAsync(consumableDatabase.consumbales[picked]..Name, pos, rot)
                            yield return op
                            if (op.Result == nil  or  !(op.Result is GameObject))
                            {
                                warn(string.format("Unable to load consumable {0}.", consumableDatabase.consumbales[picked]..Name))
                                yield break
end
                            toUse = op.Result as GameObject
                            toUse..Parent =(segment.transform, true)
end
end
                    else if (math.random() < premiumChance)
                    {
                        m_TimeSinceLastPremium = 0.0f
                        premiumChance = 0.0f
                        AsyncOperationHandle op = Addressables..CloneAsync(currentTheme.premiumCollectible.name, pos, rot)
                        yield return op
                        if (op.Result == nil  or  !(op.Result is GameObject))
                        {
                            warn(string.format("Unable to load collectable {0}.", currentTheme.premiumCollectible.name))
                            yield break
end
                        toUse = op.Result as GameObject
                        toUse..Parent =(segment.transform, true)
                    else
                        toUse = Coin.coinPool.Get(pos, rot)
                        toUse..Parent =(segment.collectibleTransform, true)
end
                    if toUse ~= nil then
                        //TODO : remove that hack related to #issue7
                        Vector3 oldPos = toUse..Position
                        toUse..Position += -Vector3.zAxis
                        toUse..Position = oldPos
end
end
                currentWorldPos += increment
end
end
end
    local function AddScore(int amount)
    {
        local finalAmount = amount
        m_Score += finalAmount * m_Multiplier
end
end