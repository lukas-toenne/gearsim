from __future__ import annotations
from collections.abc import Sequence

import bpy
from .node_value import *


def cleanup_armature(obj):
    gearsim_namespace.clear_id_drivers(obj)
    gearsim_namespace.clear_id_properties(obj)
    for pbone in obj.pose.bones:
        gearsim_namespace.clear_bone_drivers(pbone)
        gearsim_namespace.clear_bone_properties(pbone)


# Add a properties and drivers for frame delta
def setup_armature(obj, frame_current):
    # HACK: Computing frame deltas with drivers would usually create cyclic dependencies.
    #
    # The "delta" property depends on the previous frame value:
    #    delta = prev_frame - frame
    #
    # The prev_frame value copies the current frame,
    # but this has to happen at the end of the timestep!
    # The prev_frame driver gets a dependency on delta (without actually using the value),
    # which ensures that delta is update before the frame value is copied to prev_frame.
    # The delta driver uses the built-in "self" so we can access the prev_frame variable
    # without an explicit dependency and avoid a cycle.

    frame_delta = FrameDeltaValue(obj, value=0.0)
    frame_prev = FramePrevValue(obj, value=frame_current)

    frame_delta.make_driver("frame - {frame_prev}",
        use_self=True,
        frame_prev=frame_prev.self_prop(),
    )
    # Dummy variable to enforce a dependency and make sure that prev_frame is updated AFTER the delta
    frame_prev.make_driver("frame", delta=frame_delta)


def build_drivers(obj : bpy.types.Object, nodes : Sequence[GearNode], frame_current):
    if obj.type != 'ARMATURE':
        raise Exception("Gear nodes require armature object")

    cleanup_armature(obj)
    setup_armature(obj, frame_current)

    # Returns a topological sort of the input nodes
    def gather_expression_nodes(rootnode : GearNode):
        marked = set()
        visited = set()
        sorted = list()
        def visit(node):
            if node in marked:
                return
            if node in visited:
                raise Exception("Found cyclic node dependency")
            visited.add(node)
            for inname, srcnode, srcname in node.links:
                if isinstance(srcnode, ExpressionNode):
                    visit(srcnode)
            visited.remove(node)
            marked.add(node)
            sorted.append(node)

        visit(rootnode)
        return sorted

    for node in nodes:
        if isinstance(node, GearNode):
            input_nodes = gather_expression_nodes(node)

            context = NodeContext.from_gear(node.target_gear)

            for index, inode in enumerate(input_nodes):
                # TODO unique but semantically meaningful node names
                context.scope = "Node{index}_".format(index=index)

                # Resolve links
                for inname, srcnode, srcname in inode.links:
                    setattr(inode, inname, getattr(srcnode, srcname))

                inode.build_drivers(context)
