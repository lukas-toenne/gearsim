from __future__ import annotations
from collections.abc import Sequence

import bpy
from math import *
from .pose_driver_utils import PropertyNamespace


# Creates a system of interlocked gears using drivers to update rotations.
#
# Rotations are updated indirectly through integrated angular velocities.
# The reason is that computing absolute rotation value from the source gear
# can involve a variable phase. The phase can in turn depend on a condition
# when gears can be unlocked, e.g. with a clutch. Either the gear rotation
# is updated or the phase is updated, depending on the clutch condition.
# However, to the driver system this creates a cyclic dependency, even though
# in reality only one "direction" is needed at any point.
#
# Using velocity state variables solves the problem:
# - all velocities depend on source gear velocities
# - rotations are updated from own velocity and frame delta
# - phase corrections can depend on source gear position
#   (i.e. teeth don't overlap, phase is a multiple of 1/teeth)


# Max. supported length of driver expressions
max_expr_len = bpy.types.Driver.bl_rna.properties['expression'].length_max

gearsim_namespace = PropertyNamespace("__gearsim__")
_frame_prev_prop = "frame_prev"
_frame_delta_prop = "frame_delta"

_idprop_speed = "speed"

class DriverVariable:
    def __init__(self, varname):
        self.varname = varname

    def set_scope(self, scope):
        self.varname = self.varname + scope

    def __str__(self):
        return self.varname

    def apply(self, driver):
        # Should be implemented by subclass
        assert(False)

class RotationVariable(DriverVariable):
    def __init__(self, varname, target, axis):
        super().__init__(varname)
        self.target = target
        self.axis = axis

    def apply(self, driver):
        gearsim_namespace.add_rotation_variable(driver, self.varname, self.target, self.axis)

class IDPropVariable(DriverVariable):
    def __init__(self, varname, target, prop):
        super().__init__(varname)
        self.target = target
        self.prop = prop

    def apply(self, driver):
        gearsim_namespace.add_idprop_variable(driver, self.varname, self.target, self.prop)

class FrameDeltaVariable(DriverVariable):
    def __init__(self, varname, target):
        super().__init__(varname)
        self.target = target

    def apply(self, driver):
        gearsim_namespace.add_idprop_variable(driver, self.varname, self.target, _frame_delta_prop)


# def bound_expression(expr, vars):
#     return expr.format(*[v.varname for v in vars])

# def make_prop_driver(target, prop, index, expression, variables, use_self=False):
#     assert len(expression) <= max_expr_len, "Driver expression length exceeded: " + expression
#     driver = gearsim_namespace.add_prop_driver(target, prop, index)
#     driver.use_self = use_self
#     driver.expression = bound_expression(expression, variables)
#     for v in variables:
#         v.apply(driver)

# def make_idprop_driver(target, prop, expression, variables, use_self=False):
#     assert len(expression) <= max_expr_len, "Driver expression length exceeded: " + expression
#     driver = gearsim_namespace.add_idprop_driver(target, prop)
#     driver.use_self = use_self
#     driver.expression = bound_expression(expression, variables)
#     for v in variables:
#         v.apply(driver)

def make_prop_driver(target, propname, index, expression, variables, use_self):
    assert len(expression) <= max_expr_len, "Driver expression length exceeded: " + expression
    driver = gearsim_namespace.add_prop_driver(target, propname, index)
    driver.use_self = use_self
    driver.expression = expression
    for v in variables:
        v.apply(driver)

def make_idprop_driver(target, propname, expression, variables, use_self=False):
    assert len(expression) <= max_expr_len, "Driver expression length exceeded: " + expression
    driver = gearsim_namespace.add_idprop_driver(target, propname)
    driver.use_self = use_self
    driver.expression = expression
    for v in variables:
        v.apply(driver)



class GearNodeContext:
    def __init__(self, target, current_value_expr):
        self.target = target
        self.current_value_expr = current_value_expr


class GearNode():
    scope = None

    def add_idprop(self, context, propname, default, min, max):
        gearsim_namespace.add_idprop(context.target, self.scope + propname, default, min, max)
        return propname

    def make_framedelta_var(self, context, varname):
        return FrameDeltaVariable(varname, context.target.id_data)

    def make_idprop_var(self, context, varname, propname):
        return IDPropVariable(varname, context.target, self.scope + propname)

    def make_prop_driver(self, context, propname, index, expression, variables, use_self):
        # No scope here, props are built in
        return make_prop_driver(context.target, propname, index, expression, variables, use_self)

    def make_idprop_driver(self, context, propname, expression, variables, use_self=False):
        return make_idprop_driver(context.target, self.scope + propname, expression, variables, use_self)


