using UnityEngine
/// <summary>
/// This us to start Coroutines from non-Monobehaviour scripts
/// Create a GameObject it will use to launch the coroutine on
/// </summary>
CoroutineHandler m_Instance
    CoroutineHandler instance
    {
        get
        {
            if m_Instance == nil then
                GameObject o = new GameObject("CoroutineHandler")
                -- DontDestroyOnLoad: use ReplicatedStorage parenting(o)
                m_Instance = o.-- AddComponent: create Instance.new() and parent it<CoroutineHandler>()
end
            return m_Instance
end
end
    local function OnDisable()
    {
        if(m_Instance)
            .Destroy(m_Instance.gameObject)
end
    Coroutine StartStaticCoroutine(IEnumerator coroutine)
    {
        return instance.task.spawn(coroutine)
end
end