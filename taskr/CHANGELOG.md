# Taskr Changelog

## v1.0.20

- **Fix**: A task whose command can't be found is no longer disabled on its first miss. It skips the run and keeps its schedule, and is only disabled (with the usual modlog notice) once the command has been missing for 24 hours. This replaces the 15 minute startup window from v1.0.19, and a cog being reloaded or stuck no longer switches tasks off. The 24 hours keep counting across bot restarts, and the count resets when the command comes back or the task is turned back on.

## v1.0.19

- **Fix**: For the first 15 minutes after the cog loads, a task whose command isn't registered yet (another cog still starting up after a restart) skips that run instead of being disabled.
- **Change**: When a task is disabled because its command can't be found or its author fails the command's permission checks, the reason is posted to the server's modlog.

## v1.0.18

- **Change**: The AI helper now uses OpenAI's gpt-6-luna model instead of gpt-5-mini.

## v1.0.17

- **Fix**: The task menu's toggle button now reads "Task is ON" / "Task is OFF" instead of just "On" / "Off", so it shows the task's state instead of looking like an action.
