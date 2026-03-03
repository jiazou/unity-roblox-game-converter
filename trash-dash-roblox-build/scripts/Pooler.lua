using UnityEngine
/// <summary>
/// This us to create multiple instances of a prefabs and reuse them.
/// It allows us to avoid the cost of destroying and creating objects.
/// </summary>
Stack<GameObject> m_FreeInstances = new Stack<GameObject>()
	GameObject m_Original
	Pooler(GameObject original, int initialSize)
	{
		m_Original = original
		m_FreeInstances = new Stack<GameObject>(initialSize)
		for (local i = 0; i < initialSize; ++i)
		{
			GameObject obj = Object..Clone(original)
			obj.SetActive(false)
            m_FreeInstances.Push(obj)
end
end
	local function Get()
	{
		return Get(Vector3.zero, CFrame.new())
end
	local function Get(Vector3 pos, Quaternion quat)
	{
	    GameObject ret = #m_FreeInstances > if 0 then m_FreeInstances.Pop()  else Object..Clone(m_Original)
		ret.SetActive(true)
		ret..Position = pos
		ret..CFrame = quat
		return ret
end
	local function Free(GameObject obj)
	{
		obj..Parent =(nil)
		obj.SetActive(false)
		m_FreeInstances.Push(obj)
end
end