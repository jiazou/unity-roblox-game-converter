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
    "DontDestroyOnLoad": "-- DontDestroyOnLoad: use ReplicatedStorage parenting",

    # --- GameObject ---
    # Note: SetActive is handled by a regex rule in code_transpiler.py
    # that maps <var>.SetActive(<arg>) → <var>.Visible = <arg>
    "gameObject.name": ".Name",
    "gameObject.tag": ":GetAttribute('Tag')",
    "gameObject.layer": "-- layer: use CollisionGroups",
    "CompareTag": ":GetAttribute('Tag') ==",
    "GameObject.Find": "workspace:FindFirstChild",
    "GameObject.FindWithTag": "-- FindWithTag: use CollectionService:GetTagged",
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
    "AddComponent": "-- AddComponent: create Instance.new() and parent it",

    # --- Time ---
    "Time.time": "workspace:GetServerTimeNow()",
    "Time.deltaTime": "dt",  # from Heartbeat callback parameter
    "Time.fixedDeltaTime": "dt",
    "Time.timeScale": "-- timeScale: no direct Roblox equivalent",
    "Time.unscaledDeltaTime": "dt",
    "Time.realtimeSinceStartup": "os.clock()",
    "Time.frameCount": "-- frameCount: no direct equivalent",

    # --- Input ---
    "Input.GetKey": "UserInputService:IsKeyDown",
    "Input.GetKeyDown": "UserInputService.InputBegan",
    "Input.GetKeyUp": "UserInputService.InputEnded",
    "Input.GetMouseButton": "UserInputService:IsMouseButtonPressed",
    "Input.GetMouseButtonDown": "UserInputService.InputBegan",
    "Input.GetAxis": "-- GetAxis: use UserInputService or ContextActionService",
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
    "Mathf.Lerp": "-- Mathf.Lerp: use a + (b - a) * t",
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
    "Mathf.MoveTowards": "-- MoveTowards: manual impl a + sign(b-a) * min(abs(b-a), maxDelta)",
    "Mathf.SmoothDamp": "-- SmoothDamp: manual implementation needed",
    "Mathf.PingPong": "-- PingPong: manual implementation needed",
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
    "Vector3.Angle": "-- Vector3.Angle: math.acos(a.Unit:Dot(b.Unit))",
    "Vector3.MoveTowards": "-- MoveTowards: manual implementation",
    "Vector3.ClampMagnitude": "-- ClampMagnitude: v.Unit * math.min(v.Magnitude, max)",
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
    "rigidbody.useGravity": "-- useGravity: no per-object gravity toggle",
    "rigidbody.MovePosition": ".CFrame",

    # --- Collider events ---
    "OnCollisionEnter": ".Touched",
    "OnCollisionExit": ".TouchEnded",
    "OnTriggerEnter": ".Touched",
    "OnTriggerExit": ".TouchEnded",

    # --- Coroutines ---
    "StartCoroutine": "task.spawn",
    "StopCoroutine": "task.cancel",
    "StopAllCoroutines": "-- StopAllCoroutines: cancel tracked tasks",
    "yield return null": "task.wait()",
    "yield return new WaitForSeconds": "task.wait",
    "yield return new WaitForEndOfFrame": "task.wait()",
    "yield return new WaitForFixedUpdate": "task.wait()",

    # --- Scene management ---
    "SceneManager.LoadScene": "-- LoadScene: use TeleportService or place switching",
    "SceneManager.GetActiveScene": "-- GetActiveScene: no direct equivalent",

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
    "Animator.SetBool": "-- Animator: use Roblox AnimationController",
    "Animator.SetFloat": "-- Animator: use Roblox AnimationController",
    "Animator.SetTrigger": "-- Animator: use AnimationTrack:Play()",
    "Animator.Play": "-- Animator: use AnimationTrack:Play()",
    "Animation.Play": "-- Animation: use AnimationTrack:Play()",

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
    "RectTransform": "-- RectTransform: use UDim2 for positioning",

    # --- PlayerPrefs ---
    "PlayerPrefs.SetInt": "-- PlayerPrefs: use DataStoreService",
    "PlayerPrefs.GetInt": "-- PlayerPrefs: use DataStoreService",
    "PlayerPrefs.SetFloat": "-- PlayerPrefs: use DataStoreService",
    "PlayerPrefs.GetFloat": "-- PlayerPrefs: use DataStoreService",
    "PlayerPrefs.SetString": "-- PlayerPrefs: use DataStoreService",
    "PlayerPrefs.GetString": "-- PlayerPrefs: use DataStoreService",
    "PlayerPrefs.Save": "-- PlayerPrefs: DataStoreService auto-saves",

    # --- Networking (common patterns) ---
    "[Command]": "-- [Command]: use RemoteEvent (client → server)",
    "[ClientRpc]": "-- [ClientRpc]: use RemoteEvent (server → client)",
    "[SyncVar]": "-- [SyncVar]: use Attributes or ValueObjects for replication",

    # --- Random ---
    "Random.Range": "math.random",
    "Random.value": "math.random()",
    "Random.insideUnitSphere": "-- Random.insideUnitSphere: Random.new():NextUnitVector()",
    "Random.insideUnitCircle": "-- Random.insideUnitCircle: manual impl",
    "UnityEngine.Random": "Random.new()",

    # --- String ---
    "string.Format": "string.format",
    "string.IsNullOrEmpty": "-- IsNullOrEmpty: check s == nil or s == ''",

    # --- Collections ---
    # NOTE: .Length, .Count, .Add(), .Remove(), .Contains() are handled by
    # explicit regex patterns in _rule_based_transpile() which properly
    # restructure the syntax (e.g., "items.Length" → "#items").
    "List<": "-- List<T>: use Luau table {}",
    "Dictionary<": "-- Dictionary<K,V>: use Luau table {}",
    ".Clear()": "table.clear",
    "foreach": "for _, v in",

    # --- TextMeshPro (TMP) — widely used in modern Unity games ---
    "TextMeshProUGUI": "TextLabel",
    "TextMeshPro": "TextLabel",
    "TMP_Text": "TextLabel",
    "TMP_InputField": "TextBox",
    ".SetText(": ".Text =",

    # --- DOTween (most popular tweening library) ---
    "DOTween.To": "TweenService:Create",
    ".DOMove(": "-- DOMove: use TweenService:Create(part, info, {Position = target})",
    ".DORotate(": "-- DORotate: use TweenService:Create(part, info, {CFrame = target})",
    ".DOScale(": "-- DOScale: use TweenService:Create(part, info, {Size = target})",
    ".DOFade(": "-- DOFade: use TweenService:Create(part, info, {Transparency = target})",
    ".DOColor(": "-- DOColor: use TweenService:Create(part, info, {Color = target})",
    ".DOLocalMove(": "-- DOLocalMove: use TweenService:Create with relative CFrame",
    ".DOKill(": "-- DOKill: cancel tween",
    ".SetEase(": "-- SetEase: use TweenInfo EasingStyle",
    ".SetDelay(": "-- SetDelay: use TweenInfo DelayTime",
    ".SetLoops(": "-- SetLoops: use TweenInfo RepeatCount",
    ".OnComplete(": "-- OnComplete: use Tween.Completed:Connect()",

    # --- NavMesh / AI Navigation ---
    "NavMeshAgent": "-- NavMeshAgent: use Roblox PathfindingService",
    "NavMesh.CalculatePath": "PathfindingService:CreatePath()",
    ".SetDestination(": "-- SetDestination: use Path:ComputeAsync(target)",
    ".remainingDistance": "-- remainingDistance: compute from waypoints",
    ".isStopped": "-- isStopped: track manually",
    "navMeshAgent.speed": "-- NavMeshAgent.speed: set Humanoid.WalkSpeed",
    "agent.speed": "-- NavMeshAgent.speed: set Humanoid.WalkSpeed",
    "NavMeshObstacle": "-- NavMeshObstacle: no direct equivalent, use collision",

    # --- New Input System (Unity 2019+) ---
    "InputAction": "-- InputAction: use ContextActionService or UserInputService",
    ".ReadValue<Vector2>()": "-- ReadValue: use UserInputService input events",
    ".performed": "-- performed: use InputBegan/InputChanged",
    ".canceled": "-- canceled: use InputEnded",
    "PlayerInput": "-- PlayerInput: use UserInputService",

    # --- async/await patterns (common in modern Unity) ---
    "async Task": "-- async Task: use task.spawn(function()",
    "async void": "-- async void: use task.spawn(function()",
    "await Task.Delay": "task.wait",
    "await Task.Yield()": "task.wait()",
    "UniTask": "-- UniTask: use task library",
    "await UniTask.Delay": "task.wait",
    "await UniTask.Yield()": "task.wait()",

    # --- LINQ (very common in C# game code) ---
    ".Where(": "-- Where: use manual loop filter",
    ".Select(": "-- Select: use manual loop map",
    ".FirstOrDefault(": "-- FirstOrDefault: use manual find",
    ".First(": "-- First: use manual find",
    ".Any(": "-- Any: use manual loop check",
    ".All(": "-- All: use manual loop check",
    ".OrderBy(": "-- OrderBy: use table.sort",
    ".OrderByDescending(": "-- OrderByDescending: use table.sort with reverse",
    ".ToList()": "-- ToList: already a table",
    ".ToArray()": "-- ToArray: already a table",
    ".Sum(": "-- Sum: use manual loop accumulator",
    ".Max(": "-- Max: use math.max in loop",
    ".Min(": "-- Min: use math.min in loop",
    ".Count(": "-- Count: use # operator or manual loop",
    ".Distinct()": "-- Distinct: use dictionary-based dedup",
    ".GroupBy(": "-- GroupBy: use manual dictionary grouping",

    # --- Cinemachine (very common camera system) ---
    "CinemachineVirtualCamera": "-- CinemachineVirtualCamera: configure workspace.CurrentCamera",
    "CinemachineBrain": "-- CinemachineBrain: use workspace.CurrentCamera",
    ".m_Lens.FieldOfView": ".FieldOfView",

    # --- Terrain ---
    "Terrain.activeTerrain": "-- Terrain: use Roblox Terrain object",
    "TerrainData": "-- TerrainData: use workspace.Terrain",
    ".GetHeight(": "-- GetHeight: no direct equivalent",
    "SplatPrototype": "-- SplatPrototype: use Terrain:FillBall/FillBlock with materials",

    # --- 2D Physics ---
    "Rigidbody2D": "-- Rigidbody2D: no 2D physics in Roblox",
    "Physics2D.Raycast": "workspace:Raycast",
    "Collider2D": "BasePart",

    # --- Miscellaneous common APIs ---
    "Application.targetFrameRate": "-- targetFrameRate: no equivalent",
    "Application.persistentDataPath": "-- persistentDataPath: use DataStoreService",
    "Application.isPlaying": "-- isPlaying: always true at runtime",
    "Application.platform": "-- platform: use UserInputService:GetPlatform()",
    "Application.Quit": "-- Quit: no equivalent, use TeleportService",
    "Resources.Load": "-- Resources.Load: use ReplicatedStorage:FindFirstChild",
    "Addressables.LoadAssetAsync": "-- Addressables: use ReplicatedStorage:WaitForChild",
    "Object.FindObjectOfType": "-- FindObjectOfType: use workspace:FindFirstChildOfClass",
    "Object.FindObjectsOfType": "-- FindObjectsOfType: use workspace:GetDescendants()",
    "LayerMask": "-- LayerMask: use CollisionGroups",
    "Physics.IgnoreCollision": "-- IgnoreCollision: use CollisionGroups",
    "WaitUntil": "-- WaitUntil: use while loop with task.wait()",
    "WaitWhile": "-- WaitWhile: use while loop with task.wait()",
    "Invoke(": "task.delay",
    "InvokeRepeating(": "-- InvokeRepeating: use task.spawn with while loop and task.wait",
    "CancelInvoke": "-- CancelInvoke: cancel spawned task",
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
    # Additional type mappings for common game patterns
    "Bounds": "-- Bounds (use Region3)",
    "Rect": "-- Rect (use Rect or UDim2)",
    "Ray": "Ray",
    "RaycastHit": "RaycastResult",
    "LayerMask": "number",
    "Texture2D": "string",  # asset ID
    "Sprite": "string",     # asset ID
    "Material": "string",   # asset ID
    "Mesh": "string",       # asset ID
    "NavMeshAgent": "-- (PathfindingService)",
    "CharacterController": "Humanoid",
    "Terrain": "Terrain",
    "Canvas": "ScreenGui",
    "RectTransform": "Frame",
    "Image": "ImageLabel",
    "Button": "TextButton",
    "Text": "TextLabel",
    "TMP_Text": "TextLabel",
    "TextMeshProUGUI": "TextLabel",
    "Slider": "-- Slider (custom UI)",
    "Toggle": "-- Toggle (custom UI)",
    "Dropdown": "-- Dropdown (custom UI)",
    "InputField": "TextBox",
    "ScrollRect": "ScrollingFrame",
    "IEnumerable": "-- table",
    "IList": "-- table",
    "Action": "-- function",
    "Func": "-- function",
    "UnityAction": "-- function",
    "UnityEvent": "BindableEvent",
    "Coroutine": "thread",
    "WaitForSeconds": "number",
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
    "PathfindingService": 'local PathfindingService = game:GetService("PathfindingService")',
    "ContextActionService": 'local ContextActionService = game:GetService("ContextActionService")',
    "GuiService": 'local GuiService = game:GetService("GuiService")',
    "MarketplaceService": 'local MarketplaceService = game:GetService("MarketplaceService")',
    "PhysicsService": 'local PhysicsService = game:GetService("PhysicsService")',
    "HttpService": 'local HttpService = game:GetService("HttpService")',
    "TextService": 'local TextService = game:GetService("TextService")',
}
