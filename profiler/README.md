# Profiler Help

Cog profiling tools for bot owners and developers<br/><br/>This cog provides tools to profile the performance of other cogs' commands, methods, tasks, and listeners.<br/><br/>By default, metrics are not stored persistently and are only kept for 1 hour in memory. You can change these settings with the `[p]profiler` base command.

# profiler

- Usage: `[p]profiler`
- Restricted to: `BOT_OWNER`

Profiling commands

## profiler verbose

- Usage: `[p]profiler verbose`

Toggle verbose stats

## profiler attach

- Usage: `[p]profiler attach <cogs>`

Attach a profiler to a cog

## profiler view

- Usage: `[p]profiler view`
- Aliases: `v`

View a menu of the current stats

## profiler settings

- Usage: `[p]profiler settings`

View the current profiler settings

## profiler memory

- Usage: `[p]profiler memory [limit=15]`
- Aliases: `mem and m`

Profile memory usage of objects in the current environment

## profiler methods

- Usage: `[p]profiler methods`
- Aliases: `list`

List all available methods that can be tracked<br/><br/>Sends a text file containing all trackable methods organized by cog. Useful for finding specific methods to profile without attaching to entire cogs.

## profiler save

- Usage: `[p]profiler save`

Toggle saving stats persistently<br/><br/>**Warning**: The config size can grow very large if this is enabled for a long time

## profiler delta

- Usage: `[p]profiler delta <delta>`

Set the data retention period in hours

## profiler detach

- Usage: `[p]profiler detach <cogs>`

Remove a cog from the profiling list<br/><br/>This will remove all collected stats for this cog from the config
