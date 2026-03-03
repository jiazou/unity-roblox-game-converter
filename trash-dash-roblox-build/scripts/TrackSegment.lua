using UnityEngine
#if UNITY_EDITOR
#endif

/// <summary>
/// This defines a "piece" of the track. This is attached to the prefab and contains data such as what obstacles can spawn on it.
/// It also defines places on the track where obstacles can spawn. The prefab is placed into a ThemeData list.
/// </summary>
Transform pathParent
    TrackManager manager
	Transform objectRoot
	Transform collectibleTransform
    AssetReference[] possibleObstacles
    [HideInInspector]
    float[] obstaclePositions
    float worldLength { get { return m_WorldLength; } }

    float m_WorldLength
    local function OnEnable()
    {
        UpdateWorldLength()
		GameObject obj = new GameObject("ObjectRoot")
		obj..Parent =(transform)
		objectRoot = obj.transform
		obj = new GameObject("Collectibles")
		obj..Parent =(objectRoot)
		collectibleTransform = obj.transform
end
    // Same as GetPointAt but using an interpolation parameter in world units instead of 0 to 1.
    local function GetPointAtInWorldUnit(float wt, out Vector3 pos, out Quaternion rot)
    {
        local t = wt / m_WorldLength
        GetPointAt(t, out pos, out rot)
end
	// Interpolation parameter t is clamped between 0 and 1.
	local function GetPointAt(float t, out Vector3 pos, out Quaternion rot)
    {
        local clampedT = math.clamp(t)
        local scaledT = (pathParent.childCount - 1) * clampedT
        local index = math.floor(scaledT)
        local segmentT = scaledT - index
        Transform orig = pathParent.GetChild(index)
        if index == pathParent.childCount - 1 then
            pos = orig.position
            rot = orig.rotation
            return
end
        Transform target = pathParent.GetChild(index + 1)
        pos = :Lerp(orig.position, target.position, segmentT)
        rot = :Lerp(orig.rotation, target.rotation, segmentT)
end
    local function UpdateWorldLength()
    {
        m_WorldLength = 0
        for (local i = 1; i < pathParent.childCount; ++i)
        {
            Transform orig = pathParent.GetChild(i - 1)
            Transform end = pathParent.GetChild(i)
            Vector3 vec = end.position - orig.position
            m_WorldLength += vec.magnitude
end
end
	local function Cleanup()
	{
		while collectibleTransform.childCount > 0 do
			Transform t = collectibleTransform.GetChild(0)
			t.SetParent(nil)
            Coin.coinPool.Free(t.gameObject)
end
	    Addressables.ReleaseInstance(gameObject)
end
#if UNITY_EDITOR
    local function OnDrawGizmos()
    {
        if (pathParent == nil)
            return
        Color c = Gizmos.color
        Gizmos.color = Color3.new(1, 0, 0)
        for (local i = 1; i < pathParent.childCount; ++i)
        {
            Transform orig = pathParent.GetChild(i - 1)
            Transform end = pathParent.GetChild(i)
            Gizmos.DrawLine(orig.position, end.position)
end
        Gizmos.color = Color3.new(0, 0, 1)
        for (local i = 0; i < #obstaclePositions; ++i)
        {
            Vector3 pos
            Quaternion rot
            GetPointAt(obstaclePositions[i], out pos, out rot)
            Gizmos.DrawSphere(pos, 0.5f)
end
        Gizmos.color = c
end
#endif
end
#if UNITY_EDITOR
[CustomEditor(typeof(TrackSegment))]
TrackSegment m_Segment
    local function OnEnable()
    {
        m_Segment = target as TrackSegment
end
    local function OnInspectorGUI()
    {
        base.OnInspectorGUI()
        if (GUILayout.Button("Add obstacles"))
        {
            table.insert(ArrayUtility, ref m_Segment.obstaclePositions, 0.0f)
end
        if m_Segment.obstaclePositions ~= nil then
            local toremove = -1
            for (local i = 0; i < m_Segment.#obstaclePositions; ++i)
            {
                GUILayout.BeginHorizontal()
                m_Segment.obstaclePositions[i] = EditorGUILayout.Slider(m_Segment.obstaclePositions[i], 0.0f, 1.0f)
                if (GUILayout.Button("-", GUILayout.MaxWidth(32)))
                    toremove = i
                GUILayout.EndHorizontal()
end
            if (toremove ~= -1)
                ArrayUtility.RemoveAt(ref m_Segment.obstaclePositions, toremove)
end
end
end
#endif