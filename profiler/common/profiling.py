import asyncio
import logging
from datetime import datetime, timedelta

from discord import app_commands
from discord.ext import tasks
from redbot.core import commands

from ..abc import MixinMeta
from .models import Method

log = logging.getLogger("red.vrt.profiler.profiling")


class Profiling(MixinMeta):
    def attach_method(self, method_key: str) -> bool:
        """Attach a profiler to a specific method.

        Args:
            method_key (str): The key of the method to attach the profiler to.

        Returns:
            True if attached successfully, False otherwise.
        """
        method = self.methods.get(method_key)
        if not method:
            log.warning(f"{method_key} method not found. Cant track method.")
            return False
        cog = self.bot.get_cog(method.cog_name)
        if not cog:
            log.warning(f"{method.cog_name} cog not found. Cant track {method_key} method.")
            return False
        if method.func_type == "method":
            original_method = getattr(cog, method_key.split(".")[-1], None)
            if not original_method:
                log.warning(f"{method_key} not found in {method.cog_name} cog.")
                return False
            wrapped_fn = self.profile_wrapper(original_method, method.cog_name, method.func_type)
            setattr(cog, method_key.split(".")[-1], wrapped_fn)
            self.original_methods.setdefault(method.cog_name, {})[method_key.split(".")[-1]] = original_method
        elif method.func_type in ["command", "hybrid"] and method.command_name:
            command = self.bot.get_command(method.command_name)
            if not command:
                log.warning(f"{method_key} not found in {method.cog_name} cog.")
                return False
            original_callback = command.callback
            wrapped_callback = self.profile_wrapper(original_callback, method.cog_name, method.func_type)
            command.callback = wrapped_callback
            self.original_callbacks.setdefault(method.cog_name, {})[command.qualified_name] = original_callback
        elif method.func_type == "slash":
            command: app_commands.Command = getattr(cog, method_key.split(".")[-1], None)
            if not command:
                log.warning(f"{method_key} not found in {method.cog_name} cog.")
                return False
            original_callback = command.callback
            wrapped_callback = self.profile_wrapper(original_callback, method.cog_name, method.func_type)
            setattr(command, "_callback", wrapped_callback)
            self.original_slash_callbacks.setdefault(method.cog_name, {})[command.qualified_name] = original_callback
        elif method.func_type == "task":
            loop: tasks.Loop = getattr(cog, method_key.split(".")[-1], None)
            if not loop:
                log.warning(f"{method_key} not found in {method.cog_name} cog.")
                return False
            original_coro = loop.coro
            wrapped_coro = self.profile_wrapper(original_coro, method.cog_name, method.func_type)
            loop.coro = wrapped_coro
            self.original_loops.setdefault(method.cog_name, {})[method_key.split(".")[-1]] = original_coro
        elif method.func_type == "listener":
            for listener_name, listener_coro in cog.get_listeners():
                if f"{listener_coro.__module__}.{listener_coro.__name__}" == method_key:
                    break
            else:
                log.warning(f"{method_key} not found in {method.cog_name} cog.")
                return False
            wrapped_coro = self.profile_wrapper(listener_coro, method.cog_name, method.func_type)
            self.original_listeners.setdefault(method.cog_name, {})[listener_name] = (listener_coro, wrapped_coro)
            self.bot.remove_listener(listener_coro, name=listener_name)
            self.bot.add_listener(wrapped_coro, name=listener_name)
        else:
            raise ValueError(f"Invalid method type: {method.func_type}")
        return True

    def attach_cog(self, cog_name: str) -> bool:
        """Attach a profiler to the methods of a specified cog.

        Args:
            cog_name (str): The name of the cog to attach the profiler to.

        Returns:
            True if attached successfully, False otherwise.
        """
        cog: commands.Cog = self.bot.get_cog(cog_name)
        if not cog:
            return False

        used_keys = []

        attached = False
        # Attach the profiler to the commands of the cog
        if self.db.track_commands:
            for command in cog.walk_commands():
                if not command.enabled:
                    continue
                key = f"{command.callback.__module__}.{command.callback.__name__}"
                log.debug(f"Attaching profiler to COMMAND {key}")

                used_keys.append(key)

                original_callback = command.callback
                wrapped_callback = self.profile_wrapper(original_callback, cog_name, "command")
                command.callback = wrapped_callback
                self.original_callbacks.setdefault(cog_name, {})[command.qualified_name] = original_callback
                attached = True

            for command in cog.walk_app_commands():
                if isinstance(command, app_commands.Group):
                    continue
                key = f"{command.callback.__module__}.{command.callback.__name__}"
                log.debug(f"Attaching profiler to SLASH COMMAND {key}")

                used_keys.append(key)

                original_callback = command.callback
                wrapped_callback = self.profile_wrapper(original_callback, cog_name, "slash")

                setattr(command, "_callback", wrapped_callback)
                self.original_slash_callbacks.setdefault(cog_name, {})[command.qualified_name] = original_callback
                attached = True

        # Attach the profiler to the listeners of the cog
        if self.db.track_listeners:
            for listener_name, listener_coro in cog.get_listeners():
                if listener_coro.__qualname__.split(".")[0] != cog_name:
                    continue

                key = f"{listener_coro.__module__}.{listener_coro.__name__}"
                log.debug(f"Attaching profiler to LISTENER {key}")

                used_keys.append(key)

                wrapped_coro = self.profile_wrapper(listener_coro, cog_name, "listener")

                self.original_listeners.setdefault(cog_name, {})[listener_name] = (listener_coro, wrapped_coro)
                self.bot.remove_listener(listener_coro, name=listener_name)
                self.bot.add_listener(wrapped_coro, name=listener_name)

                attached = True

        # Attach the profiler to the methods of the cog
        if self.db.track_methods:
            for attr_name in dir(cog):
                attr = getattr(cog, attr_name, None)
                if any(
                    [
                        attr_name in [i for i in dir(self)],
                        attr is None,
                        not hasattr(attr, "__module__"),  # Skip builtins
                        not callable(attr),  # Skip non-callable attributes
                        attr_name.startswith("__"),  # Skip dunder methods
                        getattr(attr, "__cog_listener__", None) is not None,  # Skip listeners
                    ]
                ):
                    continue

                key = f"{attr.__module__}.{attr_name}"
                if key.startswith("redbot"):
                    continue

                if isinstance(attr, tasks.Loop):
                    log.debug(f"Attaching profiler to TASK {key}")
                    original_coro = attr.coro
                    wrapped_coro = self.profile_wrapper(original_coro, cog_name, "task")
                    attr.coro = wrapped_coro
                    self.original_loops.setdefault(cog_name, {})[attr_name] = original_coro
                else:
                    log.debug(f"Attaching profiler to METHOD {key}")
                    wrapped_fn = self.profile_wrapper(attr, cog_name, "method")
                    self.original_methods.setdefault(cog_name, {})[attr_name] = attr
                    setattr(cog, attr_name, wrapped_fn)

                attached = True

        return attached

    def detach_profilers(self) -> None:
        """Detach profilers from all methods, commands, tasks, and listeners."""
        # Detach methods
        for cog_name, methods in self.original_methods.items():
            cog = self.bot.get_cog(cog_name)
            if not cog:
                continue
            for method_name, original_method in methods.items():
                setattr(cog, method_name, original_method)
                log.debug(f"Detaching profiler from method {cog_name}.{method_name}")
        self.original_methods.clear()

        # Detach loops
        for cog_name, loops in self.original_loops.items():
            cog = self.bot.get_cog(cog_name)
            if not cog:
                continue
            for loop_name, original_coro in loops.items():
                loop = getattr(cog, loop_name, None)
                if not loop:
                    continue
                loop.coro = original_coro
                log.debug(f"Detaching profiler from loop {cog_name}.{loop_name}")
        self.original_loops.clear()

        # Detach commands
        for cog_name, callbacks in self.original_callbacks.items():
            cog = self.bot.get_cog(cog_name)
            if not cog:
                continue
            for command_name, original_callback in callbacks.items():
                command = self.bot.get_command(command_name)
                if not command:
                    continue
                command.callback = original_callback
                log.debug(f"Detaching profiler from command {cog_name}.{command_name}")
        self.original_callbacks.clear()

        # Detach app commands
        for cog_name, callbacks in self.original_slash_callbacks.items():
            cog = self.bot.get_cog(cog_name)
            if not cog:
                continue
            for command_name, original_callback in callbacks.items():
                for command in cog.walk_app_commands():
                    if command.qualified_name != command_name:
                        continue
                    setattr(command, "_callback", original_callback)
                log.debug(f"Detaching profiler from slash command {cog_name}.{command_name}")
        self.original_slash_callbacks.clear()

        # Detach listeners
        for cog_name, listeners in self.original_listeners.items():
            cog = self.bot.get_cog(cog_name)
            if not cog:
                continue
            for listener_name, (original_coro, wrapped_coro) in listeners.items():
                self.bot.remove_listener(wrapped_coro, name=listener_name)
                self.bot.add_listener(original_coro, name=listener_name)
                log.debug(f"Detaching profiler from listener {cog_name}.{listener_name}")
        self.original_listeners.clear()

    def map_methods(self) -> None:
        """Populate the methods cache"""
        self.methods.clear()
        for cog_name in self.bot.cogs:
            cog = self.bot.get_cog(cog_name)
            # Add commands
            for command in cog.walk_commands():
                if isinstance(command, commands.HybridCommand) or isinstance(command, commands.HybridGroup):
                    func_type = "hybrid"
                elif isinstance(command, commands.Command) or isinstance(command, commands.Group):
                    func_type = "command"
                else:
                    continue
                key = f"{command.callback.__module__}.{command.callback.__name__}"
                self.methods[key] = Method(
                    is_coro=True, func_type=func_type, cog_name=cog_name, command_name=command.qualified_name
                )
            # Add app commands
            for command in cog.walk_app_commands():
                if isinstance(command, app_commands.Command):
                    func_type = "slash"
                else:
                    continue
                key = f"{command.callback.__module__}.{command.callback.__name__}"
                self.methods[key] = Method(
                    is_coro=True, func_type=func_type, cog_name=cog_name, command_name=command.qualified_name
                )
            # Add listeners
            for _, listener_coro in cog.get_listeners():
                key = f"{listener_coro.__module__}.{listener_coro.__name__}"
                self.methods[key] = Method(is_coro=True, func_type="listener", cog_name=cog_name)
            # Add methods
            for attr_name in dir(cog):
                attr = getattr(cog, attr_name, None)
                if any(
                    [
                        attr is None,
                        not hasattr(attr, "__module__"),  # Skip builtins
                        not callable(attr),  # Skip non-callable attributes
                        attr_name.startswith("__"),  # Skip dunder methods
                        getattr(attr, "__cog_listener__", None) is not None,  # Skip listeners
                    ]
                ):
                    continue
                key = f"{attr.__module__}.{attr_name}"
                if key.startswith("redbot"):
                    continue
                if key in self.methods:
                    continue
                is_coro = asyncio.iscoroutinefunction(attr)
                func_type = "task" if isinstance(attr, tasks.Loop) else "method"
                self.methods[key] = Method(is_coro=is_coro, func_type=func_type, cog_name=cog_name)

    def build(self) -> None:
        for cog_name in self.db.tracked_cogs:
            attached = self.attach_cog(cog_name)
            if not attached:
                log.warning(f"Failed to attach profiler to {cog_name}")

        for method_key in self.db.tracked_methods:
            if method_key in self.currently_tracked:
                continue
            attached = self.attach_method(method_key)
            if not attached:
                log.warning(f"Failed to attach profiler to {method_key}")

    async def cleanup(self) -> bool:
        def _run() -> bool:
            oldest_allowed_record = datetime.now() - timedelta(hours=self.db.delta)
            cleaned = False
            copied = {k: v.copy() for k, v in self.db.stats.items()}
            for cog_name, methods in copied.items():
                if not self.bot.get_cog(cog_name):
                    del self.db.stats[cog_name]
                    cleaned = True
                    continue
                if cog_name not in self.db.tracked_cogs:
                    del self.db.stats[cog_name]
                    cleaned = True
                    continue

                for method_name, profiles in methods.items():
                    if not profiles:
                        del self.db.stats[cog_name][method_name]
                        cleaned = True
                        continue
                    if profiles[0].func_type in ["command", "hybrid", "slash"] and not self.db.track_commands:
                        del self.db.stats[cog_name][method_name]
                        cleaned = True
                        continue
                    elif profiles[0].func_type == "listener" and not self.db.track_listeners:
                        del self.db.stats[cog_name][method_name]
                        cleaned = True
                        continue
                    elif profiles[0].func_type == "task" and not self.db.track_tasks:
                        del self.db.stats[cog_name][method_name]
                        cleaned = True
                        continue
                    elif profiles[0].func_type == "method" and not self.db.track_methods:
                        del self.db.stats[cog_name][method_name]
                        cleaned = True
                        continue
                    elif profiles[0].timestamp < oldest_allowed_record:
                        self.db.stats[cog_name][method_name] = [
                            i for i in profiles if i.timestamp > oldest_allowed_record
                        ]
                        cleaned = True
                        continue

                    indexes_to_remove = set()
                    for idx, profile in enumerate(profiles):
                        if idx >= len(self.db.stats[cog_name][method_name]):
                            break
                        if profile.func_profiles and not self.db.verbose:
                            indexes_to_remove.add(idx)

                    if indexes_to_remove:
                        self.db.stats[cog_name][method_name] = [
                            i for idx, i in enumerate(profiles) if idx not in indexes_to_remove
                        ]
                        cleaned = True

            return cleaned

        cleaned = await asyncio.to_thread(_run)
        if cleaned:
            await self.save()
        return cleaned
