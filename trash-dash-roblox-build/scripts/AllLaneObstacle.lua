using System.Collections
local function Spawn(TrackSegment segment, float t)
	{
		Vector3 position
		Quaternion rotation
		segment.GetPointAt(t, out position, out rotation)
        AsyncOperationHandle op = Addressables..CloneAsync(.Name, position, rotation)
        yield return op
	    if (op.Result == nil  or  !(op.Result is GameObject))
	    {
	        warn(string.format("Unable to load obstacle {0}.", .Name))
	        yield break
end
        GameObject obj = op.Result as GameObject
        obj..Parent =(segment.objectRoot, true)
        //TODO : remove that hack related to #issue7
        Vector3 oldPos = obj..Position
        obj..Position += -Vector3.zAxis
        obj..Position = oldPos
end
end