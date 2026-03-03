using UnityEngine
/// <summary>
/// This used to modify the game state (e.g. limit length run, seed etc.)
/// Subclass it and wanted messages to handle the state.
/// </summary>
local function OnRunStart(GameState state)
	{
end
	local function OnRunTick(GameState state)
	{
end
	//return true if the gameobver screen should be displayed, returning false will return directly to loadout (useful for challenge)
	local function OnRunEnd(GameState state)
	{
		return true
end
end
// The following classes are all the samples modifiers.

float distance
	LimitedLengthRun(float dist)
	{
		distance = dist
end
	local function OnRunTick(GameState state)
	{
		if state.trackManager.worldDistance >= distance then
			state.trackManager.characterController.currentLife = 0
end
end
	local function OnRunStart(GameState state)
	{
end
	local function OnRunEnd(GameState state)
	{
		state.QuitToLoadout()
		return false
end
end
int m_Seed
    local k_DaysInAWeek = 7
	SeededRun()
	{
        m_Seed = System.DateTime.Now.DayOfYear / k_DaysInAWeek
end
	local function OnRunStart(GameState state)
	{
		state.trackManager.trackSeed = m_Seed
end
	local function OnRunEnd(GameState state)
	{
		state.QuitToLoadout()
		return false
end
end
local function OnRunTick(GameState state)
	{
		if (state.trackManager.characterController.currentLife > 1)
			state.trackManager.characterController.currentLife = 1
end
	local function OnRunStart(GameState state)
	{
end
	local function OnRunEnd(GameState state)
	{
		state.QuitToLoadout()
		return false
end
end