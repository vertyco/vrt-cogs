# Block Blaster web assets

Every file under `web/` that is not page code. `art-src/` paths are under `assets/pixel-flow/art-src/` (gitignored, holds the scripts that make these files). Original means taken from the original game's Android build in `assets/pixel-flow/`. New means made for this game.

## Model conventions (the page relies on these)

- GLB, Y up, meters. Every shooter is drawn as a cat; files and code keep the name pig. The cat faces +Z. Feet rest on y = 0. One cat is about 0.86 wide, 0.8 deep (0.95 with its tail) and 1.15 tall to the ear tips.
- A mesh node named `Tint_*` is the part the page tints with the instance color. Its material is named `Tint` and is white (1,1,1), so the instance color is the final color. Every other mesh keeps its own fixed color.
- `pig.glb` has a `FacePlate` mesh (eyes only; the nose, cheeks, whiskers and pink inner ears are geometry with their own material colors, which the page bakes into vertex colors). Its material uses the embedded face sheet (`models/pig_faces.png`, 1280x128, five frames of 256x128: open, blink, happy, empty, question). The plate's UVs cover frame 0 (u 0 to 0.2); the page shows frame N by setting the texture offset to N * 0.2.
- `AmmoAnchor` (an empty on `pig.glb`, `pig_surprise.glb`, `mascot.glb`, `pig_super_shooter.glb`, `unicorn.glb`) is where the ammo number sits: the middle of the cat's top face.
- The `overlay_*` models are placed at the same origin and scale as a cat; they carry fixed colors (the frozen and astro glass are alpha-blended).
- Snake and dragon pieces lie along Z with the head's face toward +Z, centered, about 0.6 long and 0.5 to 0.6 wide. Place pieces end to end about 0.55 apart for the snake and 0.6 for the dragon (they overlap a little on purpose).
- The original's face-less meshes (`models/features/*.glb`) keep the original's units and orientation: one GLB per prefab, parts as separate nodes with the prefab's local transforms, no materials (the page assigns colors). The original's `Pixel 1x1` cube mesh is 0.5 wide and 0.04 to 1.5 tall (the game scales its height per cell).
- No skeletal animation: hops, squash, recoil, spin and vanish are transforms applied per instance, as spec section 9.1 says. The cat's poses are its five face frames.

## Music

| File | Source | Used for |
|---|---|---|
| `music/menu.ogg` | New: Lyria 3 Pro through OpenRouter, `art-src/music/lyria.py` with `art-src/music/prompt_menu.txt` (mp3 original `art-src/music/ai_menu.mp3`), converted with ffmpeg | Menu and level path loop |
| `music/level.ogg` | New: Lyria 3 Pro through OpenRouter, `art-src/music/lyria.py` with `art-src/music/prompt_level.txt` (mp3 original `art-src/music/ai_level.mp3`), converted with ffmpeg | Normal level loop |
| `music/hard.ogg` | New: Lyria 3 Pro through OpenRouter, `art-src/music/lyria.py` with `art-src/music/prompt_hard.txt` (mp3 original `art-src/music/ai_hard.mp3`), converted with ffmpeg | Very Hard level loop |

## Pictures made for the game

| File | Source | Used for |
|---|---|---|
| `icon.png` | New: Gemini 3.1 Flash Image through OpenRouter from the cat model previews (drafts in `art-src/previews/cat-art/`, raw `art-src/previews/icon-raw.png`), cropped square, 256x256 | Hub menu icon |
| `thumb.png` | New: Gemini 3.1 Flash Image (raw `art-src/previews/thumb-raw.png`), cropped 16:9, 640x360, the only text is the title | Hub menu card cover |
| `models/pig_faces.png` | New: `art-src/faces.py` | Cat face sheet, also embedded in `pig.glb` |
| `art/ui/TopLabel_Blue.png`, `art/ui/TopLabel_Red.png` | New: `assets/pixel-flow/tools/make_top_labels.py` mirrors the right cap of the original's `Frame_Label_Rounded_Blue/Red.png` (flat on the left) onto the left | Level pill in the top bar, a 9-slice (`border-image`, 50 px caps) |
| `art/ui/SurprisePixelQuestionMark.png` | Original `art/ui/SurprisePixelQuestionMark.png` (115x121, white on clear) | The "?" on a hidden Surprise Pixel's pale cube, tinted dark by `web/looks/surprise_pixel.js` |

## New Feature popup pictures

