from __future__ import annotations
from collections.abc import Sequence

import bpy
import sys
from math import *
from .pose_driver_utils import PropertyNamespace

gearsim_namespace = PropertyNamespace("__gearsim__")
_frame_prev_prop = "frame_prev"
_frame_delta_prop = "frame_delta"


class GearDescriptor:
    def __init__(self, obj : bpy.types.Object, bone_name, axis):
        assert(obj.type == 'ARMATURE')
        self.id_data = obj
        self.pose_bone = obj.pose.bones.get(bone_name)
        self.axis = axis


# Context needed to turn nodes and values into concrete drivers
class NodeContext:
    def __init__(self, target_gear : GearDescriptor, current_value_expr):
        self.scope = None
        self.target_gear = target_gear
        self.current_value_expr = current_value_expr

        self.frame_delta_value = FrameDeltaValue(target)


# Describes a value that can be driven or used as a variable in other drivers
class NodeValue:
    def make_driver_variable(self, driver : bpy.types.Driver) -> bpy.types.DriverVariable:
        pass

    def make_driver(self, expression, variables : Sequence[NodeVariable], use_self=False) -> bpy.types.Driver:
        pass

class RotationValue(NodeValue):
    def __init__(self, target, axis):
        self.target = target
        self.axis = axis

    @classmethod
    def from_gear(cls, gear : GearDescriptor):
        return cls(gear.pose_bone, gear.axis)

    @classmethod
    def from_context(cls, context : NodeContext):
        return cls(context.target_gear.pose_bone, context.target_gear.axis)

    def make_driver_variable(self, driver : bpy.types.Driver) -> bpy.types.DriverVariable:
        return gearsim_namespace.add_rotation_variable(driver, self.target, self.axis)

    def make_driver(self, expression, variables : Sequence[NodeVariable], use_self=False) -> bpy.types.Driver:
        driver = gearsim_namespace.add_rotation_driver(self.target, self.axis)
        driver.expression = expression
        for var in variables:
            var.make_driver_variable(driver)
        driver.use_self = use_self
        return driver

class IDPropValue(NodeValue):
    def __init__(self, target, prop, value=None, min=None, max=None):
        self.target = target
        self.prop = prop
        if value is not None:
            if min is None:
                min = sys.float_info.min
            if max is None:
                max = sys.float_info.max
            self.create(value, min, max)

    @classmethod
    def from_gear(cls, gear : GearDescriptor, prop, value=None, min=None, max=None):
        return cls(gear.pose_bone, prop, value, min, max)

    @classmethod
    def from_context(cls, context : NodeContext, prop, value=None, min=None, max=None):
        return cls(context.target_gear.pose_bone, context.scope + prop, value, min, max)

    def qualified_prop(self):
        return gearsim_namespace.idprop_uuid(self.target, self.prop)

    def create(self, value, min, max):
        gearsim_namespace.add_idprop(self.target, self.prop, value, min, max)

    def make_driver_variable(self, driver : bpy.types.Driver) -> bpy.types.DriverVariable:
        return gearsim_namespace.add_idprop_variable(driver, self.target, self.prop)

    def make_driver(self, expression, variables : Sequence[NodeVariable], use_self=False) -> bpy.types.Driver:
        driver = gearsim_namespace.add_idprop_driver(self.target, self.prop)
        driver.expression = expression
        for var in variables:
            var.make_driver_variable(driver)
        driver.use_self = use_self
        return driver

class FrameDeltaValue(IDPropValue):
    def __init__(self, target, value=None):
        super().__init__(target, _frame_delta_prop, value)

    @classmethod
    def from_gear(cls, gear : GearDescriptor, value=None):
        return cls(gear.pose_bone.id_data, value)

    @classmethod
    def from_context(cls, context : NodeContext, value=None):
        return cls(context.id_data, value)

class FramePrevValue(IDPropValue):
    def __init__(self, target, value=None):
        super().__init__(target, _frame_prev_prop, value)

    @classmethod
    def from_gear(cls, gear : GearDescriptor, value=None):
        return cls(gear.pose_bone.id_data, value)

    @classmethod
    def from_context(cls, context : NodeContext, value=None):
        return cls(context.id_data, value)


# Named value that can be converted into a driver variable
class NodeVariable:
    def __init__(self, name, value : NodeValue):
        self.name = name
        self.value = value

    def make_driver_variable(self, driver : bpy.types.Driver) -> bpy.types.DriverVariable:
        var = self.value.make_driver_variable(driver)
        var.name = self.name
        return var


class Node():
    pass


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

    frame_delta.make_driver("frame - self['{}']".format(frame_prev.qualified_prop()), [], use_self=True)
    # Dummy variable to enforce a dependency and make sure that prev_frame is updated AFTER the delta
    frame_prev.make_driver("frame", [NodeVariable("delta", frame_delta)])


def build_drivers(obj : bpy.types.Object, nodes : Sequence[GearNode], frame_current):
    if obj.type != 'ARMATURE':
        raise Exception("Gear nodes require armature object")

    cleanup_armature(obj)
    setup_armature(obj, frame_current)

    # TODO topological node sort

    # TODO unique but semantically meaningful node names
    # for i, node in enumerate(nodes):
    #     node.scope = "Node{index}_".format(index=i)

    # for node in nodes:
    #     if isinstance(node, TargetNode):
    #         node.build_drivers(obj)