from __future__ import annotations
from collections.abc import Sequence

import bpy
import sys
from .pose_driver_utils import PropertyNamespace

gearsim_namespace = PropertyNamespace("__gearsim__")

def _resolve_driver_variables(driver, expression, **kwargs):
    driver.use_self = kwargs.get("use_self", False)

    # dict to resolve expression substrings
    strdict = dict()
    for key, value in kwargs.items():
        if isinstance(value, NodeValue):
            # Create a driver variable, using the key as variable name
            var = value._make_driver_variable(driver)
            var.name = key
            strdict[key] = key
        else:
            # Direct expression substring
            strdict[key] = value
    # Resolve expression substrings
    driver.expression = expression.format(**strdict)


class GearDescriptor:
    def __init__(self, obj : bpy.types.Object, bone_name, axis):
        assert(obj.type == 'ARMATURE')
        self.id_data = obj
        self.pose_bone = obj.pose.bones.get(bone_name)
        self.axis = axis


# Context needed to turn nodes and values into concrete drivers
class NodeContext:
    scope : str

    @classmethod
    def from_gear(cls, target_gear : GearDescriptor) -> NodeContext:
        context = cls()
        context.id_data = target_gear.id_data
        context.pose_bone = target_gear.pose_bone
        context.axis = target_gear.axis
        return context

    @classmethod
    def from_object(cls, obj : bpy.types.Object) -> NodeContext:
        context = cls()
        context.id_data = obj
        return context


# Describes a value that can be driven or used as a variable in other drivers
class NodeValue:
    condition : NodeValue = None


class RotationValue(NodeValue):
    def __init__(self, target, axis):
        self.target = target
        self.axis = axis

    @classmethod
    def from_context(cls, context : NodeContext):
        return cls(context.pose_bone, context.axis)

    @classmethod
    def from_gear(cls, gear : GearDescriptor):
        return cls(gear.pose_bone, gear.axis)

    def self_prop(self):
        axisname = ['x', 'y', 'z']
        return "self.rotation_euler." + axisname[self.axis]

    def _make_driver_variable(self, driver : bpy.types.Driver) -> bpy.types.DriverVariable:
        return gearsim_namespace.add_rotation_variable(driver, self.target, self.axis)

    def make_driver(self, expression, *, use_self=False, **kwargs) -> bpy.types.Driver:
        driver = gearsim_namespace.add_rotation_driver(self.target, self.axis)
        _resolve_driver_variables(driver, expression, use_self=use_self, **kwargs)
        return driver


class IDPropValue(NodeValue):
    def __init__(self, target, prop, *, value=None, min=None, max=None):
        self.target = target
        self.prop = prop
        if value is not None:
            if min is None:
                min = -sys.float_info.max
            if max is None:
                max = sys.float_info.max
            self.create(value, min, max)

    @classmethod
    def from_context(cls, context : NodeContext, prop, *, value=None, min=None, max=None):
        return cls(context.pose_bone, context.scope + prop, value=value, min=min, max=max)

    def self_prop(self):
        return "self['" + gearsim_namespace.idprop_uuid(self.target, self.prop) + "']"

    def create(self, value, min, max):
        gearsim_namespace.add_idprop(self.target, self.prop, value, min, max)

    def _make_driver_variable(self, driver : bpy.types.Driver) -> bpy.types.DriverVariable:
        return gearsim_namespace.add_idprop_variable(driver, self.target, self.prop)

    def make_driver(self, expression, *, use_self=False, **kwargs) -> bpy.types.Driver:
        driver = gearsim_namespace.add_idprop_driver(self.target, self.prop)
        _resolve_driver_variables(driver, expression, use_self=use_self, **kwargs)
        return driver


class FrameDeltaValue(IDPropValue):
    def __init__(self, target, *, value=None):
        super().__init__(target, "frame_delta", value=value)

    @classmethod
    def from_context(cls, context : NodeContext, *, value=None):
        return cls(context.id_data, value=value)


class FramePrevValue(IDPropValue):
    def __init__(self, target, *, value=None):
        super().__init__(target, "frame_prev", value=value)

    @classmethod
    def from_context(cls, context : NodeContext, *, value=None):
        return cls(context.id_data, value=value)


# Extended node value than can carry a condition
class OutputValue(IDPropValue):
    condition : NodeValue

    def __init__(self, target, prop, condprop=None, *, value=None, min=None, max=None):
        super().__init__(target, prop, value=value, min=min, max=max)
        self.condition = IDPropValue(target, condprop, value=1.0, min=0.0, max=1.0) if condprop else None

    @classmethod
    def from_context(cls, context : NodeContext, name, condname=None, *, value=None, min=None, max=None):
        return cls(context.pose_bone, context.scope + name, context.scope + condname, value=value, min=min, max=max)
