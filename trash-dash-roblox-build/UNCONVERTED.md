# Unconverted Features Report

> Generated: 2026-03-03 03:37 UTC
> Unity Project: trash-dash

## Conversion Statistics

| Metric | Value |
|--------|-------|
| Total materials processed | 73 |
| Fully converted | 18 |
| Partially converted | 53 |
| Skipped (unconvertible) | 2 |

## Unconverted Feature Summary

| Feature | Materials Affected | Severity |
|---------|--------------------|----------|
| World curve effect | 49 | LOW |
| Vertex color multiplication | 44 | HIGH |
| Blinking animation | 4 | LOW |
| Soft particles | 3 | LOW |
| Vertex-color-only shader | 2 | HIGH |
| Premultiplied alpha blending | 2 | LOW |
| Vertex rotation animation | 2 | LOW |
| Additive blending | 1 | LOW |

## Materials Requiring Manual Work

### BackgroundCircle (`/home/user/trash-dash/Assets/Materials/BackgroundCircle.mat`)

**Shader**: `Unlit/VertexColor`  
**Pipeline**: CUSTOM  
**Status**: Not converted

**Unconverted**:
- [ ] **Vertex-color-only shader** (HIGH) — Assign flat color manually in Roblox Studio

---

### Bin (`/home/user/trash-dash/Assets/Materials/Bin.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`Bin_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### BinBag (`/home/user/trash-dash/Assets/Materials/BinBag.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`BinBag_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### BinNight (`/home/user/trash-dash/Assets/Materials/BinNight.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`BinNight_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### BlobShadow (`/home/user/trash-dash/Assets/Materials/BlobShadow.mat`)

**Shader**: `Unlit/CurvedUnlitAlpha`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`BlobShadow_color.png`)
- [x] Alpha mode → Transparency

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### BrickWall (`/home/user/trash-dash/Assets/Materials/BrickWall.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`BrickWall_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### Car01 (`/home/user/trash-dash/Assets/Materials/Car01.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`Car01_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### Car02 (`/home/user/trash-dash/Assets/Materials/Car02.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`Car02_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### CatOrange (`/home/user/trash-dash/Assets/Materials/CatOrange.mat`)

**Shader**: `Unlit/UnlitBlinking`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`CatOrange_color.png`)

**Unconverted**:
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect
- [ ] **Blinking animation** (LOW) — Companion Luau tween script generated

**Companion scripts**: 1 Luau script(s) generated

---

### CloudMaterial (`/home/user/trash-dash/Assets/Materials/CloudMaterial.mat`)

**Shader**: `Unlit/CurvedUnlitCloud`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Alpha mode → Transparency

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### Clover (`/home/user/trash-dash/Assets/Materials/Clover.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`Clover_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### Construction (`/home/user/trash-dash/Assets/Materials/Construction.mat`)

**Shader**: `Particles/Alpha Blended Premultiply`  
**Pipeline**: PARTICLE  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`Construction_color.png`)
- [x] Alpha mode → Transparency

**Unconverted**:
- [ ] **Premultiplied alpha blending** (LOW) — Use standard alpha blending (close approximation)

---

### ConstructionGear (`/home/user/trash-dash/Assets/Materials/ConstructionGear.mat`)

**Shader**: `Unlit/UnlitBlinking`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`ConstructionGear_color.png`)

**Unconverted**:
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect
- [ ] **Blinking animation** (LOW) — Companion Luau tween script generated

**Companion scripts**: 1 Luau script(s) generated

---

### CorrugatedMetal (`/home/user/trash-dash/Assets/Materials/CorrugatedMetal.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`CorrugatedMetal_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### Dog (`/home/user/trash-dash/Assets/Materials/Dog.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`Dog_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### DogNight (`/home/user/trash-dash/Assets/Materials/DogNight.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`DogNight_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### Dumpster (`/home/user/trash-dash/Assets/Materials/Dumpster.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`Dumpster_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### ExtraLifeParticle (`/home/user/trash-dash/Assets/Materials/ExtraLifeParticle.mat`)

**Shader**: `Particles/Alpha Blended`  
**Pipeline**: PARTICLE  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`ExtraLifeParticle_color.png`)
- [x] Color tint → SurfaceAppearance.Color (0.5, 0.5, 0.5)
- [x] Alpha mode → Transparency