class TargetNode(GearNode):
    input_node : SourceGearNode = None

    def __init__(self, target_gear : GearDescriptor):
        self.target_gear = target_gear

    def build_drivers(self, obj : bpy.types.Object):
        assert(input)

        axis_names = ['x', 'y', 'z']
        current_value_expr = "self.rotation_euler.{axis}".format(axis=axis_names[self.target_gear.axis])
        context = GearNodeContext(self.target_gear.pose_bone, current_value_expr)

        self.input_node.build_drivers(context)
        self.make_prop_driver(context, "rotation_euler", self.target_gear.axis, str(self.input_node.output), [self.input_node.output], False)


class SourceGearNode(GearNode):
    output : DriverVariable = None


class ConstRotationNode(SourceGearNode):
    def __init__(self, default_speed):
        self.default_speed = default_speed

    # 
    def build_drivers(self, context : GearNodeContext):
        # User setting to control speed
        self.add_idprop(context, "speed", self.default_speed, -1000000.0, 1000000.0)
        self.add_idprop(context, "rotation", 0.0, -1000000.0, 1000000.0)
        speedvar = self.make_idprop_var(context, "speed", "speed")
        deltavar = self.make_framedelta_var(context, "dt")
        self.make_idprop_driver(
            context,
            "rotation",
            "{curval}+{speed}*{delta}".format(
                curval=context.current_value_expr,
                speed=speedvar,
                delta=deltavar,
            ),
            [speedvar, deltavar],
            use_self = True)
        self.output = self.make_idprop_var(context, "rotation", "rotation")


# class Transmission:
#     def __init__(self, source_gear : GearDescriptor, source_teeth, ratio, condition : ConditionDescriptor = None):
#         self.source_gear = source_gear
#         self.source_teeth = source_teeth
#         self.ratio = ratio
#         self.condition = condition

#     def build_expression(self, target_gear : GearDescriptor, scope):
#         # User variable to control phase between gears
#         idprop_phase = "tooth_phase" + scope
#         gearsim_namespace.add_idprop(target_gear.pose_bone, idprop_phase, 0.0, 0.0, 1.0)

#         self.expr = "{source_rot}*{trans_ratio}+{trans_phase}".format(
#         )


#         inputvar = IDPropVariable("input" + scope, target_gear.pose_bone, inputprop)
#         phasevar = IDPropVariable("phase" + scope, target_gear.pose_bone, idprop_phase)
#         sourcevar = RotationVariable("src" + scope, self.source_gear.pose_bone, self.source_gear.axis)
#         vars.extend([inputvar, phasevar, sourcevar])
#         # Expression to align the rotation angle between two gears
#         expr = "2*pi*(round(({input})/pi*.5*{target_teeth}-{sourcevar}/pi*.5*{source_teeth}-{phase})+{phase})/{target_teeth}+{sourcevar}*{ratio}".format(
#             target_teeth=self.source_teeth / self.ratio,
#             source_teeth=self.source_teeth,
#             ratio=self.ratio,
#             input=inputvar.varname,
#             phase=phasevar.varname,
#             sourcevar=sourcevar.varname,
#             )
#         return expr


