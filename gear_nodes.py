from __future__ import annotations
from collections.abc import Sequence

import bpy
import sys
from math import *
from .node_value import *


# Named value that can be converted into a driver variable
class NodeVariable:
    name : str
    value : NodeValue

    def __init__(self, name, value):
        self.name = name
        self.value = value

    def make_driver_variable(self, driver : bpy.types.Driver) -> bpy.types.DriverVariable:
        var = self.value.make_driver_variable(driver)
        var.name = self.name
        return var


class Node():
    def __init__(self):
        self.links = []

    def link(self, input_name, source_node, source_name):
        self.links.append((input_name, source_node, source_name))


# Node that drives the actual gear rotation.
class GearNode(Node):
    target_gear : GearDescriptor
    input_value : NodeValue

    def __init__(self, target_gear):
        super().__init__()
        self.target_gear = target_gear

    def build_drivers(self, context : NodeContext):
        rotation = RotationValue.from_context(context)
        rotation.make_driver(
            "gear_rotation",
            [NodeVariable("gear_rotation", self.input_value)]
        )


# Node used to build conditional expressions for gear drivers.
class ExpressionNode(Node):
    pass


class ConstRotationNode(ExpressionNode):
    default_speed : float
    output_value : NodeValue

    def __init__(self, default_speed):
        super().__init__()
        self.default_speed = default_speed

    def build_drivers(self, context : NodeContext):
        rotation = IDPropValue.from_context(context, "rotation", value=0.0)
        # Variable speed setting
        speed = UserParameter.from_context(context, "speed", value=self.default_speed)
        frame_delta = FrameDeltaValue.from_context(context)
        rotation.make_driver(
            "{curval} + speed * delta".format(curval=rotation.self_prop()),
            [NodeVariable("speed", speed), NodeVariable("delta", frame_delta)],
            use_self = True
        )
        self.output_value = rotation


class TransmissionNode(ExpressionNode):
    input_gear : GearDescriptor
    input_teeth : int
    output_teeth : int
    output_value : NodeValue
    condition : NodeValue

    def __init__(self, input_gear, input_teeth, output_teeth):
        super().__init__()
        self.input_gear = input_gear
        self.input_teeth = input_teeth
        self.output_teeth = output_teeth

    def build_drivers(self, context : NodeContext):
        input_rotation = RotationValue.from_gear(self.input_gear)
        condition = IDPropValue.from_context(context, "condition", value=1.0)
        rotation = IDPropValue.from_context(context, "rotation", value=0.0)
        phase = IDPropValue.from_context(context, "phase", value=0.0)
        ratio = self.input_teeth / self.output_teeth
        rotation.make_driver(
            "input * {ratio} + phase if condition else {same}".format(ratio=ratio, same=rotation.self_prop()),
            [NodeVariable("input", input_rotation), NodeVariable("phase", phase), NodeVariable("condition", condition)],
            use_self = True
        )
        self.output_value = rotation


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

    frame_delta.make_driver(
        "frame - {frame_prev}".format(frame_prev=frame_prev.self_prop()),
        [],
        use_self = True
    )
    # Dummy variable to enforce a dependency and make sure that prev_frame is updated AFTER the delta
    frame_prev.make_driver("frame", [NodeVariable("delta", frame_delta)])


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

            context = NodeContext(node.target_gear)

            for index, inode in enumerate(input_nodes):
                # TODO unique but semantically meaningful node names
                context.scope = "Node{index}_".format(index=index)

                # Resolve links
                for inname, srcnode, srcname in inode.links:
                    setattr(inode, inname, getattr(srcnode, srcname))

                inode.build_drivers(context)
