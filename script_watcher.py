"""
script_watcher.py: Reload watched script upon changes.

Copyright (C) 2015 Isaac Weaver
Author: Isaac Weaver <wisaac407@gmail.com>

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License along
    with this program; if not, write to the Free Software Foundation, Inc.,
    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""

bl_info = {
    "name": "Script Watcher",
    "author": "Isaac Weaver",
    "version": (0, 7),
    "blender": (2, 80, 0),
    "location": "Properties > Scene > Script Watcher",
    "description": "Reloads an external script on edits.",
    "warning": "Still in beta stage.",
    "wiki_url": "http://wiki.blender.org/index.php/Extensions:2.6/Py/Scripts/Development/Script_Watcher",
    "tracker_url": "https://github.com/wisaac407/blender-script-watcher/issues/new",
    "category": "Development",
}

import os
import sys
import io
import traceback
import types
import subprocess
import pdb
import contextlib

import console_python  # Blender module giving us access to the blender python console.
import bpy
from bpy.app.handlers import persistent


@persistent
def load_handler(dummy):
    running = bpy.context.scene.sw_settings.running

    # First of all, make sure script watcher is off on all the scenes.
    for scene in bpy.data.scenes:
        bpy.ops.wm.sw_watch_end({'scene': scene})

    # Startup script watcher on the current scene if needed.
    if running and bpy.context.scene.sw_settings.auto_watch_on_startup:
        bpy.ops.wm.sw_watch_start()

    # Reset the consoles list to remove all the consoles that don't exist anymore.
    for screen in bpy.data.screens:
        screen.sw_consoles.clear()


def add_scrollback(ctx, text, text_type):
    for line in text:
        bpy.ops.console.scrollback_append(ctx, text=line.replace('\t', '    '),
                                          type=text_type)


def get_console_id(area):
    """Return the console id of the given region."""
    if area.type == 'CONSOLE':  # Only continue if we have a console area.
        for region in area.regions:
            if region.type == 'WINDOW':
                return hash(region)  # The id is the hash of the window region.
    return False


def isnum(s):
    return s[1:].isnumeric() and s[0] in '-+1234567890'


def make_annotations(cls):
    """Converts class fields to annotations if running with Blender 2.8"""
    if bpy.app.version < (2, 80):
        return cls
    bl_props = {k: v for k, v in cls.__dict__.items() if isinstance(v, tuple)}
    if bl_props:
        if '__annotations__' not in cls.__dict__:
            setattr(cls, '__annotations__', {})
        annotations = cls.__dict__['__annotations__']
        for k, v in bl_props.items():
            annotations[k] = v
            delattr(cls, k)
    return cls


class SplitIO(io.StringIO):
    """Feed the input stream into another stream."""
    PREFIX = '[Script Watcher]: '

    _can_prefix = True

    def __init__(self, stream):
        io.StringIO.__init__(self)

        self.stream = stream

    def write(self, s):
        # Make sure we prefix our string before we do anything else with it.
        if self._can_prefix:
            s = self.PREFIX + s
        # only add the prefix if the last stream ended with a newline.
        self._can_prefix = s.endswith('\n')

        # Make sure to call the super classes write method.
        io.StringIO.write(self, s)

        # When we are written to, we also write to the secondary stream.
        self.stream.write(s)


class SWDebuggerPaused(Exception):
    """SW Debugger Pause Event"""


# class SWDebugger(pdb.Pdb):
#     cur_frame = None
#
#     def __init__(self, *a):
#         class stdin:
#             def readline(self):
#                 raise SWDebuggerPaused
#         super(SWDebugger, self).__init__(*a)
#
#     def get_code(self, frame: types.FrameType):
#         c = frame.f_code
#         return c
#         return types.CodeType(c.co_argcount, c.co_kwonlyargcount, c.co_nlocals,
#                               c.co_stacksize, c.co_flags, c.co_code[frame.f_lasti:], c.co_consts,
#                               c.co_names, c.co_varnames, c.co_filename, c.co_name,
#                               c.co_firstlineno, c.co_lnotab, c.co_freevars, c.co_cellvars)
#
#     def start(self, code, locals):
#         try:
#             sys.settrace(self.trace_dispatch)
#             exec(code, locals, locals)
#         except SWDebuggerPaused:
#             print("Paused")
#
#     def pause(self, frame=None):
#         sys.settrace(None)
#         if frame is not None:
#             self.cur_frame = frame
#         raise SWDebuggerPaused
#
#     def resume(self):
#         import pydevd
#         pydevd.settrace()
#         code = self.get_code(self.cur_frame)
#         exec(code, self.cur_frame.f_globals, self.cur_frame.f_locals)
#         # try:
#         #     sys.settrace(self.trace_dispatch)
#         #     code = self.get_code(self.cur_frame)
#         #     exec(code, self.cur_frame.f_globals, self.cur_frame.f_locals)
#         # except SWDebuggerPaused:
#         #     print("Paused")
#
#     def input_line(self, line):
#         line = line.strip()
#         if line == 'continue':
#             self.resume()
#         elif line == 'locals':
#             locs = {}
#             for key, val in self.cur_frame.f_locals.items():
#                 if key not in self.cur_frame.f_globals:
#                     locs[key] = val
#             return locs
#         elif line == 'globals':
#             return self.cur_frame.f_globals
#         elif line == 'dis':
#             import dis, contextlib
#             ret = io.StringIO()
#             with contextlib.redirect_stdout(ret):
#                 dis.dis(self.cur_frame.f_code)
#             ret.seek(0)
#             return ret.read()
#         elif line == 'lineno':
#             return self.cur_frame.f_lineno
#         elif line == 'lasti':
#             return self.cur_frame.f_lasti
#         elif line == 'exit':
#             self.quitting = True
#         else:
#             return "Invalid Command: " + line
#
#     def dispatch_line(self, frame: types.FrameType):
#         if frame.f_code.co_filename == "/home/isaac/blender-addons/script-watcher/test.py":
#             self.pause(frame)
#         else:
#             return self.trace_dispatch
#
#     def dispatch_return(self, frame, arg):
#         #self.pause(frame)
#         return self.trace_dispatch
#
#     def dispatch_exception(self, frame, arg):
#         #self.pause(frame)
#         return self.trace_dispatch
#
#     def dispatch_call(self, frame, arg):
#         return self.trace_dispatch
#

class Input:
    _buffer = None

    def write(self, line):
        self._buffer = line

    def readline(self):
        if self._buffer:
            ret = self._buffer
            # self._buffer = None
            return ret
        raise SWDebuggerPaused


class Output:
    _buffer = None

    def write(self, s):
        if self._buffer is None:
            self._buffer = ''
        self._buffer += s

    def read(self):
        ret = self._buffer
        self._buffer = None
        return ret

    def flush(self):
        pass

class SWDebugger:
    def __init__(self):
        self._cur_frame = None
        self._stdin = Input()
        self._stdout = Output()
        self._old_input = input

        self._debugger = pdb.Pdb(stdin=self._stdin, stdout=self._stdout)

    @staticmethod
    def _new_input(arg):
        sys.__stdout__.write("new input function in use")
        return sys.readline()

    def get_prompt(self):
        return self._debugger.prompt

    def start(self, code, mod_dict):
        """Start the debugger"""

        try:
            pdb.__dict__['input'] = self._new_input
            self._debugger.run(code, mod_dict)
        except SWDebuggerPaused as e:
            pdb.__dict__['input'] = self._old_input
            tb = e.__traceback__
            while tb.tb_next is not None:
                tb = tb.tb_next
            self._cur_frame = tb.tb_frame

    def input_line(self, line):
        """Receive user input"""
        self._stdin.write(line)

        try:
            pdb.__dict__['input'] = self._new_input
            self._debugger.set_trace(self._cur_frame)
            # exec(self._cur_frame.f_code, self._cur_frame.f_globals, self._cur_frame.f_locals)
        except SWDebuggerPaused as e:
            pdb.__dict__['input'] = self._old_input
            tb = e.__traceback__
            while tb.tb_next is not None:
                tb = tb.tb_next

            self._cur_frame = tb.tb_frame
        return self._stdout.read()



def create_fake_module():
    """Registers a fake module for handling """
    mod_name = 'console_pdb'
    if mod_name not in sys.modules:
        language_id = "pdb"

        def add_scrollback(text, text_type):
            for l in text.split("\n"):
                bpy.ops.console.scrollback_append(text=l.replace("\t", "    "),
                                                  type=text_type)

        def get_debugger(debugger_id, mod=None, code=None):
            # # This part was taken from get_console from console_python
            # debuggers = getattr(get_debugger, "debuggers", None)
            # hash_next = hash(bpy.context.window_manager)
            #
            # if debuggers is None:
            #     debuggers = get_debugger.debuggers = {}
            #     get_debugger.consoles_namespace_hash = hash_next
            # else:
            #     # check if clearing the namespace is needed to avoid a memory leak.
            #     # the window manager is normally loaded with new blend files
            #     # so this is a reasonable way to deal with namespace clearing.
            #     # bpy.data hashing is reset by undo so cant be used.
            #     hash_prev = getattr(get_debugger, "debuggers_namespace_hash", 0)
            #
            #     if hash_prev != hash_next:
            #         get_debugger.consoles_namespace_hash = hash_next
            #         debuggers.clear()
            #
            # debugger = debuggers.get(debugger_id)
            debuggers = getattr(get_debugger, "debuggers", None)
            if debuggers is None:
                get_debugger.debuggers = debuggers = {}
            if debugger_id not in debuggers:
                #loader = ScriptWatcherLoader(bpy.context.scene.sw_settings.filepath)
                debuggers[debugger_id] = SWDebugger()
            debugger = debuggers[debugger_id]

            #if debugger is None:
                #debugger = SWDebugger()
            return debugger

        def execute(context, is_interactive):
            sc = context.space_data

            try:
                line = sc.history[-1].body
            except:
                return {'CANCELLED'}

            debugger = get_debugger(hash(context.region))

            bpy.ops.console.scrollback_append(text=sc.prompt + line, type='INPUT')

            output = debugger.input_line(line)
            if not isinstance(output, str):
                output = repr(output)
            add_scrollback(output, "OUTPUT")

            # insert a new blank line
            bpy.ops.console.history_append(text="", current_character=0,
                                           remove_duplicates=True)

            sc.prompt = debugger.get_prompt()
            return {'FINISHED'}

        def autocomplete(context):
            # ~ sc = context.space_data
            # TODO
            return {'CANCELLED'}

        def banner(context):
            sc = context.space_data

            return {'FINISHED'}

        mod = types.ModuleType(mod_name)
        mod.execute = execute
        mod.banner = banner
        mod.autocomplete = autocomplete
        mod.get_debugger = get_debugger

        sys.modules[mod_name] = mod
create_fake_module()

class ScriptWatcherLoader:
    """Load the script"""
    filepath = None
    mod_name = None
    run_main = None

    def __init__(self, filepath, run_main=False):
        self.filepath = filepath
        self.mod_name = self.get_mod_name()
        self.run_main = run_main

    def get_module(self):
        """Load the module"""
        with open(self.filepath) as f:
            paths, files = self.get_paths()

            # Create the module and setup the basic properties.
            mod = types.ModuleType(self.mod_name if self.run_main else '__main__')
            mod.__file__ = self.filepath
            mod.__path__ = paths
            mod.__package__ = self.mod_name
            mod.__loader__ = self

            code = compile(f.read(), self.filepath, 'exec')
            return mod, code

    def load_module(self):
        try:
            # Get the module
            mod, code = self.get_module()

            # Add the module to the system module cache.
            sys.modules[self.mod_name] = mod

            # Finally, execute the module.
            exec(code, mod.__dict__)

            if self.run_main and 'main' in mod.__dict__:
                mod.main()

        except IOError:
            print('Could not open script file.')

        except:
            sys.stderr.write("There was an error when loading the module:\n" + traceback.format_exc())

    def reload(self):
        """Reload the module clearing any cached sub-modules"""
        print('Reloading script:', self.filepath)
        self.remove_cached_mods()
        self.load_module()

    def get_paths(self):
        """Find all the python paths surrounding the given filepath."""
        dirname = os.path.dirname(self.filepath)

        paths = []
        filepaths = []

        for root, dirs, files in os.walk(dirname, topdown=True):
            if '__init__.py' in files:
                paths.append(root)
                for f in files:
                    filepaths.append(os.path.join(root, f))
            else:
                dirs[:] = []  # No __init__ so we stop walking this dir.

        # If we just have one (non __init__) file then return just that file.
        return paths, filepaths or [self.filepath]

    def get_mod_name(self):
        """Return the module name."""
        dir, mod = os.path.split(self.filepath)

        # Module is a package.
        if mod == '__init__.py':
            mod = os.path.basename(dir)

        # Module is a single file.
        else:
            mod = os.path.splitext(mod)[0]

        return mod

    def remove_cached_mods(self):
        """Remove all the script modules from the system cache."""
        paths = self.get_paths()
        for mod_name, mod in list(sys.modules.items()):
            if hasattr(mod, '__file__') and mod.__file__ and os.path.dirname(mod.__file__) in paths:
                del sys.modules[mod_name]

# Addon preferences.
@make_annotations
class ScriptWatcherPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    editor_path = bpy.props.StringProperty(
        name='Editor Path',
        description='Path to external editor.',
        subtype='FILE_PATH'
    )

    def draw(self, context):
        layout = self.layout

        layout.prop(self, 'editor_path')


# Define the script watching operator.
class WatchScriptOperator(bpy.types.Operator):
    """Watches the script for changes, reloads the script if any changes occur."""
    bl_idname = "wm.sw_watch_start"
    bl_label = "Watch Script"

    _timer = None
    _running = False
    _times = None
    use_py_console = None
    use_pdb = None
    loader = None

    def reload_script(self, context):
        """Reload this script while printing the output to blenders python console."""

        # Setup stdout and stderr.
        stdout = SplitIO(sys.stdout)
        stderr = SplitIO(sys.stderr)

        sys.stdout = stdout
        sys.stderr = stderr

        # Run the script.
        if self.use_pdb:
            self.loader.remove_cached_mods()
            mod, code = self.loader.get_module()

            sys.modules[mod.__name__] = mod

            for area in context.screen.areas:
                if area.type == 'CONSOLE':
                    for space in area.spaces:
                        if space.type == 'CONSOLE':
                            break
                    debugger_id = get_console_id(area)

            # Ensure that the module is loaded
            create_fake_module()

            space.language = 'pdb'
            import console_pdb
            debugger = console_pdb.get_debugger(debugger_id)
            debugger.start(code, mod.__dict__)
        else:
            self.loader.reload()

        # Go back to the begining so we can read the streams.
        stdout.seek(0)
        stderr.seek(0)

        # Don't use readlines because that leaves trailing new lines.
        output = stdout.read().split('\n')
        output_err = stderr.read().split('\n')

        for console in context.screen.sw_consoles:
            if console.active and isnum(console.name):  # Make sure it's not some random string.

                console, _, _ = console_python.get_console(int(console.name))

                # Set the locals to the modules dict.
                console.locals = sys.modules[self.loader.mod_name].__dict__

        if self.use_py_console:
            # Print the output to the consoles.
            for area in context.screen.areas:
                if area.type == "CONSOLE":
                    ctx = context.copy()
                    ctx.update({"area": area})

                    # Actually print the output.
                    if output:
                        add_scrollback(ctx, output, 'OUTPUT')

                    if output_err:
                        add_scrollback(ctx, output_err, 'ERROR')

        # Cleanup
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

    def modal(self, context, event):
        if not context.scene.sw_settings.running:
            self.cancel(context)
            return {'CANCELLED'}

        if context.scene.sw_settings.reload:
            context.scene.sw_settings.reload = False
            self.reload_script(context)
            return {'PASS_THROUGH'}

        if event.type == 'TIMER':
            for path in self._times:
                cur_time = os.stat(path).st_mtime

                if cur_time != self._times[path]:
                    self._times[path] = cur_time
                    self.reload_script(context)

        return {'PASS_THROUGH'}

    def execute(self, context):
        if context.scene.sw_settings.running:
            return {'CANCELLED'}

        # Grab the settings and store them as local variables.
        self.use_py_console = context.scene.sw_settings.use_py_console
        self.use_pdb = context.scene.sw_settings.use_pdb

        filepath = bpy.path.abspath(context.scene.sw_settings.filepath)

        # If it's not a file, doesn't exist or permission is denied we don't proceed.
        if not os.path.isfile(filepath):
            self.report({'ERROR'}, 'Unable to open script.')
            return {'CANCELLED'}

        self.loader = ScriptWatcherLoader(filepath, context.scene.sw_settings.run_main)

        # Setup the times dict to keep track of when all the files where last edited.
        dirs, files = self.loader.get_paths()
        self._times = dict(
            (path, os.stat(path).st_mtime) for path in files)  # Where we store the times of all the paths.
        self._times[files[0]] = 0  # We set one of the times to 0 so the script will be loaded on startup.

        # Setup the event timer.
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)

        context.scene.sw_settings.running = True
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)

        # Should we call a separate close function on the loader?
        self.loader.remove_cached_mods()

        context.scene.sw_settings.running = False


class CancelScriptWatcher(bpy.types.Operator):
    """Stop watching the current script."""
    bl_idname = "wm.sw_watch_end"
    bl_label = "Stop Watching"

    def execute(self, context):
        # Setting the running flag to false will cause the modal to cancel itself.
        context.scene.sw_settings.running = False
        return {'FINISHED'}


class ReloadScriptWatcher(bpy.types.Operator):
    """Reload the current script."""
    bl_idname = "wm.sw_reload"
    bl_label = "Reload Script"

    def execute(self, context):
        # Setting the reload flag to true will cause the modal to cancel itself.
        context.scene.sw_settings.reload = True
        return {'FINISHED'}


class OpenExternalEditor(bpy.types.Operator):
    """Edit script in an external text editor."""
    bl_idname = "wm.sw_edit_externally"
    bl_label = "Edit Externally"

    def execute(self, context):
        addon_prefs = context.user_preferences.addons[__name__].preferences

        filepath = bpy.path.abspath(context.scene.sw_settings.filepath)

        subprocess.Popen((addon_prefs.editor_path, filepath))
        return {'FINISHED'}


class SWAddBreakpoint(bpy.types.Operator):
    """Add a breakpoint"""
    bl_idname = "wm.sw_breakpoint_add"
    bl_label = "Add Breakpoint"

    def execute(self, context):
        sw = context.scene.sw_settings
        bp = sw.breakpoints.add()
        sw.breakpoint_active_index = sw.breakpoints.values().index(bp)

        return {'FINISHED'}


class SWRemoveBreakpoint(bpy.types.Operator):
    """Remove a breakpoint"""
    bl_idname = "wm.sw_breakpoint_remove"
    bl_label = "Remove Breakpoint"

    def execute(self, context):
        sw = context.scene.sw_settings
        sw.breakpoints.remove(sw.breakpoint_active_index)

        sw.breakpoint_active_index = max(sw.breakpoint_active_index - 1, 0)

        return {'FINISHED'}


# Create the UI for the operator. NEEDS FINISHING!!
class ScriptWatcherPanel(bpy.types.Panel):
    """UI for the script watcher."""
    bl_label = "Script Watcher"
    bl_idname = "SCENE_PT_script_watcher"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout
        running = context.scene.sw_settings.running

        col = layout.column()
        col.prop(context.scene.sw_settings, 'filepath')
        col.prop(context.scene.sw_settings, 'use_py_console')
        col.prop(context.scene.sw_settings, 'auto_watch_on_startup')
        col.prop(context.scene.sw_settings, 'run_main')

        if bpy.app.version < (2, 80, 0):
            col.operator('wm.sw_watch_start', icon='VISIBLE_IPO_ON')
        else:
            col.operator('wm.sw_watch_start', icon='HIDE_OFF')

        col.enabled = not running

        if running:
            row = layout.row(align=True)
            row.operator('wm.sw_watch_end', icon='CANCEL')
            row.operator('wm.sw_reload', icon='FILE_REFRESH')

        layout.separator()
        layout.operator('wm.sw_edit_externally', icon='TEXT')

        layout.prop(context.scene.sw_settings, 'use_pdb')

        layout.label("Breakpoints:")
        row = layout.row()
        col = row.column()
        col.template_list("SW_UL_breakpoints", "breakpoints", context.scene.sw_settings,
                             "breakpoints", context.scene.sw_settings, "breakpoint_active_index", rows=1)
        col = row.column(align=True)
        col.operator("wm.sw_breakpoint_add", icon='ZOOMIN', text="")
        col.operator("wm.sw_breakpoint_remove", icon='ZOOMOUT', text="")


class SW_UL_breakpoints(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index, flt_flag):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row()
            row.prop(item, "lineno", emboss=False)
            row.prop(item, "active")
        # 'GRID' layout type should be as compact as possible (typically a single icon!).
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon_value=icon)


class SWBreakpoint(bpy.types.PropertyGroup):
    lineno = bpy.props.IntProperty(
        name="Line Number",
        min=1,
        default=1
    )

    active = bpy.props.BoolProperty(
        name="Active",
        description="Activate breakpoint",
        default=True
    )


@make_annotations
class ScriptWatcherSettings(bpy.types.PropertyGroup):
    """All the script watcher settings."""
    running = bpy.props.BoolProperty(default=False)
    reload = bpy.props.BoolProperty(default=False)

    filepath = bpy.props.StringProperty(
        name='Script',
        description='Script file to watch for changes.',
        subtype='FILE_PATH'
    )

    use_py_console = bpy.props.BoolProperty(
        name='Use py console',
        description='Use blenders built-in python console for program output (e.g. print statements and error messages)',
        default=False
    )

    use_pdb = bpy.props.BoolProperty(
        name="Use Python Debugger",
        description="Use the python debugger in the console",
        default=False
    )

    auto_watch_on_startup = bpy.props.BoolProperty(
        name='Watch on startup',
        description='Watch script automatically on new .blend load',
        default=False
    )

    breakpoints = bpy.props.CollectionProperty(
        name="Breakpoints",
        description="Debugging breakpoints",
        type=SWBreakpoint
    )

    breakpoint_active_index = bpy.props.IntProperty()

    run_main = bpy.props.BoolProperty(
        name='Run Main',
        description='Instead of running the module with the name __main__ execute the module and call main()',
        default=False,
    )

def update_debug(self, context):
    console_id = get_console_id(context.area)

    console, _, _ = console_python.get_console(console_id)

    if self.active:
        console.globals = console.locals

        if context.scene.sw_settings.running:
            dir, mod = os.path.split(bpy.path.abspath(context.scene.sw_settings.filepath))

            # XXX This is almost the same as get_mod_name so it should become a global function.
            if mod == '__init__.py':
                mod = os.path.basename(dir)
            else:
                mod = os.path.splitext(mod)[0]

            console.locals = sys.modules[mod].__dict__

    else:
        console.locals = console.globals

        # ctx = context.copy() # Operators only take dicts.
        # bpy.ops.console.update_console(ctx, debug_mode=self.active, script='test-script.py')


@make_annotations
class SWConsoleSettings(bpy.types.PropertyGroup):
    active = bpy.props.BoolProperty(
        name="Debug Mode",
        update=update_debug,
        description="Enter Script Watcher debugging mode (when in debug mode you can access the script variables).",
        default=False
    )


class SWConsoleHeader(bpy.types.Header):
    bl_idname = "CONSOLE_HT_script_watcher"
    bl_space_type = 'CONSOLE'

    def draw(self, context):
        layout = self.layout

        cs = context.screen.sw_consoles

        console_id = str(get_console_id(context.area))

        # Make sure this console is in the consoles collection.
        if console_id not in cs:
            console = cs.add()
            console.name = console_id

        row = layout.row()
        row.scale_x = 1.8
        row.prop(cs[console_id], 'active', toggle=True)

classes = (
    ScriptWatcherPreferences,

    WatchScriptOperator,
    CancelScriptWatcher,
    ReloadScriptWatcher,
    OpenExternalEditor,

    ScriptWatcherPanel,
    ScriptWatcherSettings,
    SWConsoleSettings,
    SWConsoleHeader,
)

def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)

    bpy.types.Scene.sw_settings = \
        bpy.props.PointerProperty(type=ScriptWatcherSettings)

    bpy.app.handlers.load_post.append(load_handler)

    bpy.types.Screen.sw_consoles = bpy.props.CollectionProperty(
        type=SWConsoleSettings
    )


def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)

    bpy.app.handlers.load_post.remove(load_handler)

    del bpy.types.Scene.sw_settings

    del bpy.types.Screen.sw_consoles


if __name__ == "__main__":
    if 'console_pdb' in sys.modules:
        del sys.modules['console_pdb']
    register()
