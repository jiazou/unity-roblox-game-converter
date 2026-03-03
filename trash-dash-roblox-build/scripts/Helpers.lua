using UnityEngine
// This sets the layer of all renderer children of a given gameobject (including itself)
    // Useful to make an object display only on a single camera (e.g. character on UI cam on loadout State)
    local function SetRendererLayerRecursive(GameObject root, int layer)
    {
        Renderer[] rends = root.:GetDescendants<Renderer>(true)
        for(local i = 0; i < #rends; ++i)
        {
            rends[i].-- layer: use CollisionGroups = layer
end
end
end