| File | Source | Used for |
|---|---|---|
| `art/features/FeatureImage_Accordion.png` | New: rendered from the new models (and the original's pipe or UFO mesh) by `art-src/render_feature_images.py`, outline added by `art-src/outline_features.py`, 512x512 | New Feature popup for Accordion |
| `art/features/FeatureImage_AstroPig.png` | New: rendered from the new models (and the original's pipe or UFO mesh) by `art-src/render_feature_images.py`, outline added by `art-src/outline_features.py`, 512x512 | New Feature popup for AstroPig |
| `art/features/FeatureImage_Biscuit.png` | Original `art/ui/FeatureImage_Biscuit.png`, resized to 512 max | New Feature popup for Biscuit (shows no creature) |
| `art/features/FeatureImage_BullTotem.png` | New: rendered from the new models (and the original's pipe or UFO mesh) by `art-src/render_feature_images.py`, outline added by `art-src/outline_features.py`, 512x512 | New Feature popup for BullTotem |
| `art/features/FeatureImage_ColorDoor.png` | Original `art/ui/FeatureImage_ColorDoor.png`, resized to 512 max | New Feature popup for ColorDoor (shows no creature) |
| `art/features/FeatureImage_ColoredShooterCage.png` | New: rendered from the new models (and the original's pipe or UFO mesh) by `art-src/render_feature_images.py`, outline added by `art-src/outline_features.py`, 512x512 | New Feature popup for ColoredShooterCage |
| `art/features/FeatureImage_ConnectedShooter.png` | New: rendered from the new models (and the original's pipe or UFO mesh) by `art-src/render_feature_images.py`, outline added by `art-src/outline_features.py`, 512x512 | New Feature popup for ConnectedShooter |
| `art/features/FeatureImage_ConveyorWall.png` | New: rendered from the new models (and the original's pipe or UFO mesh) by `art-src/render_feature_images.py`, outline added by `art-src/outline_features.py`, 512x512 | New Feature popup for ConveyorWall |
| `art/features/FeatureImage_Crossbow.png` | Original `art/ui/FeatureImage_Crossbow.png`, resized to 512 max | New Feature popup for Crossbow (shows no creature) |
| `art/features/FeatureImage_Curtain.png` | New: rendered from the new models (and the original's pipe or UFO mesh) by `art-src/render_feature_images.py`, outline added by `art-src/outline_features.py`, 512x512 | New Feature popup for Curtain |
| `art/features/FeatureImage_Dragon.png` | New: rendered from the new models (and the original's pipe or UFO mesh) by `art-src/render_feature_images.py`, outline added by `art-src/outline_features.py`, 512x512 | New Feature popup for Dragon |
| `art/features/FeatureImage_EggBox.png` | Original `art/ui/FeatureImage_EggBox.png`, resized to 512 max | New Feature popup for EggBox (shows no creature) |
| `art/features/FeatureImage_FrozenShooter.png` | New: rendered from the new models (and the original's pipe or UFO mesh) by `art-src/render_feature_images.py`, outline added by `art-src/outline_features.py`, 512x512 | New Feature popup for FrozenShooter |
| `art/features/FeatureImage_Gate.png` | Original `art/ui/FeatureImage_Gate.png`, resized to 512 max | New Feature popup for Gate (shows no creature) |
| `art/features/FeatureImage_HardPixel.png` | Original `art/ui/FeatureImage_HardPixel.png`, resized to 512 max | New Feature popup for HardPixel (shows no creature) |
| `art/features/FeatureImage_IceBlock.png` | Original `art/ui/FeatureImage_IceBlock.png`, resized to 512 max | New Feature popup for IceBlock (shows no creature) |
| `art/features/FeatureImage_JellyBeans.png` | Original `art/ui/FeatureImage_JellyBeans.png`, resized to 512 max | New Feature popup for JellyBeans (shows no creature) |
| `art/features/FeatureImage_LockandKey.png` | Original `art/ui/FeatureImage_LockandKey.png`, resized to 512 max | New Feature popup for LockandKey (shows no creature) |
| `art/features/FeatureImage_Matryoshka.png` | New: rendered from the new models (and the original's pipe or UFO mesh) by `art-src/render_feature_images.py`, outline added by `art-src/outline_features.py`, 512x512 | New Feature popup for Matryoshka |
| `art/features/FeatureImage_MusicToy.png` | Original `art/ui/FeatureImage_MusicToy.png`, resized to 512 max | New Feature popup for MusicToy (shows no creature) |
| `art/features/FeatureImage_PigCell.png` | New: rendered from the new models (and the original's pipe or UFO mesh) by `art-src/render_feature_images.py`, outline added by `art-src/outline_features.py`, 512x512 | New Feature popup for PigCell |
| `art/features/FeatureImage_PixelMixer.png` | Original `art/ui/FeatureImage_PixelMixer.png`, resized to 512 max | New Feature popup for PixelMixer (shows no creature) |
| `art/features/FeatureImage_PixelPipe.png` | Original `art/ui/FeatureImage_PixelPipe.png`, resized to 512 max | New Feature popup for PixelPipe (shows no creature) |
| `art/features/FeatureImage_Pumpkin.png` | New: rendered from the new models (and the original's pipe or UFO mesh) by `art-src/render_feature_images.py`, outline added by `art-src/outline_features.py`, 512x512 | New Feature popup for Pumpkin |
| `art/features/FeatureImage_Rocket.png` | Original `art/ui/FeatureImage_Rocket.png`, resized to 512 max | New Feature popup for Rocket (shows no creature) |
| `art/features/FeatureImage_Shackles.png` | New: rendered from the new models (and the original's pipe or UFO mesh) by `art-src/render_feature_images.py`, outline added by `art-src/outline_features.py`, 512x512 | New Feature popup for Shackles |
| `art/features/FeatureImage_ShooterPipe.png` | New: rendered from the new models (and the original's pipe or UFO mesh) by `art-src/render_feature_images.py`, outline added by `art-src/outline_features.py`, 512x512 | New Feature popup for ShooterPipe |
| `art/features/FeatureImage_SlotCage.png` | Original `art/ui/FeatureImage_SlotCage.png`, resized to 512 max | New Feature popup for SlotCage (shows no creature) |
| `art/features/FeatureImage_Snake.png` | New: rendered from the new models (and the original's pipe or UFO mesh) by `art-src/render_feature_images.py`, outline added by `art-src/outline_features.py`, 512x512 | New Feature popup for Snake |
| `art/features/FeatureImage_SurprisePixel.png` | Original `art/ui/FeatureImage_SurprisePixel.png`, resized to 512 max | New Feature popup for SurprisePixel (shows no creature) |
| `art/features/FeatureImage_SurpriseShooter.png` | New: rendered from the new models (and the original's pipe or UFO mesh) by `art-src/render_feature_images.py`, outline added by `art-src/outline_features.py`, 512x512 | New Feature popup for SurpriseShooter |
| `art/features/FeatureImage_Ufo.png` | New: rendered from the new models (and the original's pipe or UFO mesh) by `art-src/render_feature_images.py`, outline added by `art-src/outline_features.py`, 512x512 | New Feature popup for Ufo |
| `art/features/FeatureImage_Wall.png` | Original `art/ui/FeatureImage_Wall.png`, resized to 512 max | New Feature popup for Wall (shows no creature) |
| `art/features/FeatureImage_WoodHammer.png` | Original `art/ui/FeatureImage_WoodHammer.png`, resized to 512 max | New Feature popup for WoodHammer (shows no creature) |

## UI pictures and effects (original, copied by `art-src/copy_ui.py`)

| File | Source | Used for |
|---|---|---|
| `art/ui/Slot.png` | Original `art/ui/Slot.png` | Waiting slot row |
| `art/ui/SlotStroke.png` | Original `art/ui/SlotStroke.png` | Waiting slot row |
| `art/ui/SlotStroke3.png` | Original `art/ui/SlotStroke3.png` | Waiting slot row |
| `art/ui/FullTrayImage.png` | Original `art/ui/FullTrayImage.png` | Belt trays and the free-tray counter |
| `art/ui/HalfTrayImage.png` | Original `art/ui/HalfTrayImage.png` | Belt trays and the free-tray counter |
| `art/ui/TrayIcon.png` | Original `art/ui/TrayIcon.png` | Belt trays and the free-tray counter |
| `art/ui/Conveyor_Door_Ring_Glow.png` | Original `art/ui/Conveyor Door Ring Glow.png` | Belt texture and shadow |
| `art/ui/Texture_ConveyorShadow.png` | Original `art/ui/Texture_ConveyorShadow.png` | Belt texture and shadow |
| `art/ui/Texture_ConveyorTurn.png` | Original `art/ui/Texture_ConveyorTurn.png` | Belt texture and shadow |
| `art/ui/Texture_Ice_2.png` | Original `art/ui/Texture_Ice_2.png`, resized to 512 | Ice Blocks' tiles |
| `art/ui/1x1_v1.png` | Original `art/ui/1x1_v1.png` | Cube highlight overlays |
| `art/ui/1x1_v2.png` | Original `art/ui/1x1_v2.png` | Cube highlight overlays |
| `art/ui/1x1_v3.png` | Original `art/ui/1x1_v3.png` | Cube highlight overlays |
| `art/ui/2x2_Texture.png` | Original `art/ui/2x2_Texture.png` | Cube highlight overlays |
| `art/ui/2x2_v1.png` | Original `art/ui/2x2_v1.png` | Cube highlight overlays |
| `art/ui/2x2_v2.png` | Original `art/ui/2x2_v2.png` | Cube highlight overlays |
| `art/ui/2x2_v3.png` | Original `art/ui/2x2_v3.png` | Cube highlight overlays |
| `art/ui/IconPowerup_Bomb_Blue.png` | Original `art/ui/IconPowerup_Bomb_Blue.png` | Booster icon |
| `art/ui/IconPowerup_Bomb_Colored.png` | Original `art/ui/IconPowerup_Bomb_Colored.png` | Booster icon |
| `art/ui/IconPowerup_Bomb_Purple.png` | Original `art/ui/IconPowerup_Bomb_Purple.png` | Booster icon |
| `art/ui/IconPowerup_Bomb_Red.png` | Original `art/ui/IconPowerup_Bomb_Red.png` | Booster icon |
| `art/ui/IconPowerup_ExtraSlot_Blue.png` | Original `art/ui/IconPowerup_ExtraSlot_Blue.png` | Booster icon |
| `art/ui/IconPowerup_ExtraSlot_Colored.png` | Original `art/ui/IconPowerup_ExtraSlot_Colored.png` | Booster icon |
| `art/ui/IconPowerup_ExtraSlot_Purple.png` | Original `art/ui/IconPowerup_ExtraSlot_Purple.png` | Booster icon |
| `art/ui/IconPowerup_ExtraSlot_Red.png` | Original `art/ui/IconPowerup_ExtraSlot_Red.png` | Booster icon |
| `art/ui/IconPowerup_Hammer_Blue.png` | Original `art/ui/IconPowerup_Hammer_Blue.png` | Booster icon |
| `art/ui/IconPowerup_Hammer_Purple.png` | Original `art/ui/IconPowerup_Hammer_Purple.png` | Booster icon |
| `art/ui/IconPowerup_Hammer_Red.png` | Original `art/ui/IconPowerup_Hammer_Red.png` | Booster icon |
| `art/ui/IconPowerup_Hand_Blue.png` | Original `art/ui/IconPowerup_Hand_Blue.png` | Booster icon |
| `art/ui/IconPowerup_Hand_Colored.png` | Original `art/ui/IconPowerup_Hand_Colored.png` | Booster icon |
| `art/ui/IconPowerup_Hand_Purple.png` | Original `art/ui/IconPowerup_Hand_Purple.png` | Booster icon |
| `art/ui/IconPowerup_Hand_Red.png` | Original `art/ui/IconPowerup_Hand_Red.png` | Booster icon |
| `art/ui/IconPowerup_Shuffle_Blue.png` | Original `art/ui/IconPowerup_Shuffle_Blue.png` | Booster icon |
| `art/ui/IconPowerup_Shuffle_Colored.png` | Original `art/ui/IconPowerup_Shuffle_Colored.png` | Booster icon |
| `art/ui/IconPowerup_Shuffle_Purple.png` | Original `art/ui/IconPowerup_Shuffle_Purple.png` | Booster icon |
| `art/ui/IconPowerup_Shuffle_Red.png` | Original `art/ui/IconPowerup_Shuffle_Red.png` | Booster icon |
| `art/ui/IconPowerup_SuperShooter_Blue.png` | New, in place of the original's (which showed a pig): rendered from the cat models by `art-src/render_ui_images.py`, outline, pale variant and red X by `art-src/finish_ui_images.py`, at the original's size | Booster icon |
| `art/ui/IconPowerup_SuperShooter_Colored.png` | New, in place of the original's (which showed a pig): rendered from the cat models by `art-src/render_ui_images.py`, outline, pale variant and red X by `art-src/finish_ui_images.py`, at the original's size | Booster icon |
| `art/ui/IconPowerup_SuperShooter_Purple.png` | New, in place of the original's (which showed a pig): rendered from the cat models by `art-src/render_ui_images.py`, outline, pale variant and red X by `art-src/finish_ui_images.py`, at the original's size | Booster icon |
| `art/ui/IconPowerup_SuperShooter_Red.png` | New, in place of the original's (which showed a pig): rendered from the cat models by `art-src/render_ui_images.py`, outline, pale variant and red X by `art-src/finish_ui_images.py`, at the original's size | Booster icon |
| `art/ui/Icon_SuperBooster_Colorful.png` | New, in place of the original's (which showed a pig): rendered from the cat models by `art-src/render_ui_images.py`, outline, pale variant and red X by `art-src/finish_ui_images.py`, at the original's size | Super Unicorn icon and warning |
| `art/ui/Icon_SuperBooster_Inactive.png` | New, in place of the original's (which showed a pig): rendered from the cat models by `art-src/render_ui_images.py`, outline, pale variant and red X by `art-src/finish_ui_images.py`, at the original's size | Super Unicorn icon and warning |
| `art/ui/Icon_SuperUnicorn_Active.png` | New, in place of the original's (which showed a pig): rendered from the cat models by `art-src/render_ui_images.py`, outline, pale variant and red X by `art-src/finish_ui_images.py`, at the original's size | Super Unicorn icon and warning |
| `art/ui/LevelEndWarning_SuperUnicorn.png` | New, in place of the original's (which showed a pig): rendered from the cat models by `art-src/render_ui_images.py`, outline, pale variant and red X by `art-src/finish_ui_images.py`, at the original's size | Super Unicorn icon and warning |
| `art/ui/Button_Booster_Blue.png` | Original `art/ui/Button_Booster_Blue.png` | Booster bar button |
| `art/ui/Button_Booster_Inside_Yellow.png` | Original `art/ui/Button_Booster_Inside_Yellow.png` | Booster bar button |
| `art/ui/Button_Booster_Purple.png` | Original `art/ui/Button_Booster_Purple.png` | Booster bar button |
| `art/ui/Button_Booster_Red.png` | Original `art/ui/Button_Booster_Red.png` | Booster bar button |
| `art/ui/Button_Powerup_Green.png` | Original `art/ui/Button_Powerup_Green.png` | Booster bar button |
| `art/ui/Button_Powerup_Yellow.png` | Original `art/ui/Button_Powerup_Yellow.png` | Booster bar button |
| `art/ui/Button_SuperBooster_Black.png` | Original `art/ui/Button_SuperBooster_Black.png` | Booster bar button |
| `art/ui/Button_SuperBooster_Blue.png` | Original `art/ui/Button_SuperBooster_Blue.png` | Booster bar button |
| `art/ui/Button_SuperBooster_Fill.png` | Original `art/ui/Button_SuperBooster_Fill.png` | Booster bar button |
| `art/ui/Button_SuperBooster_Inactive.png` | Original `art/ui/Button_SuperBooster_Inactive.png` | Booster bar button |
| `art/ui/Button_SuperBooster_Purple.png` | Original `art/ui/Button_SuperBooster_Purple.png` | Booster bar button |
| `art/ui/Button_SuperBooster_Red.png` | Original `art/ui/Button_SuperBooster_Red.png` | Booster bar button |
| `art/ui/PowerupButton_Blue.png` | Original `art/ui/PowerupButton_Blue.png` | Booster bar button |
| `art/ui/PowerupButton_Disabled.png` | Original `art/ui/PowerupButton_Disabled.png` | Booster bar button |
| `art/ui/PowerupButton_Hard.png` | Original `art/ui/PowerupButton_Hard.png` | Booster bar button |
| `art/ui/PowerupButton_Purple.png` | Original `art/ui/PowerupButton_Purple.png` | Booster bar button |
| `art/ui/PowerupButton_Red.png` | Original `art/ui/PowerupButton_Red.png` | Booster bar button |
| `art/ui/PowerupButton_Yellow.png` | Original `art/ui/PowerupButton_Yellow.png` | Booster bar button |
| `art/ui/Gold_Single_Rotated_1x.png` | Original `art/ui/Gold_Single_Rotated_1x.png` | Coin icon and coin rewards |
| `art/ui/Gold_Win.png` | Original `art/ui/Gold_Win.png` | Coin icon and coin rewards |
| `art/ui/GoldTexture.png` | Original `art/ui/GoldTexture.png` | Coin icon and coin rewards |
| `art/ui/Icon_Gold.png` | Original `art/ui/Icon_Gold.png` | Coin icon and coin rewards |
| `art/ui/Icon_Gold_Gift.png` | Original `art/ui/Icon_Gold_Gift.png` | Coin icon and coin rewards |
| `art/ui/Icon_Medal_Gold.png` | Original `art/ui/Icon_Medal_Gold.png` | Trophy and wings (win panel, highest-level table) |
| `art/ui/Icon_Trophy.png` | Original `art/ui/Icon_Trophy.png` | Trophy and wings (win panel, highest-level table) |
| `art/ui/Trophy_Wing.png` | Original `art/ui/Trophy_Wing.png` | Trophy and wings (win panel, highest-level table) |
| `art/ui/Button_Black_Rounder.png` | Original `art/ui/Button_Black_Rounder.png` | Button background |
| `art/ui/Button_Black_Rounder_S.png` | Original `art/ui/Button_Black_Rounder_S.png` | Button background |
| `art/ui/Button_Blue.png` | Original `art/ui/Button_Blue.png` | Button background |
| `art/ui/Button_Blue_Rounder.png` | Original `art/ui/Button_Blue_Rounder.png` | Button background |
| `art/ui/Button_Blue_Rounder_S.png` | Original `art/ui/Button_Blue_Rounder_S.png` | Button background |
| `art/ui/Button_Blue_Small.png` | Original `art/ui/Button_Blue_Small.png` | Button background |
| `art/ui/Button_Circle_Blue.png` | Original `art/ui/Button_Circle_Blue.png` | Button background |
| `art/ui/Button_Circle_Dark.png` | Original `art/ui/Button_Circle_Dark.png` | Button background |
| `art/ui/Button_Circle_Hard.png` | Original `art/ui/Button_Circle_Hard.png` | Button background |
| `art/ui/Button_Circle_Purple.png` | Original `art/ui/Button_Circle_Purple.png` | Button background |
| `art/ui/Button_Circle_Red.png` | Original `art/ui/Button_Circle_Red.png` | Button background |
| `art/ui/Button_Circle_Yellow.png` | Original `art/ui/Button_Circle_Yellow.png` | Button background |
| `art/ui/Button_Close_Floating.png` | Original `art/ui/Button_Close_Floating.png` | Button background |
| `art/ui/Button_Close_Popup.png` | Original `art/ui/Button_Close_Popup.png` | Button background |
| `art/ui/Button_Close_Popup_Bg.png` | Original `art/ui/Button_Close_Popup_Bg.png` | Button background |
| `art/ui/Button_Close_Popup_Dark.png` | Original `art/ui/Button_Close_Popup_Dark.png` | Button background |
| `art/ui/Button_Close_Popup_Dark_OutlineOrange.png` | Original `art/ui/Button_Close_Popup_Dark_OutlineOrange.png` | Button background |
| `art/ui/Button_Dark.png` | Original `art/ui/Button_Dark.png` | Button background |
| `art/ui/Button_Dark_Small.png` | Original `art/ui/Button_Dark_Small.png` | Button background |
| `art/ui/Button_Disabled.png` | Original `art/ui/Button_Disabled.png` | Button background |
| `art/ui/Button_Disabled_Rounder.png` | Original `art/ui/Button_Disabled_Rounder.png` | Button background |
| `art/ui/Button_Disabled_Rounder_S.png` | Original `art/ui/Button_Disabled_Rounder_S.png` | Button background |
| `art/ui/Button_Disabled_Small.png` | Original `art/ui/Button_Disabled_Small.png` | Button background |
| `art/ui/Button_Green.png` | Original `art/ui/Button_Green.png` | Button background |
| `art/ui/Button_Green_Rounder.png` | Original `art/ui/Button_Green_Rounder.png` | Button background |
| `art/ui/Button_Green_Rounder_S.png` | Original `art/ui/Button_Green_Rounder_S.png` | Button background |
| `art/ui/Button_Green_Rounder_XS.png` | Original `art/ui/Button_Green_Rounder_XS.png` | Button background |
| `art/ui/Button_Green_Small.png` | Original `art/ui/Button_Green_Small.png` | Button background |
| `art/ui/Button_Info.png` | Original `art/ui/Button_Info.png` | Button background |
| `art/ui/Button_Info_Red.png` | Original `art/ui/Button_Info_Red.png` | Button background |
| `art/ui/Button_Mint.png` | Original `art/ui/Button_Mint.png` | Button background |
| `art/ui/Button_Mint_Small.png` | Original `art/ui/Button_Mint_Small.png` | Button background |
| `art/ui/Button_Pink.png` | Original `art/ui/Button_Pink.png` | Button background |
| `art/ui/Button_Pink_Small.png` | Original `art/ui/Button_Pink_Small.png` | Button background |
| `art/ui/Button_Play.png` | Original `art/ui/Button_Play.png` | Button background |
| `art/ui/Button_Purple.png` | Original `art/ui/Button_Purple.png` | Button background |
| `art/ui/Button_Purple_Rounder.png` | Original `art/ui/Button_Purple_Rounder.png` | Button background |
| `art/ui/Button_Purple_Rounder_S.png` | Original `art/ui/Button_Purple_Rounder_S.png` | Button background |
| `art/ui/Button_Purple_Small.png` | Original `art/ui/Button_Purple_Small.png` | Button background |
| `art/ui/Button_Red.png` | Original `art/ui/Button_Red.png` | Button background |
| `art/ui/Button_Red_Rounder.png` | Original `art/ui/Button_Red_Rounder.png` | Button background |
| `art/ui/Button_Red_Rounder_S.png` | Original `art/ui/Button_Red_Rounder_S.png` | Button background |
| `art/ui/Button_Red_Small.png` | Original `art/ui/Button_Red_Small.png` | Button background |
| `art/ui/Button_Simple_Blue.png` | Original `art/ui/Button_Simple_Blue.png` | Button background |
| `art/ui/Button_Simple_Green.png` | Original `art/ui/Button_Simple_Green.png` | Button background |
| `art/ui/Button_Simple_Yellow.png` | Original `art/ui/Button_Simple_Yellow.png` | Button background |
| `art/ui/Button_Sky.png` | Original `art/ui/Button_Sky.png` | Button background |
| `art/ui/Button_Sky_Rounder_1.png` | Original `art/ui/Button_Sky_Rounder 1.png` | Button background |
| `art/ui/Button_Sky_Rounder.png` | Original `art/ui/Button_Sky_Rounder.png` | Button background |
| `art/ui/Button_Sky_Rounder_S.png` | Original `art/ui/Button_Sky_Rounder_S.png` | Button background |
| `art/ui/Button_Sky_Small.png` | Original `art/ui/Button_Sky_Small.png` | Button background |
| `art/ui/Button_Yellow.png` | Original `art/ui/Button_Yellow.png` | Button background |
| `art/ui/Button_Yellow_Rounder.png` | Original `art/ui/Button_Yellow_Rounder.png` | Button background |
| `art/ui/Button_Yellow_Rounder_S.png` | Original `art/ui/Button_Yellow_Rounder_S.png` | Button background |
| `art/ui/Button_Yellow_Small.png` | Original `art/ui/Button_Yellow_Small.png` | Button background |
| `art/ui/Popup.png` | Original `art/ui/Popup.png` | Popup frame |
| `art/ui/Popup_Plain_Blue.png` | Original `art/ui/Popup_Plain_Blue.png` | Popup frame |
| `art/ui/Popup_Plain_DarkBlue.png` | Original `art/ui/Popup_Plain_DarkBlue.png` | Popup frame |
| `art/ui/Popup_Plain_FairyForest.png` | Original `art/ui/Popup_Plain_FairyForest.png` | Popup frame |
| `art/ui/Popup_Plain_Hard.png` | Original `art/ui/Popup_Plain_Hard.png` | Popup frame |
| `art/ui/Popup_Plain_Orange.png` | Original `art/ui/Popup_Plain_Orange.png` | Popup frame |
| `art/ui/Popup_Plain_Purple.png` | Original `art/ui/Popup_Plain_Purple.png` | Popup frame |
| `art/ui/Popup_Plain_Purple_Dark.png` | Original `art/ui/Popup_Plain_Purple_Dark.png` | Popup frame |
| `art/ui/Popup_Plain_Red.png` | Original `art/ui/Popup_Plain_Red.png` | Popup frame |
| `art/ui/Popup_Plain_Yellow.png` | Original `art/ui/Popup_Plain_Yellow.png` | Popup frame |
| `art/ui/Popup_Section_Blue.png` | Original `art/ui/Popup_Section_Blue.png` | Popup frame |
| `art/ui/Popup_Section_Blue_Bold.png` | Original `art/ui/Popup_Section_Blue_Bold.png` | Popup frame |
| `art/ui/Popup_Section_Blue_Borderless.png` | Original `art/ui/Popup_Section_Blue_Borderless.png` | Popup frame |
| `art/ui/Popup_Section_Blue_Lilac.png` | Original `art/ui/Popup_Section_Blue_Lilac.png` | Popup frame |
| `art/ui/Popup_Section_BlueDark_BorderRadiusSmall.png` | Original `art/ui/Popup_Section_BlueDark_BorderRadiusSmall.png` | Popup frame |
| `art/ui/Popup_Section_Circle_Blue.png` | Original `art/ui/Popup_Section_Circle_Blue.png` | Popup frame |
| `art/ui/Popup_Section_Circle_Purple.png` | Original `art/ui/Popup_Section_Circle_Purple.png` | Popup frame |
| `art/ui/Popup_Section_Circle_Red.png` | Original `art/ui/Popup_Section_Circle_Red.png` | Popup frame |
| `art/ui/Popup_Section_Hard.png` | Original `art/ui/Popup_Section_Hard.png` | Popup frame |
| `art/ui/Popup_Section_Purple.png` | Original `art/ui/Popup_Section_Purple.png` | Popup frame |
| `art/ui/Popup_Section_Purple_Borderless.png` | Original `art/ui/Popup_Section_Purple_Borderless.png` | Popup frame |
| `art/ui/Popup_Section_Red.png` | Original `art/ui/Popup_Section_Red.png` | Popup frame |
| `art/ui/Popup_Section_Red_Borderless.png` | Original `art/ui/Popup_Section_Red_Borderless.png` | Popup frame |
| `art/ui/Popup_Section_RedDark.png` | Original `art/ui/Popup_Section_RedDark.png` | Popup frame |
| `art/ui/Popup_Section_Yellow.png` | Original `art/ui/Popup_Section_Yellow.png` | Popup frame |
| `art/ui/Popup_Section_Yellow_Borderless.png` | Original `art/ui/Popup_Section_Yellow_Borderless.png` | Popup frame |
| `art/ui/Popup_Section_Yellow_Light.png` | Original `art/ui/Popup_Section_Yellow_Light.png` | Popup frame |
| `art/ui/Popup_With_Header_Blue.png` | Original `art/ui/Popup_With_Header_Blue.png` | Popup frame |
| `art/ui/Popup_With_Header_ContentMask.png` | Original `art/ui/Popup_With_Header_ContentMask.png` | Popup frame |
| `art/ui/Popup_With_Header_DarkBlue_Light.png` | Original `art/ui/Popup_With_Header_DarkBlue_Light.png` | Popup frame |
| `art/ui/Popup_With_Header_Hard.png` | Original `art/ui/Popup_With_Header_Hard.png` | Popup frame |
| `art/ui/Popup_With_Header_Purple.png` | Original `art/ui/Popup_With_Header_Purple.png` | Popup frame |
| `art/ui/Popup_With_Header_Red.png` | Original `art/ui/Popup_With_Header_Red.png` | Popup frame |
| `art/ui/Popup_With_Header_Yellow.png` | Original `art/ui/Popup_With_Header_Yellow.png` | Popup frame |
| `art/ui/PopupPanels.png` | Original `art/ui/PopupPanels.png` | Popup frame |
| `art/ui/Frame_Basic_Circle160.png` | Original `art/ui/Frame_Basic_Circle160.png` | Panel and label frame |
| `art/ui/Frame_Basic_Rounded78.png` | Original `art/ui/Frame_Basic_Rounded78.png` | Panel and label frame |
| `art/ui/Frame_Border_Mask.png` | Original `art/ui/Frame_Border_Mask.png` | Panel and label frame |
| `art/ui/Frame_Border_Yellow.png` | Original `art/ui/Frame_Border_Yellow.png` | Panel and label frame |
| `art/ui/Frame_Bubble_Blue.png` | Original `art/ui/Frame_Bubble_Blue.png` | Panel and label frame |
| `art/ui/Frame_Bubble_Hard.png` | Original `art/ui/Frame_Bubble_Hard.png` | Panel and label frame |
| `art/ui/Frame_Bubble_Purple.png` | Original `art/ui/Frame_Bubble_Purple.png` | Panel and label frame |
| `art/ui/Frame_Bubble_Red.png` | Original `art/ui/Frame_Bubble_Red.png` | Panel and label frame |
| `art/ui/Frame_Bubble_Yellow.png` | Original `art/ui/Frame_Bubble_Yellow.png` | Panel and label frame |
| `art/ui/Frame_Input_Field_Blue.png` | Original `art/ui/Frame_Input_Field_Blue.png` | Panel and label frame |
| `art/ui/Frame_Item_Card_Blue.png` | Original `art/ui/Frame_Item_Card_Blue.png` | Panel and label frame |
| `art/ui/Frame_Item_Card_Yellow.png` | Original `art/ui/Frame_Item_Card_Yellow.png` | Panel and label frame |
| `art/ui/Frame_Label_Pill_Red.png` | Original `art/ui/Frame_Label_Pill_Red.png` | Panel and label frame |
| `art/ui/Frame_Label_Rounded_Blue.png` | Original `art/ui/Frame_Label_Rounded_Blue.png` | Panel and label frame |
| `art/ui/Frame_Label_Rounded_Dark.png` | Original `art/ui/Frame_Label_Rounded_Dark.png` | Panel and label frame |
| `art/ui/Frame_Label_Rounded_Red.png` | Original `art/ui/Frame_Label_Rounded_Red.png` | Panel and label frame |
| `art/ui/Frame_tile_1.png` | Original `art/ui/Frame_tile_1.png` | Panel and label frame |
| `art/ui/Frame_Triangle_DarkBlue.png` | Original `art/ui/Frame_Triangle_DarkBlue.png` | Panel and label frame |
| `art/ui/Frame_Yellow_Light.png` | Original `art/ui/Frame_Yellow_Light.png` | Panel and label frame |
| `art/ui/Frame_Yellow_Light_Arrow_L.png` | Original `art/ui/Frame_Yellow_Light_Arrow_L.png` | Panel and label frame |
| `art/ui/Frame_Yellow_Light_L.png` | Original `art/ui/Frame_Yellow_Light_L.png` | Panel and label frame |
| `art/ui/Icon_Close02.png` | Original `art/ui/Icon_Close02.png` | Settings panel and close icons |
| `art/ui/Icon_Settings.png` | Original `art/ui/Icon_Settings.png` | Settings panel and close icons |
| `art/ui/Slider_Handle.png` | Original `art/ui/Slider_Handle.png` | Settings panel and close icons |
| `art/ui/Toggle_Handle.png` | Original `art/ui/Toggle_Handle.png` | Settings panel and close icons |
| `art/ui/Icon_GoldenLock.png` | Original `art/ui/Icon GoldenLock.png` | Lock icons |
| `art/ui/Icon_Lock.png` | Original `art/ui/Icon_Lock.png` | Lock icons |
| `art/ui/Icon_Lock01_l.png` | Original `art/ui/Icon_Lock01_l.png` | Lock icons |
| `art/ui/Icon_Lock_Open_Small.png` | Original `art/ui/Icon_Lock_Open_Small.png` | Lock icons |
| `art/ui/Icon_Lock_White.png` | Original `art/ui/Icon_Lock_White.png` | Lock icons |
| `art/ui/Icon_Lock_Yellow.png` | Original `art/ui/Icon_Lock_Yellow.png` | Lock icons |
| `art/ui/Icon_Locked_Out_Offer.png` | Original `art/ui/Icon_Locked_Out_Offer.png` | Lock icons |
| `art/ui/Lock.png` | Original `art/ui/Lock.png` | Lock icons |
| `art/ui/Icon_Curtain_Fail_Offer.png` | New, in place of the original's (which showed a pig): rendered from the cat models by `art-src/render_ui_images.py`, outline, pale variant and red X by `art-src/finish_ui_images.py`, at the original's size | Fail-offer (revive) icon |
| `art/ui/Icon_Frozen_Offer.png` | New, in place of the original's (which showed a pig): rendered from the cat models by `art-src/render_ui_images.py`, outline, pale variant and red X by `art-src/finish_ui_images.py`, at the original's size | Fail-offer (revive) icon |
| `art/ui/Icon_Hammer_Block.png` | Original `art/ui/Icon_Hammer_Block.png` | Fail-offer (revive) icon |
| `art/ui/Icon_Hammer_Block_Tight.png` | Original `art/ui/Icon_Hammer_Block_Tight.png` | Fail-offer (revive) icon |
| `art/ui/Icon_Obstacle_Fail_Offer.png` | Original `art/ui/Icon_Obstacle_Fail_Offer.png` | Fail-offer (revive) icon |
| `art/ui/Icon_Out_Of_Space_Offer.png` | New, in place of the original's (which showed a pig): rendered from the cat models by `art-src/render_ui_images.py`, outline, pale variant and red X by `art-src/finish_ui_images.py`, at the original's size | Fail-offer (revive) icon |
| `art/ui/Icon_Spaceship_Fail_Offer.png` | Original `art/ui/Icon_Spaceship_Fail_Offer.png` | Fail-offer (revive) icon |
| `art/ui/Icon_Ufo_Fail_Offer.png` | Original `art/ui/Icon_Ufo_Fail_Offer.png` | Fail-offer (revive) icon |
| `art/ui/Icon_Clock_Mini.png` | Original `art/ui/Icon_Clock_Mini.png` | Stars, clock, start icon |
| `art/ui/Icon_Clock_Pico.png` | Original `art/ui/Icon_Clock_Pico.png` | Stars, clock, start icon |
| `art/ui/Icon_Rate_Star.png` | Original `art/ui/Icon_Rate_Star.png` | Stars, clock, start icon |
| `art/ui/Icon_Rate_Star_Empty.png` | Original `art/ui/Icon_Rate_Star_Empty.png` | Stars, clock, start icon |
| `art/ui/Icon_Start.png` | Original `art/ui/Icon_Start.png` | Stars, clock, start icon |
| `art/ui/Hard_Level.png` | Original `art/ui/Hard Level.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Inner_Glow.png` | Original `art/ui/Inner_Glow.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Current_Shiny.png` | Original `art/ui/Level_Current_Shiny.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Current_Shiny_Black.png` | Original `art/ui/Level_Current_Shiny_Black.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Current_Shiny_Purple.png` | Original `art/ui/Level_Current_Shiny_Purple.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Current_Shiny_Red.png` | Original `art/ui/Level_Current_Shiny_Red.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Current_Shiny_Yellow.png` | Original `art/ui/Level_Current_Shiny_Yellow.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Feature_Intro_Bg.png` | Original `art/ui/Level_Feature_Intro_Bg.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Hard.png` | Original `art/ui/Level_Hard.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Label_Hard.png` | Original `art/ui/Level_Label_Hard.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Label_Hard_Glow.png` | Original `art/ui/Level_Label_Hard_Glow.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Label_Purple.png` | Original `art/ui/Level_Label_Purple.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Label_Purple_Glow.png` | Original `art/ui/Level_Label_Purple_Glow.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Label_Red.png` | Original `art/ui/Level_Label_Red.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Label_Red_Glow.png` | Original `art/ui/Level_Label_Red_Glow.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Label_Yellow.png` | Original `art/ui/Level_Label_Yellow.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Label_Yellow_Glow.png` | Original `art/ui/Level_Label_Yellow_Glow.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Normal.png` | Original `art/ui/Level_Normal.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Orange.png` | Original `art/ui/Level_Orange.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Orange_Red.png` | Original `art/ui/Level_Orange_Red.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Purple.png` | Original `art/ui/Level_Purple.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Tree_Column.png` | Original `art/ui/Level_Tree_Column.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Level_Tree_Column_Yellow.png` | Original `art/ui/Level_Tree_Column_Yellow.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/LevelWin.png` | Original `art/ui/LevelWin.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Pattern_FairyForest.png` | Original `art/ui/Pattern_FairyForest.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Pattern_Gift.png` | Original `art/ui/Pattern_Gift.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Pattern_Gift_Tiled.png` | Original `art/ui/Pattern_Gift_Tiled.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Pattern_HardLevel.png` | Original `art/ui/Pattern_HardLevel.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Pattern_Star.png` | Original `art/ui/Pattern_Star.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Pattern_VeryHardLevel.png` | Original `art/ui/Pattern_VeryHardLevel.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Play_Button_Glow.png` | Original `art/ui/Play_Button_Glow.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Plus_Black.png` | Original `art/ui/Plus_Black.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Plus_Green.png` | Original `art/ui/Plus_Green.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Plus_Red.png` | Original `art/ui/Plus_Red.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Plus_Yellow.png` | Original `art/ui/Plus_Yellow.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/StarPattern01.png` | Original `art/ui/StarPattern01.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/StarPattern02.png` | Original `art/ui/StarPattern02.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/SuperHardVisual.png` | Original `art/ui/SuperHardVisual.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/VeryHard_Level.png` | Original `art/ui/VeryHard Level.png` | Level path, level labels, win panel and backgrounds |
| `art/ui/Arrow_Up_4x.png` | Original `art/ui/Arrow_Up_4x.png` | Tutorial hand, arrows and speech bubble frames |
| `art/ui/Bubble_Arrow_Yellow.png` | Original `art/ui/Bubble_Arrow_Yellow.png` | Tutorial hand, arrows and speech bubble frames |
| `art/ui/Bubble_Yellow.png` | Original `art/ui/Bubble_Yellow.png` | Tutorial hand, arrows and speech bubble frames |
| `art/ui/BubbleFrame01_BgArrow.png` | Original `art/ui/BubbleFrame01_BgArrow.png` | Tutorial hand, arrows and speech bubble frames |
| `art/ui/BubbleFrame04_White_Arrow.png` | Original `art/ui/BubbleFrame04_White_Arrow.png` | Tutorial hand, arrows and speech bubble frames |
| `art/ui/BubbleFrame04_White_Bg.png` | Original `art/ui/BubbleFrame04_White_Bg.png` | Tutorial hand, arrows and speech bubble frames |
| `art/ui/Hand_Pointing.png` | Original `art/ui/Hand_Pointing.png` | Tutorial hand, arrows and speech bubble frames |
| `art/ui/Hand_Touched.png` | Original `art/ui/Hand_Touched.png` | Tutorial hand, arrows and speech bubble frames |
| `art/ui/Speech_Bubble.png` | Original `art/ui/Speech_Bubble.png` | Tutorial hand, arrows and speech bubble frames |
| `art/ui/Texture_Arrow.png` | Original `art/ui/Texture_Arrow.png` | Tutorial hand, arrows and speech bubble frames |
| `art/ui/Texture_UpGlow.png` | Original `art/ui/Texture_UpGlow.png` | Tutorial hand, arrows and speech bubble frames |
| `art/ui/Texture_UpGlowMain.png` | Original `art/ui/Texture_UpGlowMain.png` | Tutorial hand, arrows and speech bubble frames |
| `art/ui/Tutorial_Arrow_Curved_Left.png` | Original `art/ui/Tutorial_Arrow_Curved_Left.png` | Tutorial hand, arrows and speech bubble frames |
| `art/ui/Tutorial_Arrow_Curved_Right.png` | Original `art/ui/Tutorial_Arrow_Curved_Right.png` | Tutorial hand, arrows and speech bubble frames |
| `art/ui/Tutorial_Arrow_Straight.png` | Original `art/ui/Tutorial_Arrow_Straight.png` | Tutorial hand, arrows and speech bubble frames |
| `art/ui/tutorial_hand_2.png` | Original `art/ui/tutorial_hand_2.png` | Tutorial hand, arrows and speech bubble frames |
| `art/ui/Tutorial_Step2.png` | New, in place of the original's (which showed a pig): rendered from the cat models by `art-src/render_ui_images.py`, outline, pale variant and red X by `art-src/finish_ui_images.py`, at the original's size | Tutorial hand, arrows and speech bubble frames |
| `art/ui/Tutorial_Step3.png` | New, in place of the original's (which showed a pig): rendered from the cat models by `art-src/render_ui_images.py`, outline, pale variant and red X by `art-src/finish_ui_images.py`, at the original's size | Tutorial hand, arrows and speech bubble frames |
| `art/effects/fx_circle.png` | Original `art/other/fx_circle.png` | Soft shadow and effect sprite |
| `art/effects/fx_circle_glow.png` | Original `art/other/fx_circle_glow.png` | Soft shadow and effect sprite |
| `art/effects/fx_circle_line_blue.png` | Original `art/other/fx_circle_line_blue.png` | Soft shadow and effect sprite |
| `art/effects/fx_glow.png` | Original `art/other/fx_glow.png` | Soft shadow and effect sprite |
| `art/effects/fx_glow_small.png` | Original `art/other/fx_glow_small.png` | Soft shadow and effect sprite |
| `art/effects/fx_rotate_line.png` | Original `art/other/fx_rotate_line.png` | Soft shadow and effect sprite |
| `art/effects/fx_special_particle_blue.png` | Original `art/other/fx_special_particle_blue.png` | Soft shadow and effect sprite |
| `art/effects/fx_star_blue.png` | Original `art/other/fx_star_blue.png` | Soft shadow and effect sprite |
| `art/effects/fx_star_white.png` | Original `art/other/fx_star_white.png` | Soft shadow and effect sprite |
| `art/effects/fx_star_yellow.png` | Original `art/other/fx_star_yellow.png` | Soft shadow and effect sprite |
| `art/effects/glow1.png` | Original `art/other/glow1.png` | Soft shadow and effect sprite |
| `art/effects/glow2.png` | Original `art/other/glow2.png` | Soft shadow and effect sprite |
| `art/effects/glow6.png` | Original `art/other/glow6.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_10x10Door.png` | Original `art/other/Shadow_10x10Door.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_12x10Door.png` | Original `art/other/Shadow_12x10Door.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_14x14Door.png` | Original `art/other/Shadow_14x14Door.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_18x18Door.png` | Original `art/other/Shadow_18x18Door.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_1x1_Circle.png` | Original `art/other/Shadow_1x1 Circle.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_1x1_Cube.png` | Original `art/other/Shadow_1x1 Cube.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_1x1_Gem.png` | Original `art/other/Shadow_1x1 Gem.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_1x2.png` | Original `art/other/Shadow_1x2.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_1x3.png` | Original `art/other/Shadow_1x3.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_1x4.png` | Original `art/other/Shadow_1x4.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_1x5.png` | Original `art/other/Shadow_1x5.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_2x1.png` | Original `art/other/Shadow_2x1.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_2x2_Circle.png` | Original `art/other/Shadow_2x2 Circle.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_2x2.png` | Original `art/other/Shadow_2x2.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_2x2Cube.png` | Original `art/other/Shadow_2x2Cube.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_2x3.png` | Original `art/other/Shadow_2x3.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_2x4.png` | Original `art/other/Shadow_2x4.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_3x1.png` | Original `art/other/Shadow_3x1.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_3x2.png` | Original `art/other/Shadow_3x2.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_3x3.png` | Original `art/other/Shadow_3x3.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_4x1.png` | Original `art/other/Shadow_4x1.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_5x1.png` | Original `art/other/Shadow_5x1.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_Eggbox2x2.png` | Original `art/other/Shadow_Eggbox2x2.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_Eggbox2x3.png` | Original `art/other/Shadow_Eggbox2x3.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_Eggbox3x2.png` | Original `art/other/Shadow_Eggbox3x2.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_GoldenEgg.png` | Original `art/other/Shadow_GoldenEgg.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_IceBlock.png` | Original `art/other/Shadow_IceBlock.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_PixelPipe.png` | Original `art/other/Shadow_PixelPipe.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_Wall.png` | Original `art/other/Shadow_Wall.png` | Soft shadow and effect sprite |
| `art/effects/Shadow_WoodBlock.png` | Original `art/other/Shadow_WoodBlock.png` | Soft shadow and effect sprite |
| `art/effects/tile_particle1_1_(1).png` | Original `art/other/tile_particle1 1 (1).png` | Soft shadow and effect sprite |
| `art/effects/tile_particle1_1_(2).png` | Original `art/other/tile_particle1 1 (2).png` | Soft shadow and effect sprite |
| `art/effects/tile_particle1_1.png` | Original `art/other/tile_particle1 1.png` | Soft shadow and effect sprite |
| `art/effects/tile_particle1_1__1991.png` | Original `art/other/tile_particle1 1__1991.png` | Soft shadow and effect sprite |
| `art/effects/tile_particle2_1_(1).png` | Original `art/other/tile_particle2 1 (1).png` | Soft shadow and effect sprite |
| `art/effects/tile_particle2_1_(2).png` | Original `art/other/tile_particle2 1 (2).png` | Soft shadow and effect sprite |
| `art/effects/tile_particle2_1.png` | Original `art/other/tile_particle2 1.png` | Soft shadow and effect sprite |
| `art/effects/tile_particle2_1__2044.png` | Original `art/other/tile_particle2 1__2044.png` | Soft shadow and effect sprite |
| `art/effects/tile_particle3_1_(1).png` | Original `art/other/tile_particle3 1 (1).png` | Soft shadow and effect sprite |
| `art/effects/tile_particle3_1_(2).png` | Original `art/other/tile_particle3 1 (2).png` | Soft shadow and effect sprite |
| `art/effects/tile_particle3_1.png` | Original `art/other/tile_particle3 1.png` | Soft shadow and effect sprite |
| `art/effects/tile_particle3_1__2218.png` | Original `art/other/tile_particle3 1__2218.png` | Soft shadow and effect sprite |
| `art/effects/tile_particle4_1_(1).png` | Original `art/other/tile_particle4 1 (1).png` | Soft shadow and effect sprite |
| `art/effects/tile_particle4_1_(2).png` | Original `art/other/tile_particle4 1 (2).png` | Soft shadow and effect sprite |
| `art/effects/tile_particle4_1.png` | Original `art/other/tile_particle4 1.png` | Soft shadow and effect sprite |
| `art/effects/tile_particle4_1__2268.png` | Original `art/other/tile_particle4 1__2268.png` | Soft shadow and effect sprite |
| `art/effects/tile_particle5_1_(1).png` | Original `art/other/tile_particle5 1 (1).png` | Soft shadow and effect sprite |
| `art/effects/tile_particle5_1_(2).png` | Original `art/other/tile_particle5 1 (2).png` | Soft shadow and effect sprite |
| `art/effects/tile_particle5_1.png` | Original `art/other/tile_particle5 1.png` | Soft shadow and effect sprite |
| `art/effects/tile_particle5_1__2204.png` | Original `art/other/tile_particle5 1__2204.png` | Soft shadow and effect sprite |
| `art/effects/tile_particle6_1_(1).png` | Original `art/other/tile_particle6 1 (1).png` | Soft shadow and effect sprite |
| `art/effects/tile_particle6_1_(2).png` | Original `art/other/tile_particle6 1 (2).png` | Soft shadow and effect sprite |
| `art/effects/tile_particle6_1.png` | Original `art/other/tile_particle6 1.png` | Soft shadow and effect sprite |
| `art/effects/tile_particle6_1__2060.png` | Original `art/other/tile_particle6 1__2060.png` | Soft shadow and effect sprite |
| `art/effects/tile_particle7_1_(1).png` | Original `art/other/tile_particle7 1 (1).png` | Soft shadow and effect sprite |
| `art/effects/tile_particle7_1_(2).png` | Original `art/other/tile_particle7 1 (2).png` | Soft shadow and effect sprite |
| `art/effects/tile_particle7_1.png` | Original `art/other/tile_particle7 1.png` | Soft shadow and effect sprite |
| `art/effects/tile_particle7_1__2019.png` | Original `art/other/tile_particle7 1__2019.png` | Soft shadow and effect sprite |

## Fonts

| File | Source | Used for |
|---|---|---|
| `fonts/inter-24-black.ttf` | Original `art/fonts/inter-24-black.ttf` (Inter, SIL Open Font License 1.1, rsms.me) | Headings and numbers |
| `fonts/Roboto-Bold.ttf` | Original `art/fonts/Roboto-Bold.ttf` (Roboto, Apache License 2.0) | Text |

`GangwonEducationTteontteonBlack.ttf` is not shipped: its font data carries only an all-rights-reserved notice and no license, so headings use Inter Black.

## Models: characters (new, built by `art-src/make_models.py`, previews in `art-src/previews/<name>.png`)

| File | Source | Used for |
|---|---|---|
| `models/pig.glb` | New: `make_models.py` | The cat shooter: queues, belt, slots (white base, tint per color, face sheet) |
| `models/pig_surprise.glb` | New: `make_models.py` | Surprise cat (purple, floating question mark) |
| `models/overlay_frozen.glb` | New: `make_models.py` | Frozen cat overlay (ice shell, spikes, base) |
| `models/overlay_chains.glb` | New: `make_models.py` | Shackles overlay (two chain straps and a clasp) |
| `models/overlay_lock.glb` | New: `make_models.py` | Locked cat overlay (padlock) |
| `models/overlay_astro.glb` | New: `make_models.py` | Astro cat overlay (helmet, ring, backpack, lights) |
| `models/overlay_cage.glb` | New: `make_models.py` | Caged cat overlay (cage bars), Cat Cell and Dungeon |
| `models/mascot.glb` | New: `make_models.py` | Tutorial mascot (orange cat with a speech bubble; the page draws the text) |
| `models/pig_super_shooter.glb` | New: `make_models.py` | Super Shooter cat with a cape |
| `models/unicorn.glb` | New: `make_models.py` | Super Unicorn (a white cat with a horn, rainbow mane and tail) |
| `models/snake_head.glb` | New: `make_models.py` | Snake head (tinted) |
| `models/snake_body.glb` | New: `make_models.py` | Snake body piece (tinted) |
| `models/snake_tail.glb` | New: `make_models.py` | Snake tail (tinted) |
| `models/dragon_head.glb` | New: `make_models.py` | Dragon head (tinted) |
| `models/dragon_body.glb` | New: `make_models.py` | Dragon body piece (tinted) |
| `models/dragon_tail.glb` | New: `make_models.py` | Dragon tail (tinted) |
| `models/bull_totem.glb` | New: `make_models.py` | Bull totem block |
| `models/matryoshka_doll.glb` | New: `make_models.py` | Catroshka doll (dress and collar tinted, cat face) |
| `models/pumpkin.glb` | New: `make_models.py` | Pumpkin with a carved face made for this game (body tinted) |
| `models/matryoshka_shell.glb` | New: `make_models.py` | Catroshka shell, the open bottom half (tinted) |

## Models: the original's face-less meshes (OBJ converted to GLB)

Found by reading each prefab's mesh references with UnityPy (`art-src/extract_prefabs.py`, mesh-to-prefab map `art-src/meshmap.json`), converted by Blender (`art-src/obj_to_glb.py`). The belt pieces come from the level scene's conveyor objects (`Belt Straight`, `Belt Start`, `Belt End`, `Belt Turn`).

| File | Source prefab | Used for |
|---|---|---|
| `models/features/hardpixel_3x3.glb` | Original prefab `HardPixel 3x3` (1 mesh nodes) | HardPixel 3x3 |
| `models/features/hardpixel_2x2.glb` | Original prefab `HardPixel 2x2` (1 mesh nodes) | HardPixel 2x2 |
| `models/features/demolish_bomb.glb` | Original prefab `Demolish Bomb` (1 mesh nodes) | Demolish Bomb |
| `models/features/pixel_1x1_low_poly.glb` | Original prefab `Pixel 1x1 Low Poly` (1 mesh nodes) | Pixel 1x1 Low Poly |
| `models/features/conveyor_item_slot.glb` | Original prefab `Conveyor Item Slot` (1 mesh nodes) | Conveyor Item Slot |
| `models/features/pixel_2x2_variant.glb` | Original prefab `Pixel 2x2 Variant` (1 mesh nodes) | Pixel 2x2 Variant |
| `models/features/pixel_1x1.glb` | Original prefab `Pixel 1x1` (1 mesh nodes) | Pixel 1x1 |
| `models/features/belt_end.glb` | Original prefab `Belt End` (2 mesh nodes) | Belt End |
| `models/features/belt_straight.glb` | Original prefab `Belt Straight` (1 mesh nodes) | Belt Straight |
| `models/features/belt_start.glb` | Original prefab `Belt Start` (1 mesh nodes) | Belt Start |
| `models/features/belt_turn.glb` | Original prefab `Belt Turn` (1 mesh nodes) | Belt Turn |
| `models/features/egg_box_model_6_3x2_variant.glb` | Original prefab `Egg Box Model 6 3x2 Variant` (13 mesh nodes) | Egg Box Model 6 3x2 Variant |
| `models/features/bead_instance.glb` | Original prefab `Bead Instance` (4 mesh nodes) | Bead Instance |
| `models/features/egg_box_model_4_2x2_variant.glb` | Original prefab `Egg Box Model 4 2x2 Variant` (9 mesh nodes) | Egg Box Model 4 2x2 Variant |
| `models/features/biscuit_feature.glb` | Original prefab `Biscuit Feature` (6 mesh nodes) | Biscuit Feature |
| `models/features/key_feature.glb` | Original prefab `Key Feature` (1 mesh nodes) | Key Feature |
| `models/features/colored_shooter_cage_feature.glb` | Original prefab `Colored Shooter Cage Feature` (6 mesh nodes) | Colored Shooter Cage Feature |
| `models/features/pixel_pipe_feature.glb` | Original prefab `Pixel Pipe Feature` (2 mesh nodes) | Pixel Pipe Feature |
| `models/features/golden_egg_feature.glb` | Original prefab `Golden Egg Feature` (3 mesh nodes) | Golden Egg Feature |
| `models/features/curtain_feature.glb` | Original prefab `Curtain Feature` (2 mesh nodes) | Curtain Feature |
| `models/features/lock_feature.glb` | Original prefab `Lock Feature` (3 mesh nodes) | Lock Feature |
| `models/features/shooter_pipe_feature.glb` | Original prefab `Shooter Pipe Feature` (2 mesh nodes) | Shooter Pipe Feature |
| `models/features/hammer_feature.glb` | Original prefab `Hammer Feature` (1 mesh nodes) | Hammer Feature |
| `models/features/spaceship_model_base.glb` | Original prefab `Spaceship Model Base` (3 mesh nodes) | Spaceship Model Base |
| `models/features/pumpkin_feature.glb` | Original prefab `Pumpkin Feature` (1 mesh nodes) | Pumpkin Feature |
| `models/features/accordion_feature.glb` | Original prefab `Accordion Feature` (69 mesh nodes) | Accordion Feature |
| `models/features/pixel_ice_block_model_default.glb` | Original prefab `Pixel Ice Block Model Default` (11 mesh nodes) | Pixel Ice Block Model Default |
| `models/features/pixel_wood_block_model_default.glb` | Original prefab `Pixel Wood Block Model Default` (7 mesh nodes) | Pixel Wood Block Model Default |
| `models/features/conveyor_door_feature.glb` | Original prefab `Conveyor Door Feature` (3 mesh nodes) | Conveyor Door Feature |
| `models/features/bean_box_model_square.glb` | Original prefab `Bean Box Model Square` (2 mesh nodes) | Bean Box Model Square |
| `models/features/slot_cage_feature.glb` | Original prefab `Slot Cage Feature` (5 mesh nodes) | Slot Cage Feature |
| `models/features/crossbow_feature.glb` | Original prefab `Crossbow Feature` (5 mesh nodes) | Crossbow Feature |
| `models/features/curtain_segment_model_7x4.glb` | Original prefab `Curtain Segment Model 7x4` (4 mesh nodes) | Curtain Segment Model 7x4 |
| `models/features/gate_feature.glb` | Original prefab `Gate Feature` (3 mesh nodes) | Gate Feature |
| `models/features/split_object_feature.glb` | Original prefab `Split Object Feature` (2 mesh nodes) | Split Object Feature |
| `models/features/bean_model.glb` | Original prefab `Bean Model` (1 mesh nodes) | Bean Model |
| `models/features/music_toy_segment_model_1x3.glb` | Original prefab `Music Toy Segment Model 1x3` (3 mesh nodes) | Music Toy Segment Model 1x3 |
| `models/features/music_toy_segment_model_1x2.glb` | Original prefab `Music Toy Segment Model 1x2` (3 mesh nodes) | Music Toy Segment Model 1x2 |
| `models/features/crossbow_arrow.glb` | Original prefab `Crossbow Arrow` (1 mesh nodes) | Crossbow Arrow |
| `models/features/chained_shooter_rope_chain_model.glb` | Original prefab `Chained Shooter Rope Chain Model` (1 mesh nodes) | Chained Shooter Rope Chain Model |
| `models/features/pixel_color_door_model_18x18.glb` | Original prefab `Pixel Color Door Model 18x18` (3 mesh nodes) | Pixel Color Door Model 18x18 |
| `models/features/pixel_color_door_model_14x14.glb` | Original prefab `Pixel Color Door Model 14x14` (3 mesh nodes) | Pixel Color Door Model 14x14 |
| `models/features/pixel_color_door_model_10x10.glb` | Original prefab `Pixel Color Door Model 10x10` (3 mesh nodes) | Pixel Color Door Model 10x10 |
| `models/features/pixel_color_door_model_12x10.glb` | Original prefab `Pixel Color Door Model 12x10` (3 mesh nodes) | Pixel Color Door Model 12x10 |
| `models/features/curtain_chain_link.glb` | Original prefab `Curtain Chain Link` (1 mesh nodes) | Curtain Chain Link |
| `models/features/ufo_seat_model.glb` | Original prefab `Ufo Seat Model` (2 mesh nodes) | Ufo Seat Model |
| `models/features/pumpkin_item_model.glb` | Original prefab `Pumpkin Item Model` (37 mesh nodes) | Pumpkin Item Model |
| `models/features/ufo_model_8x8.glb` | Original prefab `Ufo Model 8x8` (6 mesh nodes) | Ufo Model 8x8 |
| `models/features/music_toy_mallet_feature.glb` | Original prefab `Music Toy Mallet Feature` (1 mesh nodes) | Music Toy Mallet Feature |
| `models/features/pixel_mixer_feature.glb` | Original prefab `Pixel Mixer Feature` (10 mesh nodes) | Pixel Mixer Feature |
| `models/features/wall_model_4x2.glb` | Original prefab `Wall Model 4x2` (2 mesh nodes) | Wall Model 4x2 |
| `models/features/wall_model_2x1.glb` | Original prefab `Wall Model 2x1` (2 mesh nodes) | Wall Model 2x1 |
| `models/features/egg_box_model_6_2x3_variant.glb` | Original prefab `Egg Box Model 6 2x3 Variant` (13 mesh nodes) | Egg Box Model 6 2x3 Variant |
| `models/features/wall_model_2x2.glb` | Original prefab `Wall Model 2x2` (1 mesh nodes) | Wall Model 2x2 |
| `models/features/wall_model_3x3.glb` | Original prefab `Wall Model 3x3` (1 mesh nodes) | Wall Model 3x3 |
| `models/features/wall_model_1x1.glb` | Original prefab `Wall Model 1x1` (1 mesh nodes) | Wall Model 1x1 |
| `models/features/wall_model_6x3.glb` | Original prefab `Wall Model 6x3` (2 mesh nodes) | Wall Model 6x3 |
| `models/features/music_toy_feature.glb` | Original prefab `Music Toy Feature` (1 mesh nodes) | Music Toy Feature |
| `models/features/belt_starter_machine.glb` | New: `make_models.py` (`model_belt_starter_machine`), from the level reference frames and sized like the original's `Belt Start` piece; it exported with no mesh. Keeps its own colors, unlike the other face-less meshes | The block at the start of the belt |

## Sounds (original WAV converted to mono OGG by `art-src/convert_sounds.py`)

Left out, as spec section 9.2 says: the Race, Lava Quest and Cosmic Journey sounds, the car loops and the three original music loops.

| File | Source | Used for |
|---|---|---|
| `sounds/accordion_close_trimmed.ogg` | Original `sounds/accordion_close_trimmed.wav` | Misc feature or transition whoosh/impact |
| `sounds/arrow_whoosh_1_trimmed.ogg` | Original `sounds/arrow_whoosh_1_trimmed.wav` | Crossbow feature / arrow |
| `sounds/arrow_whoosh_3_trimmed.ogg` | Original `sounds/arrow_whoosh_3_trimmed.wav` | Crossbow feature / arrow |
| `sounds/bean_hit_thock.ogg` | Original `sounds/bean_hit_thock.wav` | Music toy / jelly beans / berry / biscuit / egg box features |
| `sounds/beans6.ogg` | Original `sounds/beans6.wav` | Music toy / jelly beans / berry / biscuit / egg box features |
| `sounds/berry_explode_2.ogg` | Original `sounds/berry_explode_2.wav` | Music toy / jelly beans / berry / biscuit / egg box features |
| `sounds/berry_swell.ogg` | Original `sounds/berry_swell.wav` | Music toy / jelly beans / berry / biscuit / egg box features |
| `sounds/biscuit_hit_no_click.ogg` | Original `sounds/biscuit_hit_no_click.wav` | Music toy / jelly beans / berry / biscuit / egg box features |
| `sounds/board_transition_03.ogg` | Original `sounds/board_transition_03.wav` | Misc feature or transition whoosh/impact |
| `sounds/bomb.ogg` | Original `sounds/Bomb.wav` | Misc feature or transition whoosh/impact |
| `sounds/bonus_poins.ogg` | Original `sounds/Bonus Poins.wav` | Coins, rewards, claim, purchase |
| `sounds/booster_appear.ogg` | Original `sounds/booster_appear.wav` | Booster / powerup / Super Unicorn / unlock |
| `sounds/booster_shooting.ogg` | Original `sounds/booster_shooting.wav` | Booster / powerup / Super Unicorn / unlock |
| `sounds/breath3.ogg` | Original `sounds/breath3.wav` | Misc feature or transition whoosh/impact |
| `sounds/button_tap_pop.ogg` | Original `sounds/Button_Tap_Pop.wav` | UI tap / click / pop |
| `sounds/click.ogg` | Original `sounds/Click.wav` | UI tap / click / pop |
| `sounds/coin_counting.ogg` | Original `sounds/coin_counting.wav` | Coins, rewards, claim, purchase |
| `sounds/coins_collect_several_at_once_001.ogg` | Original `sounds/coins_collect_several_at_once_001.wav` | Coins, rewards, claim, purchase |
| `sounds/compileendsound.ogg` | Original `sounds/CompileEndSound.wav` | Misc feature or transition whoosh/impact |
| `sounds/crossbow_appear_base.ogg` | Original `sounds/crossbow_appear_base.wav` | Crossbow feature / arrow |
| `sounds/crossbow_appear_crossbow.ogg` | Original `sounds/crossbow_appear_crossbow.wav` | Crossbow feature / arrow |
| `sounds/curtain_chain_2.ogg` | Original `sounds/curtain_chain_2.wav` | Curtain feature |
| `sounds/curtain_hit.ogg` | Original `sounds/curtain_hit.wav` | Curtain feature |
| `sounds/curtain_pull_1.ogg` | Original `sounds/curtain_pull_1.wav` | Curtain feature |
| `sounds/curtain_pull_2.ogg` | Original `sounds/curtain_pull_2.wav` | Curtain feature |
| `sounds/daily_bonus_claim.ogg` | Original `sounds/Daily Bonus Claim.wav` | Coins, rewards, claim, purchase |
| `sounds/disapper_trimmed.ogg` | Original `sounds/disapper_trimmed.wav` | Misc feature or transition whoosh/impact |
| `sounds/door_close.ogg` | Original `sounds/door_close.wav` | Door / conveyor door / slot cage |
| `sounds/egg_break_change_trimmed.ogg` | Original `sounds/Egg Break Change_trimmed.wav` | Music toy / jelly beans / berry / biscuit / egg box features |
| `sounds/egg_full_break_trimmed.ogg` | Original `sounds/Egg Full Break_trimmed.wav` | Music toy / jelly beans / berry / biscuit / egg box features |
| `sounds/endgame_win.ogg` | Original `sounds/endgame_win.wav` | Level win jingle |
| `sounds/esm_japanese_button_4_game_mobile_user_interface_tap_fx_sound.ogg` | Original `sounds/esm_japanese_button_4_game_mobile_user_interface_tap_fx_sound.wav` | UI tap / click / pop |
| `sounds/esm_magic_game_pack_a_punch_fantasy_cast_craft_mobile_app_special_touch_pickup.ogg` | Original `sounds/esm_magic_game_pack_a_punch_fantasy_cast_craft_mobile_app_special_touch_pickup.wav` | Booster / powerup / Super Unicorn / unlock |
| `sounds/esm_metal_pin_point_ui_button_hybrid_mobile_collect_special_power_up_buff.ogg` | Original `sounds/esm_metal_pin_point_ui_button_hybrid_mobile_collect_special_power_up_buff.wav` | SFX (unclear) |
| `sounds/etfx_shoot_energy04.ogg` | Original `sounds/etfx_shoot_energy04.wav` | Pig shot / pixel hit |
| `sounds/etfx_target_hit.ogg` | Original `sounds/etfx_target_hit.wav` | Pig shot / pixel hit |
| `sounds/final_break02.ogg` | Original `sounds/final_break02.wav` | Pixel grid breaking / cube pops / gem effects |
| `sounds/first_settle2_trimmed.ogg` | Original `sounds/first_settle2_trimmed.wav` | Misc feature or transition whoosh/impact |
| `sounds/game_over.ogg` | Original `sounds/Game Over.wav` | Level fail jingle / retry |
| `sounds/game_success.ogg` | Original `sounds/Game Success.wav` | Level win jingle |
| `sounds/gem_lift_off_02.ogg` | Original `sounds/gem_lift_off_02.wav` | Pixel grid breaking / cube pops / gem effects |
| `sounds/gem_settling_01_trimmed.ogg` | Original `sounds/gem_settling_01_trimmed.wav` | Pixel grid breaking / cube pops / gem effects |
| `sounds/gem_settling_sparkle.ogg` | Original `sounds/gem_settling_sparkle.wav` | Pixel grid breaking / cube pops / gem effects |
| `sounds/gem_settling_sparkle_trimmed.ogg` | Original `sounds/gem_settling_sparkle_trimmed.wav` | Pixel grid breaking / cube pops / gem effects |
| `sounds/general_1_trimmed.ogg` | Original `sounds/general_1_trimmed.wav` | Misc feature or transition whoosh/impact |
| `sounds/gma_magic_flame_of_light_03_641.ogg` | Original `sounds/gma_magic_flame_of_light_03_641.wav` | Booster / powerup / Super Unicorn / unlock |
| `sounds/gma_magic_pop_open_03_646.ogg` | Original `sounds/gma_magic_pop_open_03_646.wav` | Booster / powerup / Super Unicorn / unlock |
| `sounds/gma_metal_door_hatch_close_slam_05_663.ogg` | Original `sounds/gma_metal_door_hatch_close_slam_05_663.wav` | Door / conveyor door / slot cage |
| `sounds/golden_egg_break_change_trimmed.ogg` | Original `sounds/golden_egg_break_change_trimmed.wav` | Music toy / jelly beans / berry / biscuit / egg box features |
| `sounds/golden_egg_full_break_trimmed.ogg` | Original `sounds/golden_egg_full_break_trimmed.wav` | Music toy / jelly beans / berry / biscuit / egg box features |
| `sounds/grid_breaking_1.ogg` | Original `sounds/grid_breaking_1.wav` | Pixel grid breaking / cube pops / gem effects |
| `sounds/grid_breaking_2.ogg` | Original `sounds/grid_breaking_2.wav` | Pixel grid breaking / cube pops / gem effects |
| `sounds/grid_breaking_6.ogg` | Original `sounds/grid_breaking_6.wav` | Pixel grid breaking / cube pops / gem effects |
| `sounds/grid_breaking_7.ogg` | Original `sounds/grid_breaking_7.wav` | Pixel grid breaking / cube pops / gem effects |
| `sounds/hit_05.ogg` | Original `sounds/hit_05.wav` | Pig shot / pixel hit |
| `sounds/ice_break_14765_trimmed.ogg` | Original `sounds/ice-break-14765_trimmed.wav` | Ice block / frozen pig shatter |
| `sounds/ice_break_14765_trimmed_trimmed.ogg` | Original `sounds/ice-break-14765_trimmed_trimmed.wav` | Ice block / frozen pig shatter |
| `sounds/ice_shatter_trimmed.ogg` | Original `sounds/ice-shatter_trimmed.wav` | Ice block / frozen pig shatter |
| `sounds/ice_shatter_3.ogg` | Original `sounds/ice_shatter_3.wav` | Ice block / frozen pig shatter |
| `sounds/industrial_impacts_hammer_wood_fixed_beam_002_trimmed_trimmed.ogg` | Original `sounds/industrial_impacts_hammer_wood_fixed_beam_002_trimmed_trimmed.wav` | Hammer / wood block feature |
| `sounds/ivy_whoosh_close.ogg` | Original `sounds/ivy_whoosh_close.wav` | Misc feature or transition whoosh/impact |
| `sounds/ivy_whoosh_open.ogg` | Original `sounds/ivy_whoosh_open.wav` | Misc feature or transition whoosh/impact |
| `sounds/machine_off.ogg` | Original `sounds/machine_off.wav` | Misc feature or transition whoosh/impact |
| `sounds/matryoshka_open1_trimmed.ogg` | Original `sounds/Matryoshka_open1_trimmed.wav` | Matryoshka (Pigroshka) feature |
| `sounds/matryoshka_open2_trimmed_hit.ogg` | Original `sounds/Matryoshka_open2_trimmed_hit.wav` | Matryoshka (Pigroshka) feature |
| `sounds/metal_hit.ogg` | Original `sounds/metal_hit.wav` | Pig shot / pixel hit |
| `sounds/mission_chest_open.ogg` | Original `sounds/Mission chest_open.wav` | Coins, rewards, claim, purchase |
| `sounds/mission_gem_impact.ogg` | Original `sounds/Mission Gem Impact.wav` | Coins, rewards, claim, purchase |
| `sounds/music_toy_collapse.ogg` | Original `sounds/music_toy_collapse.wav` | Music toy / jelly beans / berry / biscuit / egg box features |
| `sounds/old_creaky_wood_floor_stairs_footstep_fast_3_pm_owf_3611.ogg` | Original `sounds/Old_Creaky_Wood_Floor_Stairs_Footstep_Fast_3_PM_OWF_3611.wav` | Hammer / wood block feature |
| `sounds/opening_metal_slide2.ogg` | Original `sounds/opening_metal_slide2.wav` | Door / conveyor door / slot cage |
| `sounds/pass_1_trimmed.ogg` | Original `sounds/pass_1_trimmed.wav` | Misc feature or transition whoosh/impact |
| `sounds/pig2_trimmed.ogg` | Original `sounds/pig2_trimmed.wav` | Pig sound (squeal / tap) |
| `sounds/pig3_trimmed.ogg` | Original `sounds/pig3_trimmed.wav` | Pig sound (squeal / tap) |
| `sounds/pixel_packer_engine_03.ogg` | Original `sounds/pixel_packer_engine_03.wav` | Pixel grid breaking / cube pops / gem effects |
| `sounds/pm_feethmn_footstep_ice_crunch_crack_break_pmsfx_ssni_2432_trimmed.ogg` | Original `sounds/PM_FEETHmn_footstep_ice_crunch_crack_break_PMSFX_SSNI_2432_trimmed.wav` | Ice block / frozen pig shatter |
| `sounds/pm_fssf_door_mid_3.ogg` | Original `sounds/pm_fssf_door_mid_3.wav` | Door / conveyor door / slot cage |
| `sounds/pm_fssf_door_mid_7.ogg` | Original `sounds/pm_fssf_door_mid_7.wav` | Door / conveyor door / slot cage |
| `sounds/pop2.ogg` | Original `sounds/pop2.wav` | UI tap / click / pop |
| `sounds/pop_sparkle.ogg` | Original `sounds/pop_sparkle.wav` | Booster / powerup / Super Unicorn / unlock |
| `sounds/preview_3__trimmed.ogg` | Original `sounds/preview (3)_trimmed.wav` | Misc feature or transition whoosh/impact |
| `sounds/preview_5__e__minor__bpm_61_trimmed.ogg` | Original `sounds/preview (5)_E♭_minor__bpm_61_trimmed.wav` | Misc feature or transition whoosh/impact |
| `sounds/pull_01.ogg` | Original `sounds/pull_01.wav` | Shackles / chains / pulling |
| `sounds/pull_02.ogg` | Original `sounds/pull_02.wav` | Shackles / chains / pulling |
| `sounds/pulley_01_trimmed.ogg` | Original `sounds/pulley_01_trimmed.wav` | Shackles / chains / pulling |
| `sounds/pumpkin_break1_trimmed.ogg` | Original `sounds/pumpkin_break1_trimmed.wav` | Pumpkin feature |
| `sounds/pumpkin_break3_trimmed.ogg` | Original `sounds/pumpkin_break3_trimmed.wav` | Pumpkin feature |
| `sounds/pumpkin_death_trimmed.ogg` | Original `sounds/pumpkin_death_trimmed.wav` | Pumpkin feature |
| `sounds/pumpkin_emerge_start_trimmed.ogg` | Original `sounds/pumpkin_emerge_start_trimmed.wav` | Pumpkin feature |
| `sounds/pumpkin_emerge_trimmed.ogg` | Original `sounds/pumpkin_emerge_trimmed.wav` | Pumpkin feature |
| `sounds/pumpkin_hit_trimmed.ogg` | Original `sounds/pumpkin_hit_trimmed.wav` | Pumpkin feature |
| `sounds/pumpkin_light_up_trimmed.ogg` | Original `sounds/pumpkin_light_up_trimmed.wav` | Pumpkin feature |
| `sounds/purchase.ogg` | Original `sounds/Purchase.wav` | Coins, rewards, claim, purchase |
| `sounds/raise_03_trimmed.ogg` | Original `sounds/raise_03_trimmed.wav` | Booster / powerup / Super Unicorn / unlock |
| `sounds/raise_05_trimmed.ogg` | Original `sounds/raise_05_trimmed.wav` | Booster / powerup / Super Unicorn / unlock |
| `sounds/rocket_boost.ogg` | Original `sounds/rocket_boost.wav` | Rocket feature (windup, launch, merge, hit) |
| `sounds/rocket_hit.ogg` | Original `sounds/rocket_hit.wav` | Rocket feature (windup, launch, merge, hit) |
| `sounds/rocket_hit_fire.ogg` | Original `sounds/rocket_hit_fire.wav` | Rocket feature (windup, launch, merge, hit) |
| `sounds/rocket_launch1.ogg` | Original `sounds/rocket_launch1.wav` | Rocket feature (windup, launch, merge, hit) |
| `sounds/rocket_launch_windup_1.ogg` | Original `sounds/rocket_launch_windup_1.wav` | Rocket feature (windup, launch, merge, hit) |
| `sounds/rocket_lift_off_trimmed.ogg` | Original `sounds/rocket_lift_off_trimmed.wav` | Rocket feature (windup, launch, merge, hit) |
| `sounds/rocket_merge.ogg` | Original `sounds/rocket_merge.wav` | Rocket feature (windup, launch, merge, hit) |
| `sounds/rocket_opening1.ogg` | Original `sounds/rocket_opening1.wav` | Rocket feature (windup, launch, merge, hit) |
| `sounds/rope_stress_trimmed.ogg` | Original `sounds/rope_stress_trimmed.wav` | Shackles / chains / pulling |
| `sounds/selection.ogg` | Original `sounds/Selection.wav` | UI tap / click / pop |
| `sounds/shackles_break_trimmed.ogg` | Original `sounds/shackles_break_trimmed.wav` | Shackles / chains / pulling |
| `sounds/shackles_shrink_grow_2.ogg` | Original `sounds/shackles_shrink_grow_2.wav` | Shackles / chains / pulling |
| `sounds/shoot_hit.ogg` | Original `sounds/Shoot Hit.wav` | Pig shot / pixel hit |
| `sounds/shoot_foley_wood_thick_dense.ogg` | Original `sounds/Shoot_foley_wood_thick_dense.wav` | Pig shot / pixel hit |
| `sounds/shoot_whoosh_04_trimmed.ogg` | Original `sounds/shoot_whoosh_04_trimmed.wav` | Pig shot / pixel hit |
| `sounds/slot_blocker_first_anim4.ogg` | Original `sounds/slot_blocker_first_anim4.wav` | Misc feature or transition whoosh/impact |
| `sounds/sparkle1.ogg` | Original `sounds/sparkle1.wav` | Booster / powerup / Super Unicorn / unlock |
| `sounds/sport_baseball_bat_foam_swipe_001.ogg` | Original `sounds/sport_baseball_bat_foam_swipe_001.wav` | Hammer / wood block feature |
| `sounds/stagebreak3.ogg` | Original `sounds/StageBreak3.wav` | Pixel grid breaking / cube pops / gem effects |
| `sounds/tap_cartoon_pop_mouth_002.ogg` | Original `sounds/Tap_cartoon_pop_mouth_002.wav` | UI tap / click / pop |
| `sounds/tap_cartoon_pop_mouth_009_trimmed.ogg` | Original `sounds/Tap_cartoon_pop_mouth_009_trimmed.wav` | UI tap / click / pop |
| `sounds/tonal_click.ogg` | Original `sounds/Tonal Click.wav` | UI tap / click / pop |
| `sounds/totem_appears_trimmed.ogg` | Original `sounds/totem_appears_trimmed.wav` | Bull totem |
| `sounds/totem_destroy_trimmed.ogg` | Original `sounds/totem_destroy_trimmed.wav` | Bull totem |
| `sounds/try_again.ogg` | Original `sounds/Try Again.wav` | Level fail jingle / retry |
| `sounds/unicorn_button_ready.ogg` | Original `sounds/unicorn_button_ready.wav` | Booster / powerup / Super Unicorn / unlock |
| `sounds/unicorn_exit_trimmed.ogg` | Original `sounds/unicorn_exit_trimmed.wav` | Booster / powerup / Super Unicorn / unlock |
| `sounds/unlock.ogg` | Original `sounds/Unlock.wav` | Booster / powerup / Super Unicorn / unlock |
| `sounds/whoosh2_gem.ogg` | Original `sounds/whoosh2_gem.wav` | Pixel grid breaking / cube pops / gem effects |
| `sounds/wood_stage1.ogg` | Original `sounds/wood_stage1.wav` | Hammer / wood block feature |
| `sounds/wood_stage2.ogg` | Original `sounds/wood_stage2.wav` | Hammer / wood block feature |
| `sounds/x_1_trimmed.ogg` | Original `sounds/x_1_trimmed.wav` | UI tap / click / pop |
| `sounds/x_2_trimmed.ogg` | Original `sounds/x_2_trimmed.wav` | UI tap / click / pop |
| `sounds/x_3_trimmed.ogg` | Original `sounds/x_3_trimmed.wav` | UI tap / click / pop |
| `sounds/x_4_trimmed.ogg` | Original `sounds/x_4_trimmed.wav` | UI tap / click / pop |
| `sounds/x_5_trimmed.ogg` | Original `sounds/x_5_trimmed.wav` | UI tap / click / pop |
| `sounds/x_6_trimmed.ogg` | Original `sounds/x_6_trimmed.wav` | UI tap / click / pop |
| `sounds/x_7_trimmed.ogg` | Original `sounds/x_7_trimmed.wav` | UI tap / click / pop |
| `sounds/x_8_trimmed.ogg` | Original `sounds/x_8_trimmed.wav` | UI tap / click / pop |
| `sounds/zapsplat_cartoon_bird_poop_hit_surface_splat_squelch_008_74097_trimmed.ogg` | Original `sounds/zapsplat_cartoon_bird_poop_hit_surface_splat_squelch_008_74097_trimmed.wav` | Foley for UFO / Pixel Mixer / seat features |
| `sounds/zapsplat_foley_metal_small_chain_drag_short_concrete_ground_10425.ogg` | Original `sounds/zapsplat_foley_metal_small_chain_drag_short_concrete_ground_10425.wav` | Shackles / chains / pulling |
| `sounds/zapsplat_household_door_wooden_trimmed.ogg` | Original `sounds/zapsplat_household_door_wooden_trimmed.wav` | Door / conveyor door / slot cage |
| `sounds/zapsplat_household_vacuum_cleaner_set_trimmed.ogg` | Original `sounds/zapsplat_household_vacuum_cleaner_set_trimmed.wav` | Foley for UFO / Pixel Mixer / seat features |
| `sounds/zapsplat_science_fiction_spacecraft_fighter_zoom_by_ultra_fast_004_84010.ogg` | Original `sounds/zapsplat_science_fiction_spacecraft_fighter_zoom_by_ultra_fast_004_84010.wav` | Misc feature or transition whoosh/impact |
| `sounds/zapsplat_vehicles_car_seatbelt_safety_belt_click_lock_into_place_003_83839_trimmed.ogg` | Original `sounds/zapsplat_vehicles_car_seatbelt_safety_belt_click_lock_into_place_003_83839_trimmed.wav` | Foley for UFO / Pixel Mixer / seat features |