**Unconverted**:
- [ ] **Soft particles** (LOW) — No Roblox equivalent — accept hard particle edges

---

### FishBoneParticle (`/home/user/trash-dash/Assets/Materials/FishBoneParticle.mat`)

**Shader**: `Sprites/Default`  
**Pipeline**: PARTICLE  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`FishBoneParticle_color.png`)
- [x] Alpha mode → Transparency

**Unconverted**:
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### Fishbone (`/home/user/trash-dash/Assets/Materials/Fishbone.mat`)

**Shader**: `Unlit/CurvedRotation`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`Fishbone_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect
- [ ] **Vertex rotation animation** (LOW) — Companion Luau rotation script generated

**Companion scripts**: 1 Luau script(s) generated

---

### Graffiti (`/home/user/trash-dash/Assets/Materials/Graffiti.mat`)

**Shader**: `Unlit/CurvedUnlitAlpha`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Alpha mode → Transparency

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### Grass (`/home/user/trash-dash/Assets/Materials/Grass.mat`)

**Shader**: `Particles/Alpha Blended Premultiply`  
**Pipeline**: PARTICLE  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`Grass_color.png`)
- [x] Color tint → SurfaceAppearance.Color (0.39705884, 0.39705884, 0.39705884)
- [x] Alpha mode → Transparency

**Unconverted**:
- [ ] **Premultiplied alpha blending** (LOW) — Use standard alpha blending (close approximation)
- [ ] **Soft particles** (LOW) — No Roblox equivalent — accept hard particle edges

---

### Heart (`/home/user/trash-dash/Assets/Materials/Heart.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`Heart_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### LightCone (`/home/user/trash-dash/Assets/Materials/LightCone.mat`)

**Shader**: `Unlit/CurvedUnlitAlpha`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`LightCone_color.png`)
- [x] Alpha mode → Transparency

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### LightGlow (`/home/user/trash-dash/Assets/Materials/LightGlow.mat`)

**Shader**: `Unlit/CurvedUnlitAlpha`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`LightGlow_color.png`)
- [x] Alpha mode → Transparency

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### LightPool (`/home/user/trash-dash/Assets/Materials/LightPool.mat`)

**Shader**: `Unlit/CurvedUnlitAlpha`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`LightPool_color.png`)
- [x] Alpha mode → Transparency

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### Magnet (`/home/user/trash-dash/Assets/Materials/Magnet.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`Magnet_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### MagnetSparks (`/home/user/trash-dash/Assets/Materials/MagnetSparks.mat`)

**Shader**: `Unlit/CurvedUnlitAlpha`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`MagnetSparks_color.png`)
- [x] Alpha mode → Transparency

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### ManHole (`/home/user/trash-dash/Assets/Materials/ManHole.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`ManHole_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### Obstacle (`/home/user/trash-dash/Assets/Materials/Obstacle.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### PartyHatAndBowtie (`/home/user/trash-dash/Assets/Materials/PartyHatAndBowtie.mat`)

**Shader**: `Unlit/UnlitBlinking`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`PartyHatAndBowtie_color.png`)

**Unconverted**:
- [ ] **Blinking animation** (LOW) — Companion Luau tween script generated

**Companion scripts**: 1 Luau script(s) generated

---

### PickupParticle (`/home/user/trash-dash/Assets/Materials/PickupParticle.mat`)

**Shader**: `Unlit/CurvedUnlitAlpha`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`PickupParticle_color.png`)
- [x] Alpha mode → Transparency

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### Pipe (`/home/user/trash-dash/Assets/Materials/Pipe.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`Pipe_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### Plaster (`/home/user/trash-dash/Assets/Materials/Plaster.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`Plaster_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### PuffParticle (`/home/user/trash-dash/Assets/Materials/PuffParticle.mat`)

**Shader**: `Unlit/CurvedUnlitAlpha`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`PuffParticle_color.png`)
- [x] Alpha mode → Transparency

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### Racoon (`/home/user/trash-dash/Assets/Materials/Racoon.mat`)

**Shader**: `Unlit/UnlitBlinking`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`Racoon_color.png`)

