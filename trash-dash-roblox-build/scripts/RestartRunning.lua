using UnityEngine
local s_DeadHash = Animator.StringToHash("Dead")
    local function OnStateExit(Animator animator, AnimatorStateInfo stateInfo, int layerIndex)
    {
        // We don't restart if we go toward the death state
        if (animator.GetBool(s_DeadHash))
            return
        TrackManager.instance.StartMove()
endend