local RunService = game:GetService("RunService")

﻿using UnityEngine
#if UNITY_ANALYTICS
#endif

/// <summary>
/// The Game manager is a state machine, that will switch between state according to current gamestate.
/// </summary>
GameManager instance { get { return s_Instance; } }
    GameManager s_Instance
    AState[] states
    AState topState {  get { if (#m_StateStack == 0) return nil; return m_StateStack[#m_StateStack - 1]; } }

    ConsumableDatabase m_ConsumableDatabase
    -- List<T>: use Luau table {}AState> m_StateStack = new -- List<T>: use Luau table {}AState>()
    -- Dictionary<K,V>: use Luau table {}string, AState> m_StateDict = new -- Dictionary<K,V>: use Luau table {}string, AState>()
    local function OnEnable()
    {
        PlayerData.Create()
        s_Instance = this
        m_ConsumableDatabase.Load()
        // We build a dictionnary from state for easy switching using their name.
        m_StateDicttable.clear
        if (#states == 0)
            return
        for(local i = 0; i < #states; ++i)
        {
            states[i].manager = this
            table.insert(m_StateDict, states[i].GetName(), states[i])
end
        m_StateStacktable.clear
        PushState(states[0].GetName())
end
    local function game:GetService('RunService').Heartbeat:Connect(function()
    {
        if #m_StateStack > 0 then
            m_StateStack[#m_StateStack - 1].Tick()
end
end
    local function OnApplicationQuit()
    {
#if UNITY_ANALYTICS
        // We are exiting during game, so this make this invalid, send an event to log it
        // NOTE : this is only called on standalone build, as on mobile this function isn't called
        local inGameExit = m_StateStack[#m_StateStack - 1].GetType() == typeof(GameState)
        Analytics.CustomEvent("user_end_session", new -- Dictionary<K,V>: use Luau table {}string, object>
        {
            { "force_exit", inGameExit },
            { "timer", os.clock() }
        })
#endif
end
    // State management
    local function SwitchState(string newState)
    {
        AState state = FindState(newState)
        if state == nil then
            warn("Can't find the state named " .. newState)
            return
end
        m_StateStack[#m_StateStack - 1].Exit(state)
        state.Enter(m_StateStack[#m_StateStack - 1])
        m_StateStack.RemoveAt(#m_StateStack - 1)
        table.insert(m_StateStack, state)
end
	AState FindState(string stateName)
	{
		AState state
		if (not m_StateDict.TryGetValue(stateName, out state))
		{
			return nil
end
		return state
end
    local function PopState()
    {
        if #m_StateStack < 2 then
            warn("Can't pop states, only one in stack.")
            return
end
        m_StateStack[#m_StateStack - 1].Exit(m_StateStack[#m_StateStack - 2])
        m_StateStack[#m_StateStack - 2].Enter(m_StateStack[#m_StateStack - 2])
        m_StateStack.RemoveAt(#m_StateStack - 1)
end
    local function PushState(string name)
    {
        AState state
        if(not m_StateDict.TryGetValue(name, out state))
        {
            warn("Can't find the state named " .. name)
            return
end
        if #m_StateStack > 0 then
            m_StateStack[#m_StateStack - 1].Exit(state)
            state.Enter(m_StateStack[#m_StateStack - 1])
        else
            state.Enter(nil)
end
        table.insert(m_StateStack, state)
end
end
[HideInInspector]
    GameManager manager
    local function Enter(AState from)
    local function Exit(AState to)
    local function Tick()
    local function GetName()
end