**Unconverted**:
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect
- [ ] **Blinking animation** (LOW) — Companion Luau tween script generated

**Companion scripts**: 1 Luau script(s) generated

---

### Rat (`/home/user/trash-dash/Assets/Materials/Rat.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`Rat_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### RatNight (`/home/user/trash-dash/Assets/Materials/RatNight.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`RatNight_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### Rubbish (`/home/user/trash-dash/Assets/Materials/Rubbish.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`Rubbish_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### Sardines (`/home/user/trash-dash/Assets/Materials/Sardines.mat`)

**Shader**: `Unlit/CurvedRotation`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`Sardines_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect
- [ ] **Vertex rotation animation** (LOW) — Companion Luau rotation script generated

**Companion scripts**: 1 Luau script(s) generated

---

### Skip (`/home/user/trash-dash/Assets/Materials/Skip.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`Skip_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### Sky (`/home/user/trash-dash/Assets/Materials/Sky.mat`)

**Shader**: `Unlit/VertexColor`  
**Pipeline**: CUSTOM  
**Status**: Not converted

**Unconverted**:
- [ ] **Vertex-color-only shader** (HIGH) — Assign flat color manually in Roblox Studio

---

### SmokePuff (`/home/user/trash-dash/Assets/Materials/SmokePuff.mat`)

**Shader**: `Particles/Additive`  
**Pipeline**: PARTICLE  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`SmokePuff_color.png`)
- [x] Color tint → SurfaceAppearance.Color (0.5, 0.5, 0.5)
- [x] Alpha mode → Transparency

**Unconverted**:
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect
- [ ] **Additive blending** (LOW) — Use ParticleEmitter.LightEmission = 1
- [ ] **Soft particles** (LOW) — No Roblox equivalent — accept hard particle edges

---

### Sparkle (`/home/user/trash-dash/Assets/Materials/Sparkle.mat`)

**Shader**: `Unlit/CurvedUnlitAlpha`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`Sparkle_color.png`)
- [x] Alpha mode → Transparency

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### StarInner (`/home/user/trash-dash/Assets/Materials/StarInner.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`StarInner_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### StarOuter (`/home/user/trash-dash/Assets/Materials/StarOuter.mat`)

**Shader**: `Unlit/CurvedUnlitAlpha`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`StarOuter_color.png`)
- [x] Alpha mode → Transparency

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### StarParticle (`/home/user/trash-dash/Assets/Materials/StarParticle.mat`)

**Shader**: `Unlit/CurvedUnlitAlpha`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`StarParticle_color.png`)
- [x] Alpha mode → Transparency

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### Stone (`/home/user/trash-dash/Assets/Materials/Stone.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`Stone_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### StoneWall (`/home/user/trash-dash/Assets/Materials/StoneWall.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`StoneWall_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### TreeBranch (`/home/user/trash-dash/Assets/Materials/TreeBranch.mat`)

**Shader**: `Unlit/CurvedUnlitAlpha`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`TreeBranch_color.png`)
- [x] Alpha mode → Transparency

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### VCOL (`/home/user/trash-dash/Assets/Materials/VCOL.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### WarningLight (`/home/user/trash-dash/Assets/Materials/WarningLight.mat`)

**Shader**: `Unlit/CurvedUnlitAlpha`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`WarningLight_color.png`)
- [x] Alpha mode → Transparency

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### WashingLineClothes (`/home/user/trash-dash/Assets/Materials/WashingLineClothes.mat`)

**Shader**: `Unlit/CurvedUnlitAlpha`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`WashingLineClothes_color.png`)
- [x] Alpha mode → Transparency

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### WheelyBin (`/home/user/trash-dash/Assets/Materials/WheelyBin.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`WheelyBin_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---

### WoodSlats (`/home/user/trash-dash/Assets/Materials/WoodSlats.mat`)

**Shader**: `Unlit/CurvedUnlit`  
**Pipeline**: CUSTOM  
**Status**: Partially converted

**Converted**: 
- [x] Albedo texture → ColorMap (`WoodSlats_color.png`)

**Unconverted**:
- [ ] **Vertex color multiplication** (HIGH) — Bake vertex colors into albedo texture (requires mesh data)
- [ ] **World curve effect** (LOW) — Ignore — cosmetic world-curve effect

---
