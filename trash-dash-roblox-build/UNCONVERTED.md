# Unconverted Features Report

> Generated: 2026-03-04 05:00 UTC
> Unity Project: trash-dash

## Conversion Statistics

| Metric | Value |
|--------|-------|
| Total materials processed | 36 |
| Fully converted | 0 |
| Partially converted | 35 |
| Skipped (unconvertible) | 1 |

## Unconverted Feature Summary

| Feature | Materials Affected | Severity |
|---------|--------------------|----------|
| World curve effect | 34 | LOW |
| Vertex color multiplication | 31 | HIGH |
| Blinking animation | 4 | LOW |
| Vertex rotation animation | 2 | LOW |
| Vertex-color-only shader | 1 | HIGH |

## Materials Requiring Manual Work

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
