# ImGen

Create and edit images with OpenAI's GPT-Image models.<br/><br/>Generate images from text prompts or edit existing images using AI.<br/>Supports turn-based editing where you can iteratively refine images.

## /makeimage (Slash Command)

Generate an image from a text prompt<br/>

 - Usage: `/makeimage <prompt> [model] [size] [quality] [output_format]`
 - `prompt:` (Required) Describe the image you want to generate
 - `model:` (Optional) The model to use for generation
 - `size:` (Optional) Size of the generated image
 - `quality:` (Optional) Quality level of the image
 - `output_format:` (Optional) Output image format

 - Checks: `Server Only`

## /editimage (Slash Command)

Edit an existing image using AI<br/>

 - Usage: `/editimage <prompt> <image> [image2] [image3] [model] [size] [quality] [output_format]`
 - `prompt:` (Required) Describe how you want to modify the image
 - `image:` (Required) The main image to edit (required)
 - `image2:` (Optional) Additional reference image (optional)
 - `image3:` (Optional) Additional reference image (optional)
 - `model:` (Optional) The model to use for editing
 - `size:` (Optional) Size of the output image
 - `quality:` (Optional) Quality level of the image
 - `output_format:` (Optional) Output image format

 - Checks: `Server Only`

## [p]imgen

Configure ImGen settings<br/>

 - Usage: `[p]imgen`

### /imgen view (Slash Command)

View current ImGen settings<br/>

 - Usage: `/imgen view`

### /imgen access (Slash Command)

Manage role-based access rules<br/>

 - Usage: `/imgen access`

### /imgen api (Slash Command)

Set the OpenAI API key for this server<br/>

 - Usage: `/imgen api`

### /imgen clearapi (Slash Command)

Remove the OpenAI API key for this server<br/>

 - Usage: `/imgen clearapi`

### /imgen logchannel (Slash Command)

Set or clear the logging channel<br/>

 - Usage: `/imgen logchannel [channel]`
 - `channel:` (Optional) The channel to log generations to (leave empty to disable)

### /imgen clearroles (Slash Command)

Clear all role restrictions (open access)<br/>

 - Usage: `/imgen clearroles`

### /imgen defaults (Slash Command)

Set default generation settings<br/>

 - Usage: `/imgen defaults [model] [size] [quality]`
 - `model:` (Optional) Default model for generation
 - `size:` (Optional) Default image size
 - `quality:` (Optional) Default image quality

### /imgen tiers (Slash Command)

View available subscription tier presets<br/>

 - Usage: `/imgen tiers`

### /imgen tier (Slash Command)

Apply a subscription tier preset to a role<br/>

 - Usage: `/imgen tier <role> <tier>`
 - `role:` (Required) The role to configure
 - `tier:` (Required) The tier preset to apply

