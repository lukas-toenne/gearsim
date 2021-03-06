from __future__ import annotations
from collections.abc import Sequence

import bpy
import sys
from math import *
from .node_value import *


class Node():
    def __init__(self):
        self.links = []

    def link(self, input_name, source_node, source_name):
        self.links.append((input_name, source_node, source_name))


# Node that drives the actual gear rotation.
class GearNode(Node):
    target_gear : GearDescriptor
    input_value : OutputValue = None
    condition_value : NodeValue = None

    def __init__(self, target_gear):
        super().__init__()
        self.target_gear = target_gear

    def build_drivers(self, context : NodeContext):
        rotation = RotationValue.from_context(context)
        rotation.make_driver("gear_rotation",
            gear_rotation=self.input_value,
        )
        if (self.condition_value):
            self.input_value.condition.make_driver("cond",
                cond=self.condition_value,
            )


# Node used to build conditional expressions for gear drivers.
class ExpressionNode(Node):
    pass


class ConstRotationNode(ExpressionNode):
    default_speed : float
    output_value : OutputValue = None

    def __init__(self, default_speed):
        super().__init__()
        self.default_speed = default_speed

    def build_drivers(self, context : NodeContext):
        # Variable speed setting
        speed = IDPropValue.from_context(context, "speed", value=self.default_speed)
        self_rotation = RotationValue.from_context(context)
        rotation = OutputValue.from_context(context, "rotation", "condition", value=0.0)
        frame_delta = FrameDeltaValue.from_context(context)
        rotation.make_driver("{curval} + {speed} * {delta} if {cond} else {rot}",
            use_self=True,
            rot=self_rotation.self_prop(),
            curval=rotation.self_prop(),
            speed=speed,
            delta=frame_delta,
            cond=rotation.condition,
        )
        self.output_value = rotation


class TransmissionNode(ExpressionNode):
    input_gear : GearDescriptor
    input_teeth : int
    output_teeth : int
    output_value : OutputValue = None

    def __init__(self, input_gear, input_teeth, output_teeth):
        super().__init__()
        self.input_gear = input_gear
        self.input_teeth = input_teeth
        self.output_teeth = output_teeth

    def build_drivers(self, context : NodeContext):
        # Variable phase setting
        tooth_phase = IDPropValue.from_context(context, "tooth_phase", value=0.0, min=0.0, max=1.0)
        self_rotation = RotationValue.from_context(context)
        input_rotation = RotationValue.from_gear(self.input_gear)
        rotation = OutputValue.from_context(context, "rotation", "condition", value=0.0)
        tooth_offset = IDPropValue.from_context(context, "tooth_offset", value=0)
        ratio = self.input_teeth / self.output_teeth
        rotation.make_driver("{input}*{ratio} + 2*pi*({tooth_offset}+{tooth_phase})/{tooth_count} if {cond} else {rot}",
            use_self=True,
            rot=self_rotation.self_prop(),
            curval=rotation.self_prop(),
            input=input_rotation,
            ratio=ratio,
            tooth_offset=tooth_offset,
            tooth_count=self.output_teeth,
            tooth_phase=tooth_phase,
            cond=rotation.condition,
        )
        tooth_offset.make_driver("{curval} if {cond} else round({tooth_count}*({rot}-{input}*{ratio})/(2*pi))",
            use_self=True,
            rot=self_rotation.self_prop(),
            curval=tooth_offset.self_prop(),
            input=input_rotation,
            ratio=ratio,
            tooth_count=self.output_teeth,
            cond=rotation.condition,
        )
        self.output_value = rotation


class RangeConditionNode(ExpressionNode):
    pose_bone : bpy.types.PoseBone
    axis : int
    start_angle : float
    stop_angle : float
    condition_value : NodeValue = None

    def __init__(self, pose_bone, axis, start_angle, stop_angle):
        super().__init__()
        self.pose_bone = pose_bone
        self.axis = axis
        self.start_angle = start_angle
        self.stop_angle = stop_angle

    def build_drivers(self, context : NodeContext):
        input_rotation = RotationValue(self.pose_bone, self.axis)
        condition = IDPropValue.from_context(context, "condition", value=0.0)
        # Normalization factor
        one_over_two_pi = 1.0 / (2.0 * pi)
        start=self.start_angle * one_over_two_pi - floor(self.start_angle * one_over_two_pi)
        stop=self.stop_angle * one_over_two_pi - floor(self.stop_angle * one_over_two_pi)
        if start <= stop:
            expr = "1.0 if {input}*{C}-floor({input}*{C}) >= {start} and {input}*{C}-floor({input}*{C}) < {stop} else 0.0"
        else:
            expr = "1.0 if {input}*{C}-floor({input}*{C}) >= {start} or {input}*{C}-floor({input}*{C}) < {stop} else 0.0"
        condition.make_driver(expr,
            input=input_rotation,
            C=one_over_two_pi,
            start=start,
            stop=stop,
        )
        self.condition_value = condition


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
