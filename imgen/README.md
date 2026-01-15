# ImGen

Create and edit images with OpenAI's GPT-Image models.

## Features

- **AI Image Generation**: Generate images from text prompts using OpenAI's latest GPT-Image models
- **Reference-Based Generation**: Include reference images to guide the generation
- **Turn-Based Editing**: Iteratively refine generated images with an "Edit" button
- **Context Menu Editing**: Right-click any message with an image to edit it with AI
- **Per-Server Configuration**: Each server has its own API key and settings
- **Role-Based Access Control**: Restrict image generation to specific roles with configurable cooldowns
- **Generation Logging**: Log all generations to a designated channel

## Commands

### User Commands

| Command | Description |
|---------|-------------|
| `/makeimage` | Generate an image from a text prompt with optional reference images |
| `/editimage` | Edit an existing image using AI |
| `Edit Image` (context menu) | Right-click a message → Apps → Edit Image |

### Admin Commands (`/imgen`)

| Command | Description |
|---------|-------------|
| `/imgen view` | View current ImGen settings |
| `/imgen api` | Set the OpenAI API key for this server |
| `/imgen clearapi` | Remove the OpenAI API key |
| `/imgen logchannel [channel]` | Set or clear the logging channel |
| `/imgen access` | Open the role access manager |
| `/imgen clearroles` | Clear all role restrictions (open access) |
| `/imgen defaults` | Set default model, size, and quality settings |

## Setup

1. **Install the cog**:
   ```
   [p]cog install vrt-cogs imgen
   ```

2. **Load the cog**:
   ```
   [p]load imgen
   ```

3. **Set your OpenAI API key**:
   - Run `/imgen api` and click the button to enter your key
   - Get an API key from [OpenAI Platform](https://platform.openai.com/api-keys)

4. **(Optional) Configure access control**:
   - By default, anyone can use image generation
   - Use `/imgen access` to restrict access to specific roles with cooldowns and model/size/quality limits

## Models

ImGen supports the following GPT-Image models:

| Model | Description |
|-------|-------------|
| `gpt-image-1` | Standard GPT-Image model (default) |
| `gpt-image-1.5` | Newer GPT-Image model with improvements |
| `gpt-image-1-mini` | Faster, more economical variant |

## Size Options

| Size | Aspect Ratio |
|------|--------------|
| `auto` | Automatically determined (default) |
| `1024x1024` | Square |
| `1536x1024` | Landscape |
| `1024x1536` | Portrait |

## Quality Options

| Quality | Description |
|---------|-------------|
| `auto` | Automatically determined (default) |
| `low` | Faster generation, lower quality |
| `medium` | Balanced quality and speed |
| `high` | Best quality, slower generation |

## Turn-Based Editing

After generating an image, click the **✏️ Edit** button to open a modal where you can:
1. Enter a new prompt describing the desired changes
2. Optionally adjust the size and quality
3. Submit to generate an edited version

The edit uses OpenAI's turn-based conversation feature, which maintains context from the original generation for more coherent edits.

## Access Control

ImGen uses a role-based access system:

- **No roles configured**: Everyone can use image generation
- **Roles configured**: Only users with at least one allowed role can generate images
- **Cooldowns**: Each role can have a cooldown (in seconds) between generations
  - If a user has multiple allowed roles, the shortest cooldown applies
 - **Model/Size/Quality Access**: Each role can restrict which models, sizes, and quality levels are available
    - If any restrictions are set for size or quality, `auto` is no longer available

## Logging

Enable generation logging to track usage:

```
/imgen logchannel #your-log-channel
```

Each generation will log:
- The user who requested it
- The prompt used
- Model, size, and quality settings
- A link to the generated image

## Requirements

- Python 3.11+
- Red-DiscordBot 3.5+
- OpenAI API key with access to GPT-Image models
- `openai` Python package
- `pydantic` Python package (v2.11+)
