import bpy
from bpy.props import *


class GearNodeTree(bpy.types.NodeTree):
    '''Node tree for creating geared mechanisms'''
    bl_idname = 'GearNodeTreeType'
    bl_label = "Gear Node Tree"
    bl_icon = 'SETTINGS'


class GearNodeSetupOperator(bpy.types.Operator):
    bl_idname = "gearsim.setup"
    bl_label = "Set up gear simulation"
    bl_options = {'PRESET', 'UNDO'}

    @classmethod
    def poll(cls, context):
        space = getattr(context, "space_data", None)
        if not space or space.type != 'NODE_EDITOR' or space.tree_type != GearNodeTree.bl_idname:
            return False
        if space.node_tree is None:
            return False
        return True

    def execute(self, context):
        nodetree = context.space_data.node_tree

        return {'FINISHED'}


def node_header_draw(self, context):
    if context.space_data.tree_type != GearNodeTree.bl_idname:
        return
    layout = self.layout
    layout.operator("gearsim.setup")


def register():
    bpy.utils.register_class(GearNodeTree)
    bpy.utils.register_class(GearNodeSetupOperator)
    bpy.types.NODE_HT_header.append(node_header_draw)

def unregister():
    bpy.utils.unregister_class(GearNodeTree)
    bpy.utils.unregister_class(GearNodeSetupOperator)
    bpy.types.NODE_HT_header.remove(node_header_draw)
