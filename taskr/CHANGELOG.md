# Taskr Changelog

## v1.0.19

- **Fix**: For the first 15 minutes after the cog loads, a task whose command isn't registered yet (another cog still starting up after a restart) skips that run instead of being disabled.
- **Change**: When a task is disabled because its command can't be found or its author fails the command's permission checks, the reason is posted to the server's modlog.

## v1.0.18

- **Change**: The AI helper now uses OpenAI's gpt-6-luna model instead of gpt-5-mini.

## v1.0.17

- **Fix**: The task menu's toggle button now reads "Task is ON" / "Task is OFF" instead of just "On" / "Off", so it shows the task's state instead of looking like an action.
