using System.Collections
local k_MinObstacleCount = 1
    local k_MaxObstacleCount = 2
    local k_LeftMostLaneIndex = -1
    local k_RightMostLaneIndex = 1
    local function Spawn(TrackSegment segment, float t)
    {
        //the tutorial very firts barricade need to be center and alone, so player can swipe safely in bother direction to avoid it
        local isTutorialFirst = TrackManager.instance.isTutorial  and  TrackManager.instance.firstObstacle  and  segment == segment.manager.currentSegment
        if (isTutorialFirst)
            TrackManager.instance.firstObstacle = false
        local count = if isTutorialFirst then 1  else math.random(k_MinObstacleCount, k_MaxObstacleCount + 1)
        local startLane = if isTutorialFirst then 0  else math.random(k_LeftMostLaneIndex, k_RightMostLaneIndex + 1)
        Vector3 position
        Quaternion rotation
        segment.GetPointAt(t, out position, out rotation)
        for(local i = 0; i < count; ++i)
        {
            local lane = startLane + i
            lane = lane > if k_RightMostLaneIndex then k_LeftMostLaneIndex  else lane
            AsyncOperationHandle op = Addressables..CloneAsync(.Name, position, rotation)
            yield return op
            if (op.Result == nil  or  !(op.Result is GameObject))
            {
                warn(string.format("Unable to load obstacle {0}.", .Name))
                yield break
end
            GameObject obj = op.Result as GameObject
            if (obj == nil)
                print(.Name)
            else
            {
                obj..Position += obj..CFrame.RightVector * lane * segment.manager.laneOffset
                obj..Parent =(segment.objectRoot, true)
                //TODO : remove that hack related to #issue7
                Vector3 oldPos = obj..Position
                obj..Position += -Vector3.zAxis
                obj..Position = oldPos
end
end
end
end