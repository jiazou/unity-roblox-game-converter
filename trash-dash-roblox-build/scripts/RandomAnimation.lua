using UnityEngine
string parameter
	int count
	local function OnStateEnter(Animator animator, AnimatorStateInfo stateInfo, int layerIndex)
	{
		animator.SetInteger(parameter, math.random(0, count))
end
end