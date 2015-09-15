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
    "version": (0, 2),
    "blender": (2, 75, 0),
    "location": "Properties > Scene > Script Watcher",
    "description": "Reloads an external script on edits.",
    "warning": "Still in beta stage.",
    "wiki_url": "",
    "category": "Development",
}

import os, sys
import traceback
import bpy

# Define the script watching operator.
class WatchScriptOperator(bpy.types.Operator):
    """Polls the script being watched. If any changes occur re-runs script."""
    bl_idname = "wm.sw_watch_start"
    bl_label = "Watch Script"

    _timer = None
    _running = False
    _times = None
    filepath = None
    
    def get_paths(self, filepath):
        """Find all the python paths surrounding the given filepath."""
        
        dirname = os.path.dirname(filepath)
        
        paths = []
        filepaths = []
        
        for root, dirs, files in os.walk(dirname, topdown=True):
            if '__init__.py' in files:
                paths.append(root)
                for f in files:
                    filepaths.append(os.path.join(root, f))
            else:
                dirs[:] = [] # No __init__ so we stop walking this dir.
        
        return paths, filepaths or [filepath] # If we just have one (non __init__) file then that will be the file we watch.
    
    def remove_cached_mods(self, paths):
        """Remove any cached modules that where imported in the last excecution."""
        for name, mod in list(sys.modules.items()):
            # If the module is not internal and it came from a script path then it should be reloaded.
            if hasattr(mod, '__file__') and os.path.dirname(mod.__file__) in paths:
                del sys.modules[name]
    
    def get_globals(self):
        # Grab globals from the main module and override the key values.
        globs = sys.modules['__main__'].__dict__.copy()
        globs['__file__'] = self.filepath
        
        return globs

    def reload_script(self, filepath):
        print('Reloading script:', filepath)
        try:
            f = open(filepath)
            paths, files = self.get_paths(filepath)
            # Make sure that the script is in the sys path.
            for path in paths:
                if path not in sys.path:
                    sys.path.append(path)

            self.remove_cached_mods(paths)
            exec(compile(f.read(), filepath, 'exec'), self.get_globals())
        except IOError:
            print('Could not open script file.')
        except:
            print("There was an error when running the script:\n", traceback.format_exc())
        else:
            f.close()

    def modal(self, context, event):
        if not context.scene.sw_running:
            self.cancel(context)
            return {'CANCELLED'}
        if event.type == 'TIMER':
            for path in self._times:
                cur_time = os.stat(path).st_mtime
                
                if cur_time != self._times[path]:
                    self._times[path] = cur_time
                    self.reload_script(self.filepath)

        return {'PASS_THROUGH'}

    def execute(self, context):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, context.window)
        wm.modal_handler_add(self)
        
        self.filepath = bpy.path.abspath(context.scene.sw_filepath)
        
        files, dirs = self.get_paths(self.filepath)
        self._times = dict((path, os.stat(path).st_mtime) for path in files) # Where we store the times of all the paths.
        self._times[files[0]] = 0  # We set one of the times to 0 so the script will be loaded on startup.
        
        context.scene.sw_running = True
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        context.scene.sw_running = False


class CancelScriptWatcher(bpy.types.Operator):
    """Sets a flag which tells the modal to cancel itself."""
    bl_idname = "wm.sw_watch_end"
    bl_label = "Stop Watching"

    def execute(self, context):
        # Setting the running flag to false will cause the modal to cancel itself.
        context.scene.sw_running = False
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
        running = context.scene.sw_running

        col = layout.column()
        col.prop(context.scene, 'sw_filepath', text='')
        col.operator('wm.sw_watch_start', icon='VISIBLE_IPO_ON')
        col.active = not running
        if running:
            layout.operator('wm.sw_watch_end', icon='CANCEL')


def register():
    bpy.utils.register_class(WatchScriptOperator)
    bpy.utils.register_class(ScriptWatcherPanel)
    bpy.utils.register_class(CancelScriptWatcher)

    bpy.types.Scene.sw_filepath = bpy.props.StringProperty(subtype='FILE_PATH')
    bpy.types.Scene.sw_running = bpy.props.BoolProperty(default=False)


def unregister():
    bpy.utils.unregister_class(WatchScriptOperator)
    bpy.utils.unregister_class(ScriptWatcherPanel)
    bpy.utils.unregister_class(CancelScriptWatcher)

    del bpy.types.Scene.sw_filepath
    del bpy.types.Scene.sw_running


if __name__ == "__main__":
    register()
