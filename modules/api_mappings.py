"""
api_mappings.py — Comprehensive Unity C# → Roblox Luau API mapping table.

Contains categorised lookup tables for converting Unity API calls, types,
and patterns to their Roblox equivalents. Used by code_transpiler.py.

No other module is imported here.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Unity API → Roblox API call mappings
# ---------------------------------------------------------------------------
# Keys: Unity C# API pattern (as used in source code)
# Values: Roblox Luau equivalent

API_CALL_MAP: dict[str, str] = {
    # --- Debug / Logging ---
    "Debug.Log": "print",
    "Debug.LogWarning": "warn",
    "Debug.LogError": "warn",

    # --- Physics ---
    "Physics.Raycast": "workspace:Raycast",
    "Physics.RaycastAll": "workspace:Raycast",
    "Physics.OverlapSphere": "workspace:GetPartBoundsInRadius",
    "Physics.OverlapBox": "workspace:GetPartBoundsInBox",
    "Physics.SphereCast": "workspace:Spherecast",
    "Physics.Linecast": "workspace:Raycast",
    "Physics.gravity": "workspace.Gravity",

    # --- Object lifecycle ---
    "Instantiate": ".Clone",
    "Destroy": ".Destroy",
    "DestroyImmediate": ":Destroy()",
    "DontDestroyOnLoad": "-- DontDestroyOnLoad: parent to ReplicatedStorage to persist across places",

    # --- GameObject ---
    # Note: SetActive is handled by a regex rule in code_transpiler.py
    # that maps <var>.SetActive(<arg>) → <var>.Visible = <arg>
    "gameObject.name": ".Name",
    "gameObject.tag": ":GetAttribute('Tag')",
    "gameObject.layer": "CollisionGroup",  # set via PhysicsService:SetPartCollisionGroup()
    "CompareTag": ":GetAttribute('Tag') ==",
    "GameObject.Find": "workspace:FindFirstChild",
    "GameObject.FindWithTag": "CollectionService:GetTagged",
    "GameObject.FindGameObjectsWithTag": "CollectionService:GetTagged",

    # --- Transform ---
    "transform.position": ".Position",
    "transform.localPosition": ".CFrame.Position",
    "transform.rotation": ".CFrame",
    "transform.localRotation": ".CFrame",
    "transform.eulerAngles": ".Orientation",
    "transform.localScale": ".Size",
    "transform.parent": ".Parent",
    "transform.SetParent": ".Parent =",
    "transform.Find": ":FindFirstChild",
    "transform.GetChild": ":GetChildren()",
    "transform.childCount": ":GetChildren()",
    "transform.forward": ".CFrame.LookVector",
    "transform.right": ".CFrame.RightVector",
    "transform.up": ".CFrame.UpVector",
    "transform.Translate": "CFrame.new",
    "transform.Rotate": "CFrame.Angles",
    "transform.LookAt": "CFrame.lookAt",
    "transform.TransformPoint": ":PointToWorldSpace",
    "transform.InverseTransformPoint": ":PointToObjectSpace",

    # --- Component access ---
    "GetComponent": ":FindFirstChildOfClass",
    "GetComponentInChildren": ":FindFirstChildOfClass",
    "GetComponentInParent": ":FindFirstAncestorOfClass",
    "GetComponents": ":GetChildren",
    "GetComponentsInChildren": ":GetDescendants",
    "AddComponent": "Instance.new",  # parent result to self

    # --- Time ---
    "Time.time": "workspace:GetServerTimeNow()",
    "Time.deltaTime": "dt",  # from Heartbeat callback parameter
    "Time.fixedDeltaTime": "dt",
    "Time.timeScale": "workspace:SetAttribute('TimeScale', 1)",  # custom attribute pattern
    "Time.unscaledDeltaTime": "dt",
    "Time.realtimeSinceStartup": "os.clock()",
    "Time.frameCount": "-- frameCount: no direct Roblox equivalent",

    # --- Input ---
    "Input.GetKey": "UserInputService:IsKeyDown",
    "Input.GetKeyDown": "UserInputService.InputBegan",
    "Input.GetKeyUp": "UserInputService.InputEnded",
    "Input.GetMouseButton": "UserInputService:IsMouseButtonPressed",
    "Input.GetMouseButtonDown": "UserInputService.InputBegan",
    "Input.GetAxis": "UserInputService:GetGamepadState(Enum.UserInputType.Gamepad1)",  # approximate; remap per axis
    "Input.mousePosition": "UserInputService:GetMouseLocation()",
    "Input.GetTouch": "UserInputService.TouchStarted",

    # --- Mathf ---
    "Mathf.Abs": "math.abs",
    "Mathf.Ceil": "math.ceil",
    "Mathf.CeilToInt": "math.ceil",
    "Mathf.Clamp": "math.clamp",
    "Mathf.Clamp01": "math.clamp",  # clamp(x, 0, 1)
    "Mathf.Floor": "math.floor",
    "Mathf.FloorToInt": "math.floor",
    "Mathf.Lerp": "math.lerp",  # Luau-native since 2023; fallback: a + (b - a) * t
    "Mathf.Max": "math.max",
    "Mathf.Min": "math.min",
    "Mathf.Pow": "math.pow",
    "Mathf.Round": "math.round",
    "Mathf.Sqrt": "math.sqrt",
    "Mathf.Sin": "math.sin",
    "Mathf.Cos": "math.cos",
    "Mathf.Tan": "math.tan",
    "Mathf.Asin": "math.asin",
    "Mathf.Acos": "math.acos",
    "Mathf.Atan2": "math.atan2",
    "Mathf.Log": "math.log",
    "Mathf.Exp": "math.exp",
    "Mathf.Sign": "math.sign",
    "Mathf.PI": "math.pi",
    "Mathf.Infinity": "math.huge",
    "Mathf.Deg2Rad": "math.rad(1)",
    "Mathf.Rad2Deg": "math.deg(1)",
    "Mathf.MoveTowards": "math.clamp",  # MoveTowards(a, b, d) ≈ clamp(a + sign(b-a)*d, min(a,b), max(a,b))
    "Mathf.SmoothDamp": "TweenService:Create",  # approximate: use TweenService for smooth interpolation
    "Mathf.PingPong": "math.abs",  # PingPong(t, len) ≈ len - abs(t % (2*len) - len)
    "Mathf.PerlinNoise": "math.noise",

    # --- Vector3 ---
    "Vector3.zero": "Vector3.zero",
    "Vector3.one": "Vector3.one",
    "Vector3.up": "Vector3.yAxis",
    "Vector3.down": "-Vector3.yAxis",
    "Vector3.forward": "Vector3.zAxis",
    "Vector3.back": "-Vector3.zAxis",
    "Vector3.right": "Vector3.xAxis",
    "Vector3.left": "-Vector3.xAxis",
    "Vector3.Distance": "(a - b).Magnitude",
    "Vector3.Lerp": ":Lerp",
    "Vector3.Normalize": ".Unit",
    "Vector3.Cross": ":Cross",
    "Vector3.Dot": ":Dot",
    "Vector3.Angle": "math.acos",  # Vector3.Angle(a,b) = math.acos(a.Unit:Dot(b.Unit))
    "Vector3.MoveTowards": ":Lerp",  # approximate: a:Lerp(b, math.min(1, maxDelta / (b-a).Magnitude))
    "Vector3.ClampMagnitude": ".Unit",  # ClampMagnitude(v, max) = v.Unit * math.min(v.Magnitude, max)
    "new Vector3": "Vector3.new",

    # --- Vector2 ---
    "Vector2.zero": "Vector2.zero",
    "Vector2.one": "Vector2.one",
    "Vector2.Distance": "(a - b).Magnitude",
    "new Vector2": "Vector2.new",

    # --- Quaternion ---
    "Quaternion.identity": "CFrame.new()",
    "Quaternion.Euler": "CFrame.fromEulerAnglesXYZ",
    "Quaternion.LookRotation": "CFrame.lookAt",
    "Quaternion.Lerp": ":Lerp",
    "Quaternion.Slerp": ":Lerp",
    "Quaternion.Inverse": ":Inverse()",
    "Quaternion.AngleAxis": "CFrame.fromAxisAngle",

    # --- Color ---
    "Color.red": "Color3.new(1, 0, 0)",
    "Color.green": "Color3.new(0, 1, 0)",
    "Color.blue": "Color3.new(0, 0, 1)",
    "Color.white": "Color3.new(1, 1, 1)",
    "Color.black": "Color3.new(0, 0, 0)",
    "Color.yellow": "Color3.new(1, 1, 0)",
    "Color.cyan": "Color3.new(0, 1, 1)",
    "Color.magenta": "Color3.new(1, 0, 1)",
    "Color.gray": "Color3.new(0.5, 0.5, 0.5)",
    "new Color": "Color3.new",

    # --- Rigidbody ---
    "rigidbody.velocity": ".AssemblyLinearVelocity",
    "rigidbody.angularVelocity": ".AssemblyAngularVelocity",
    "rigidbody.mass": ":GetMass()",
    "rigidbody.AddForce": ":ApplyImpulse",
    "rigidbody.AddTorque": ":ApplyAngularImpulse",
    "rigidbody.isKinematic": ".Anchored",
    "rigidbody.useGravity": "workspace.Gravity",  # set to 0 to disable; no per-object toggle
    "rigidbody.MovePosition": ".CFrame",

    # --- Collider events ---
    "OnCollisionEnter": ".Touched",
    "OnCollisionExit": ".TouchEnded",
    "OnTriggerEnter": ".Touched",
    "OnTriggerExit": ".TouchEnded",

    # --- Coroutines ---
    "StartCoroutine": "task.spawn",
    "StopCoroutine": "task.cancel",
    "StopAllCoroutines": "task.cancel",  # must track task handles to cancel all
    "yield return null": "task.wait()",
    "yield return new WaitForSeconds": "task.wait",
    "yield return new WaitForEndOfFrame": "task.wait()",
    "yield return new WaitForFixedUpdate": "task.wait()",

    # --- Scene management ---
    "SceneManager.LoadScene": "TeleportService:Teleport",  # teleport player to another place
    "SceneManager.GetActiveScene": "game.PlaceId",  # current place identifier

    # --- Audio ---
    "AudioSource.Play": ":Play()",
    "AudioSource.Stop": ":Stop()",
    "AudioSource.Pause": ":Pause()",
    "AudioSource.PlayOneShot": ":Play()",
    "AudioSource.clip": ".SoundId",
    "AudioSource.volume": ".Volume",
    "AudioSource.pitch": ".PlaybackSpeed",
    "AudioSource.loop": ".Looped",
    "AudioSource.isPlaying": ".IsPlaying",

    # --- Animation ---
    "Animator.SetBool": ":SetAttribute",  # store animator params as attributes
    "Animator.SetFloat": ":SetAttribute",  # store animator params as attributes
    "Animator.SetTrigger": "AnimationTrack:Play()",
    "Animator.Play": "AnimationTrack:Play()",
    "Animation.Play": "AnimationTrack:Play()",

    # --- Camera ---
    "Camera.main": "workspace.CurrentCamera",
    "Camera.fieldOfView": ".FieldOfView",
    "Camera.ScreenToWorldPoint": ":ScreenPointToRay",
    "Camera.WorldToScreenPoint": ":WorldToScreenPoint",

    # --- UI ---
    "Canvas": "ScreenGui",
    "Text.text": ".Text",
    "Image.sprite": ".Image",
    "Button.onClick": ".Activated",
    "RectTransform": "UDim2",  # Roblox uses UDim2 for UI positioning

    # --- PlayerPrefs → DataStoreService ---
    "PlayerPrefs.SetInt": "DataStoreService:GetDataStore('PlayerPrefs'):SetAsync",
    "PlayerPrefs.GetInt": "DataStoreService:GetDataStore('PlayerPrefs'):GetAsync",
    "PlayerPrefs.SetFloat": "DataStoreService:GetDataStore('PlayerPrefs'):SetAsync",
    "PlayerPrefs.GetFloat": "DataStoreService:GetDataStore('PlayerPrefs'):GetAsync",
    "PlayerPrefs.SetString": "DataStoreService:GetDataStore('PlayerPrefs'):SetAsync",
    "PlayerPrefs.GetString": "DataStoreService:GetDataStore('PlayerPrefs'):GetAsync",
    "PlayerPrefs.Save": "-- DataStoreService auto-saves; no explicit save needed",
    "PlayerPrefs.DeleteKey": "DataStoreService:GetDataStore('PlayerPrefs'):RemoveAsync",

    # --- Networking (common patterns) ---
    "[Command]": "RemoteEvent:FireServer",  # client → server RPC
    "[ClientRpc]": "RemoteEvent:FireAllClients",  # server → client RPC
    "[SyncVar]": ":SetAttribute",  # replicated via Attributes

    # --- Random ---
    "Random.Range": "math.random",
    "Random.value": "math.random()",
    "Random.insideUnitSphere": "Random.new():NextUnitVector()",
    "Random.insideUnitCircle": "Vector2.new(math.random() * 2 - 1, math.random() * 2 - 1).Unit",
    "UnityEngine.Random": "Random.new()",

    # --- String ---
    "string.Format": "string.format",
    "string.IsNullOrEmpty": "(s == nil or s == '')",  # inline nil/empty check

    # --- Collections ---
    # NOTE: .Length, .Count, .Add(), .Remove(), .Contains() are handled by
    # explicit regex patterns in _rule_based_transpile() which properly
    # restructure the syntax (e.g., "items.Length" → "#items").
    "List<": "-- List<T>: use Luau table {}",
    "Dictionary<": "-- Dictionary<K,V>: use Luau table {}",
    ".Clear()": "table.clear",
    "foreach": "for _, v in",
}


# ---------------------------------------------------------------------------
# C# type → Luau type annotation mappings
# ---------------------------------------------------------------------------

TYPE_MAP: dict[str, str] = {
    "int": "number",
    "float": "number",
    "double": "number",
    "long": "number",
    "short": "number",
    "byte": "number",
    "uint": "number",
    "bool": "boolean",
    "string": "string",
    "void": "()",
    "object": "any",
    "var": "",  # type inference
    "Vector3": "Vector3",
    "Vector2": "Vector2",
    "Quaternion": "CFrame",
    "Color": "Color3",
    "Color32": "Color3",
    "Transform": "BasePart",
    "GameObject": "Instance",
    "Rigidbody": "BasePart",
    "Collider": "BasePart",
    "AudioSource": "Sound",
    "AudioClip": "Sound",
    "Camera": "Camera",
    "Animator": "AnimationController",
    "MonoBehaviour": "-- (script module)",
    "ScriptableObject": "-- (ModuleScript)",
}


# ---------------------------------------------------------------------------
# Unity lifecycle hook → Roblox equivalent
# ---------------------------------------------------------------------------

LIFECYCLE_MAP: dict[str, str] = {
    "Awake": "-- Awake: runs at script start (top-level code)",
    "Start": "-- Start: runs at script start (top-level code after Awake)",
    "Update": "RunService.Heartbeat:Connect(function(dt)",
    "FixedUpdate": "RunService.Stepped:Connect(function(dt)",
    "LateUpdate": "RunService.RenderStepped:Connect(function(dt)",
    "OnEnable": "script.Parent.AncestryChanged:Connect(function()",
    "OnDisable": "script.Parent.AncestryChanged:Connect(function()",
    "OnDestroy": "script.Destroying:Connect(function()",
    "OnCollisionEnter": "part.Touched:Connect(function(otherPart)",
    "OnCollisionExit": "part.TouchEnded:Connect(function(otherPart)",
    "OnTriggerEnter": "part.Touched:Connect(function(otherPart)",
    "OnTriggerExit": "part.TouchEnded:Connect(function(otherPart)",
    "OnMouseDown": "ClickDetector.MouseClick:Connect(function(player)",
    "OnMouseEnter": "ClickDetector.MouseHoverEnter:Connect(function(player)",
    "OnMouseExit": "ClickDetector.MouseHoverLeave:Connect(function(player)",
    "OnGUI": "-- OnGUI: use ScreenGui with UI elements",
    "OnApplicationQuit": "game:BindToClose(function()",
    "OnApplicationPause": "-- OnApplicationPause: no direct equivalent",
}


# ---------------------------------------------------------------------------
# Roblox service imports that may be needed
# ---------------------------------------------------------------------------

SERVICE_IMPORTS: dict[str, str] = {
    "RunService": 'local RunService = game:GetService("RunService")',
    "UserInputService": 'local UserInputService = game:GetService("UserInputService")',
    "TweenService": 'local TweenService = game:GetService("TweenService")',
    "CollectionService": 'local CollectionService = game:GetService("CollectionService")',
    "Players": 'local Players = game:GetService("Players")',
    "ReplicatedStorage": 'local ReplicatedStorage = game:GetService("ReplicatedStorage")',
    "ServerStorage": 'local ServerStorage = game:GetService("ServerStorage")',
    "DataStoreService": 'local DataStoreService = game:GetService("DataStoreService")',
    "TeleportService": 'local TeleportService = game:GetService("TeleportService")',
    "SoundService": 'local SoundService = game:GetService("SoundService")',
    "Workspace": "local Workspace = workspace",
}
