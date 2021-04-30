from __future__ import annotations
from collections.abc import Sequence

import bpy
import sys
from .pose_driver_utils import PropertyNamespace

gearsim_namespace = PropertyNamespace("__gearsim__")


class GearDescriptor:
    def __init__(self, obj : bpy.types.Object, bone_name, axis):
        assert(obj.type == 'ARMATURE')
        self.id_data = obj
        self.pose_bone = obj.pose.bones.get(bone_name)
        self.axis = axis


# Context needed to turn nodes and values into concrete drivers
class NodeContext:
    scope : str
    target_gear : GearDescriptor
    current_value : NodeValue

    def __init__(self, target_gear : GearDescriptor):
        self.target_gear = target_gear
        self.current_value = RotationValue.from_gear(target_gear)

        self.frame_delta_value = FrameDeltaValue.from_gear(target_gear)


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

    def self_prop(self):
        axisname = ['x', 'y', 'z']
        return "self.rotation_euler." + axisname[self.axis]

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
                min = -sys.float_info.max
            if max is None:
                max = sys.float_info.max
            self.create(value, min, max)

    @classmethod
    def from_gear(cls, gear : GearDescriptor, prop, value=None, min=None, max=None):
        return cls(gear.pose_bone, prop, value, min, max)

    @classmethod
    def from_context(cls, context : NodeContext, prop, value=None, min=None, max=None):
        return cls(context.target_gear.pose_bone, context.scope + prop, value, min, max)

    def self_prop(self):
        return "self['" + gearsim_namespace.idprop_uuid(self.target, self.prop) + "']"

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
        super().__init__(target, "frame_delta", value)

    @classmethod
    def from_gear(cls, gear : GearDescriptor, value=None):
        return cls(gear.pose_bone.id_data, value)

    @classmethod
    def from_context(cls, context : NodeContext, value=None):
        return cls(context.target_gear.id_data, value)

class FramePrevValue(IDPropValue):
    def __init__(self, target, value=None):
        super().__init__(target, "frame_prev", value)

    @classmethod
    def from_gear(cls, gear : GearDescriptor, value=None):
        return cls(gear.pose_bone.id_data, value)

    @classmethod
    def from_context(cls, context : NodeContext, value=None):
        return cls(context.target_gear.id_data, value)
