bl_info = {
    "name": "Script Watcher",
    "author": "Isaac Weaver",
    "version": (0, 1),
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

prefix = """
import sys
sys.path.extend(%s)
"""

# Define the script watching operator.
class WatchScriptOperator(bpy.types.Operator):
    """Polls the script being watched. If any changes occur re-runs script."""
    bl_idname = "wm.sw_watch_start"
    bl_label = "Watch Script"

    _timer = None
    _running = False
    _last_time = None
    filepath = bpy.props.StringProperty()
    
    def get_paths(self, filepath):
        """Find all the python paths surrounding the given filepath."""
        
        dirname = os.path.dirname(filepath)
        
        paths = []
        
        for root, dirs, files in os.walk(dirname, topdown=True):
            if '__init__.py' in files:
                paths.append(root)
            else:
                dirs[:] = [] # No __init__ so we stop walking this dir.
        
        return paths or [filepath] # If we just have one (non __init__) file then that will be out path.
    
    def remove_cached_mods(self, paths):
        """Remove any cached modules that where imported in the last excecution."""
        for name, mod in sys.modules.items():
            # If the module is not internal and it came from a script path then it should be reloaded.
            if hasattr(mod, '__file__') and os.path.dirname(mod.__file__) in paths:
                del sys.modules[name]
    
    def get_globals(self):
        # Grab the current globals and override the key values.
        globs = globals()
        globs['__name__'] = '__main__'
        globs['__file__'] = self.filepath
        
        return globs

    def reload_script(self, filepath):
        print('Reloading script:', filepath)
        try:
            f = open(filepath)
            paths = self.get_paths(filepath)
            # Make sure that the script is in the sys path.
            for path in paths:
                if path not in sys.path:
                    sys.path.append(path)

            self.remove_cached_mods(paths)
            exec(compile(f.read(), filepath, 'exec'), self.get_globals())
        except IOError:
            print('Could not open script file.')
        except:
            print("The was an error when running the script:\n", traceback.format_exc())
        else:
            f.close()

    def modal(self, context, event):
        if not context.scene.sw_running:
            self.cancel(context)
            return {'CANCELLED'}
        if event.type == 'TIMER':
            filepath = bpy.path.abspath(context.scene.sw_filepath)
            cur_time = os.stat(filepath).st_mtime
            if cur_time != self._last_time:
                self._last_time = cur_time
                self.reload_script(filepath)

        return {'PASS_THROUGH'}

    def execute(self, context):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, context.window)
        wm.modal_handler_add(self)
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