class GearDescriptor:
    def __init__(self, obj, name, axis):
        self.id_data = obj
        self.pose_bone = obj.pose.bones.get(name)
        self.axis = axis
        self.connections = []

    def apply_node(self, node : GearNode):
        context = GearContext(self)
        node.build_expression(context)

        self.pose_bone.rotation_mode = 'XYZ'
        expr = "({nodeexpr}) if frame>1 else 0".format(nodeexpr=node.expr)
        make_prop_driver(self.pose_bone, 'rotation_euler', self.axis, expr, node.vars, use_self=node.use_self)

    # def __add_rotation_driver(self):
    #     axis_names = ['x', 'y', 'z']
    #     expr = "self.rotation_euler.{}+dt*spd if frame>1 else 0".format(axis_names[self.axis])
    #     vars = [
    #         FrameDeltaVariable('dt', self.pose_bone.id_data),
    #         IDPropVariable('spd', self.pose_bone, _idprop_speed),
    #         ]
    #     use_self_var = True

    #     for i, conn in enumerate(reversed(self.connections)):
    #         scope = str(len(self.connections) - i)

    #         # NOTE: driver expression length is quite limited (256 chars), so to avoid exceeding the char limit
    #         # we store intermediate rotation values in extra id props
    #         idprop_input = "rotation" + scope
    #         gearsim_namespace.add_idprop(self.pose_bone, idprop_input, 0.0, -1000000.0, 1000000)
    #         make_idprop_driver(self.pose_bone, idprop_input, expr, vars, use_self=use_self_var)
    #         # Reset variables
    #         vars = []
    #         use_self_var = False

    #         expr = conn.build_expression(self, idprop_input, vars, scope)

    #         if conn.condition:
    #             for v in conn.condition.variables:
    #                 v.set_scope(str(scope))
    #             vars.extend(conn.condition.variables)
    #             cond_expr = bound_expression(conn.condition.expression, conn.condition.variables)
    #             expr = "({}) if ({}) else ({})".format(expr, cond_expr, tmpvar)
        
    #     self.pose_bone.rotation_mode = 'XYZ'
    #     make_prop_driver(self.pose_bone, 'rotation_euler', self.axis, expr, vars, use_self=use_self_var)

    # def cleanup(self):
    #     gearsim_namespace.clear_bone_drivers(self.pose_bone)
    #     gearsim_namespace.clear_bone_properties(self.pose_bone)

    # def set_const_rotation(self, rpf):
    #     gearsim_namespace.set_idprop(self.pose_bone, _idprop_speed, rpf * 2*pi)

    # sources must be a list of tuples:
    # [(GearDescriptor1, ratio1, N1, ConditionDescriptor1),
    #  (GearDescriptor2, ratio2, N2, ConditionDescriptor2),
    #  ...]
    #
    # The first source whose condition evaluates to True is used.
    # Conditions can be None or omitted, in which case the source is used unconditionally
    # and all subsequent sources ignored.
    #
    # N is the tooth count of the source gear, used to compute phase locking.
    # If N is 0 then no phase locking occurs.
    # def add_transmission(self):
    #     expr = ".0"
    #     vars = []

    #     num_sources = len(sources)
    #     for i, s in enumerate(reversed(sources)):
    #         if len(s) == 3:
    #             source, ratio, source_count = s
    #             condition = None
    #         elif len(s) == 4:
    #             source, ratio, source_count, condition = s
    #         else:
    #             assert(false)

    #         scope = str(num_sources - i)

    #         speed_sourcevar = IDPropVariable("src", source.pose_bone, _idprop_speed)
    #         speed_sourcevar.set_scope(scope)
    #         vars.append(speed_sourcevar)

    #         if condition:
    #             for v in condition.variables:
    #                 v.set_scope(scope)
    #             vars.extend(condition.variables)

    #             cond_expr = bound_expression(condition.expression, condition.variables)
    #             expr = "{}*{} if ({}) else ({})".format(speed_sourcevar.varname, ratio, cond_expr, expr)
    #         else:
    #             expr = "{}*{}".format(speed_sourcevar.varname, ratio)

    #     make_idprop_driver(self.pose_bone,_idprop_speed, expr, vars)

    def build(self):
        gearsim_namespace.add_idprop(self.pose_bone, _idprop_speed, 0.0, -1000000.0, 1000000)
        self.__add_rotation_driver()


class ConditionDescriptor:
    def __init__(self, expression, variables):
        self.expression = expression
        self.variables = variables


# Add a properties and drivers for frame delta
def setup_armature(obj, frame_current):
    # _clear_frame_drivers(obj)

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

    gearsim_namespace.add_idprop(obj, _frame_delta_prop, 0.0, -1000000.0, 1000000.0)
    gearsim_namespace.add_idprop(obj, _frame_prev_prop, 0.0, -1000000.0, 1000000.0)

    make_idprop_driver(obj, _frame_delta_prop, "frame - self['{}']".format(gearsim_namespace.idprop_uuid(obj, _frame_prev_prop)), variables=[], use_self=True)

    # Dummy variable to enforce a dependency and make sure that prev_frame is updated AFTER the delta
    make_idprop_driver(obj, _frame_prev_prop, "frame", variables=[IDPropVariable('delta', obj, _frame_delta_prop)])

def cleanup_armature(obj):
    gearsim_namespace.clear_id_drivers(obj)
    gearsim_namespace.clear_id_properties(obj)
    for pbone in obj.pose.bones:
        gearsim_namespace.clear_bone_drivers(pbone)
        gearsim_namespace.clear_bone_properties(pbone)


def build_drivers(obj : bpy.types.Object, nodes : Sequence[GearNode], frame_current):
    if obj.type != 'ARMATURE':
        raise Exception("Gear nodes require armature object")

    cleanup_armature(obj)
    setup_armature(obj, frame_current)

    # TODO topological node sort

    # TODO unique but semantically meaningful node names
    for i, node in enumerate(nodes):
        node.scope = "Node{index}_".format(index=i)

    for node in nodes:
        if isinstance(node, TargetNode):
            node.build_drivers(obj)