#!/usr/bin/env python
"""
Bot Arena - Battle Runner

Standalone script that runs a battle and renders it to video.
This is designed to be called from a subprocess to avoid blocking the Discord bot.

Usage:
    python battle_runner.py <input_json> <output_path> [--format=gif|mp4]

Input JSON format:
{
    "config": {
        "arena_width": 1000,
        "arena_height": 1000,
        "fps": 30,
        "max_duration": 120.0,
        "scale": 0.5
    },
    "team1": [
        {
            "id": "uuid",
            "name": "Bot Name",
            "chassis": {...},
            "plating": {...},
            "component": {...}
        }
    ],
    "team2": [...]
}

Output: Creates video file and prints JSON result to stdout
"""

import argparse
import json
import sys
from pathlib import Path

# Add the botarena directory itself to path so we can import submodules directly
# WITHOUT going through botarena/__init__.py (which imports redbot and causes circular imports)
_THIS_DIR = Path(__file__).parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

# Import directly from submodules to avoid botarena/__init__.py
# This prevents circular imports when running as a standalone subprocess
from common.engine import AIBehavior, BattleConfig, BattleEngine, TargetPriority  # noqa
from common.renderer import BattleRenderer  # noqa
from constants.parts import build_registry  # noqa


def run_battle_from_json(input_data: dict, output_path: str, format: str = "gif") -> dict:
    """
    Run a battle from JSON input and render to file.

    Args:
        input_data: Battle configuration and bot data
        output_path: Where to save the video
        format: "gif" or "mp4"

    Returns:
        Battle result dict (without frame data for smaller output)
    """
    # Build parts registry for rendering
    parts_registry = build_registry()

    # Parse config
    config_data = input_data.get("config", {})
    config = BattleConfig(
        arena_width=config_data.get("arena_width", 1000),
        arena_height=config_data.get("arena_height", 1000),
        fps=config_data.get("fps", 30),
        max_duration=config_data.get("max_duration", 60.0),
    )

    # Create engine
    engine = BattleEngine(config)

    # Add team 1 bots
    for bot_data in input_data.get("team1", []):
        _add_bot_from_data(engine, bot_data, team=1)

    # Add team 2 bots
    for bot_data in input_data.get("team2", []):
        _add_bot_from_data(engine, bot_data, team=2)

    # Run simulation
    result = engine.run()

    # Render video with team colors
    scale = config_data.get("scale", 0.5)
    team1_color = config_data.get("team1_color", "blue")
    team2_color = config_data.get("team2_color", "red")
    chapter = config_data.get("chapter")  # Campaign chapter for arena background
    mission_id = config_data.get("mission_id")  # Mission ID for mission-specific arena
    renderer = BattleRenderer(
        width=config.arena_width,
        height=config.arena_height,
        scale=scale,
        fps=config.fps,
        team1_color=team1_color,
        team2_color=team2_color,
        parts_registry=parts_registry,
        chapter=chapter,
        mission_id=mission_id,
    )

    output_path = Path(output_path)
    if format == "gif":
        # For GIF, skip frames to keep size manageable
        frame_skip = max(1, config.fps // 15)  # Target ~15 fps for GIF
        renderer.render_to_gif(result, output_path, frame_skip=frame_skip, show_progress=True)
    else:
        # Try MP4, fall back to GIF if ffmpeg not available
        try:
            renderer.render_to_video(result, output_path, show_progress=True)
        except (RuntimeError, FileNotFoundError) as e:
            # ffmpeg not available, fall back to GIF
            print(f"MP4 rendering failed ({e}), falling back to GIF", file=sys.stderr)
            gif_path = Path(output_path).with_suffix(".gif")
            frame_skip = max(1, config.fps // 15)
            renderer.render_to_gif(result, gif_path, frame_skip=frame_skip, show_progress=True)
            output_path = str(gif_path)

    # Return result without frames (too large)
    return {
        "winner_team": result["winner_team"],
        "total_frames": result["total_frames"],
        "duration": result["duration"],
        "team1_survivors": result["team1_survivors"],
        "team2_survivors": result["team2_survivors"],
        "bot_stats": result["bot_stats"],
        "output_path": str(output_path),
    }


def _add_bot_from_data(engine: BattleEngine, bot_data: dict, team: int):
    """Add a bot to the engine from JSON data"""
    chassis = bot_data.get("chassis", {})
    plating = bot_data.get("plating", {})
    component = bot_data.get("component", {})

    # Extract tactical orders if present (handle None case)
    tactical_orders = bot_data.get("tactical_orders") or {}

    # Map movement stance to AI behavior (1:1 mapping now - 3 behaviors)
    movement_stance = tactical_orders.get("movement_stance", "aggressive")
    behavior_str = movement_stance  # Direct mapping - aggressive, defensive, tactical

    # Get the AIBehavior enum
    behavior = None
    for member in AIBehavior:
        if member.value == behavior_str:
            behavior = member
            break
    # Default to TACTICAL if not found
    if behavior is None:
        behavior = AIBehavior.TACTICAL

    # Get target priority (simplified to 3 options, default to CLOSEST for invalid values)
    target_priority_str = tactical_orders.get("target_priority", "closest")
    target_priority = None
    for member in TargetPriority:
        if member.value == target_priority_str:
            target_priority = member
            break
    # Default to CLOSEST if not found (handles legacy strongest/furthest values)
    if target_priority is None:
        target_priority = TargetPriority.CLOSEST

    engine.add_bot(
        bot_id=bot_data.get("id", ""),
        bot_name=bot_data.get("name", "Bot"),
        team=team,
        chassis_name=chassis.get("name", "Unknown"),
        plating_name=plating.get("name", "Unknown"),
        component_name=component.get("name", "Unknown"),
        max_health=chassis.get("shielding", 0) + plating.get("shielding", 0),
        speed=chassis.get("speed", 10),
        rotation_speed=chassis.get("rotation_speed", 5),
        intelligence=chassis.get("intelligence", 5),
        damage_per_shot=component.get("damage_per_shot", 10),
        shots_per_minute=component.get("shots_per_minute", 60),
        min_range=component.get("min_range", 0),
        max_range=component.get("max_range", 200),
        is_healer=component.get("damage_per_shot", 0) < 0,
        agility=chassis.get("agility", 0.5),
        behavior=behavior,
        target_priority=target_priority,
        projectile_type=component.get("projectile_type", "bullet"),
        muzzle_offset=component.get("render_offset_x", 92.0),  # Use weapon's render offset as muzzle position
        turret_rotation_speed=chassis.get("turret_rotation_speed", 20.0),  # Turret rotation determined by chassis
    )


def main():
    parser = argparse.ArgumentParser(description="Run a Bot Arena battle and render video")
    parser.add_argument("input", help="Path to input JSON file")
    parser.add_argument("output", help="Path to output video file")
    parser.add_argument(
        "--format",
        choices=["gif", "mp4"],
        default="gif",
        help="Output format (default: gif)",
    )

    args = parser.parse_args()

    # Read input
    input_path = Path(args.input)
    if not input_path.exists():
        print(json.dumps({"error": f"Input file not found: {args.input}"}))
        sys.exit(1)

    try:
        input_data = json.loads(input_path.read_text())
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}))
        sys.exit(1)

    # Run battle
    try:
        result = run_battle_from_json(input_data, args.output, args.format)
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
