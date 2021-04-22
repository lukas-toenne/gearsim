import bpy
from math import *
from . import pose_driver_utils


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

_frame_prev_prop = "gearsim_frame_prev"
_frame_delta_prop = "gearsim_frame_delta"
_speed_prop = "gear_speed"
_phase_prop = "gear_phase"

class DriverVariable:
    def __init__(self, varname):
        self.varname = varname

    def set_scope(self, namespace):
        self.varname = self.varname + namespace

    def apply(self, driver):
        # Should be implemented by subclass
        assert(False)

class RotationVariable(DriverVariable):
    def __init__(self, varname, target, axis):
        super().__init__(varname)
        self.target = target
        self.axis = axis

    def apply(self, driver):
        pose_driver_utils.add_rotation_variable(driver, self.varname, self.target, self.axis)

class IDPropVariable(DriverVariable):
    def __init__(self, varname, target, prop):
        super().__init__(varname)
        self.target = target
        self.prop = prop

    def apply(self, driver):
        pose_driver_utils.add_idprop_variable(driver, self.varname, self.target, self.prop)

class FrameDeltaVariable(DriverVariable):
    def __init__(self, varname, target):
        super().__init__(varname)
        self.target = target

    def apply(self, driver):
        pose_driver_utils.add_idprop_variable(driver, self.varname, self.target, _frame_delta_prop)


def bound_expression(expr, vars):
    return expr.format(*[v.varname for v in vars])

def make_prop_driver(target, prop, index, expression, variables, use_self=False):
    assert len(expression) <= max_expr_len, "Driver expression length exceeded: " + expression
    driver = pose_driver_utils.add_prop_driver(target, prop, index)
    driver.use_self = use_self
    driver.expression = bound_expression(expression, variables)
    for v in variables:
        v.apply(driver)

def make_idprop_driver(target, prop, expression, variables, use_self=False):
    assert len(expression) <= max_expr_len, "Driver expression length exceeded: " + expression
    driver = pose_driver_utils.add_idprop_driver(target, prop)
    driver.use_self = use_self
    driver.expression = bound_expression(expression, variables)
    for v in variables:
        v.apply(driver)


class GearDescriptor:
    def __init__(self, obj, name, axis):
        self.pose_bone = obj.pose.bones.get(name)
        self.axis = axis

    def __add_speed_prop(self):
        pose_driver_utils.add_idprop(self.pose_bone, _speed_prop, 0.0, -1000000.0, 1000000)

    def __add_rotation_driver(self, sources):
        axis_names = ['x', 'y', 'z']
        expr = "self.rotation_euler.{}+dt*spd if frame>1 else 0".format(axis_names[self.axis])
        vars = [
            FrameDeltaVariable('dt', self.pose_bone.id_data),
            IDPropVariable('spd', self.pose_bone, _speed_prop),
            ]
        use_self_var = True

        num_sources = len(sources)
        for i, s in enumerate(reversed(sources)):
            if len(s) == 3:
                source, ratio, source_count = s
                condition = None
            elif len(s) == 4:
                source, ratio, source_count, condition = s
            else:
                assert(false)

            if source_count == 0:
                continue

            scope = str(num_sources - i)

            # NOTE: driver expression length is quite limited (256 chars), so to avoid exceeding the char limit
            # we store intermediate rotation values in extra id props
            tmp_prop = "aligned_rotation{}".format(scope)
            pose_driver_utils.add_idprop(self.pose_bone, tmp_prop, 0.0, -1000000.0, 1000000)

            make_idprop_driver(self.pose_bone, tmp_prop, expr, vars, use_self=use_self_var)

            # User variable to control phase between gears
            _phase_prop = "phase{}".format(scope)
            pose_driver_utils.add_idprop(self.pose_bone, _phase_prop, 0.0, 0.0, 1.0)

            tmpvar = "tmp{}".format(scope)
            rot_sourcevar = "src{}".format(scope)
            phasevar = "phase{}".format(scope)
            target_count = source_count / ratio

            # Expression to align the rotation angle between two gears
            expr = "2*pi*(round(({rot_target})/pi*.5*{teeth_target}-{rot_source}/pi*.5*{teeth_source}-{phase})+{phase})/{teeth_target}+{rot_source}*{ratio}".format(
                rot_target=tmpvar, teeth_target=target_count, rot_source=rot_sourcevar, teeth_source=source_count, phase=phasevar, ratio=ratio
                )
            vars = [
                IDPropVariable(tmpvar, self.pose_bone, tmp_prop),
                RotationVariable(rot_sourcevar, source.pose_bone, source.axis),
                IDPropVariable(phasevar, self.pose_bone, _phase_prop),
                ]
            use_self_var = False

            if condition:
                for v in condition.variables:
                    v.set_scope(str(scope))
                vars.extend(condition.variables)
                cond_expr = bound_expression(condition.expression, condition.variables)
                expr = "({}) if ({}) else ({})".format(expr, cond_expr, tmpvar)
        
        self.pose_bone.rotation_mode = 'XYZ'
        make_prop_driver(self.pose_bone, 'rotation_euler', self.axis, expr, vars, use_self=use_self_var)

    def clear_drivers(self):
        pose_driver_utils.clear_drivers(self.pose_bone)

    def set_const_rotation(self, rpf):
        self.__add_speed_prop()
        self.__add_rotation_driver([])
        pose_driver_utils.set_idprop(self.pose_bone, _speed_prop, rpf * 2*pi)
 
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
    def add_transmission(self, sources):
        self.__add_speed_prop()
        self.__add_rotation_driver(sources)

        expr = ".0"
        vars = []

        num_sources = len(sources)
        for i, s in enumerate(reversed(sources)):
            if len(s) == 3:
                source, ratio, source_count = s
                condition = None
            elif len(s) == 4:
                source, ratio, source_count, condition = s
            else:
                assert(false)

            scope = str(num_sources - i)

            speed_sourcevar = IDPropVariable("src", source.pose_bone, _speed_prop)
            speed_sourcevar.set_scope(scope)
            vars.append(speed_sourcevar)

            if condition:
                for v in condition.variables:
                    v.set_scope(scope)
                vars.extend(condition.variables)

                cond_expr = bound_expression(condition.expression, condition.variables)
                expr = "{}*{} if ({}) else ({})".format(speed_sourcevar.varname, ratio, cond_expr, expr)
            else:
                expr = "{}*{}".format(speed_sourcevar.varname, ratio)

        make_idprop_driver(self.pose_bone, _speed_prop, expr, vars)


class ConditionDescriptor:
    def __init__(self, expression, variables):
        self.expression = expression
        self.variables = variables


def _clear_frame_drivers(obj):
    if not obj.animation_data:
        return
    varnames = set('["{}"]'.format(name) for name in [_frame_prev_prop, _frame_delta_prop])
    for d in obj.animation_data.drivers:
        if d.data_path in varnames:
            obj.animation_data.drivers.remove(d)

# Add a property for the previous frame value
def add_frame_prev_property(obj, scene):
    _clear_frame_drivers(obj)

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

    obj[_frame_delta_prop] = 0.0
    obj[_frame_prev_prop] = scene.frame_current

    make_idprop_driver(obj, _frame_delta_prop, "frame - self['{}']".format(_frame_prev_prop), variables=[], use_self=True)

    # Dummy variable to enforce a dependency and make sure that prev_frame is updated AFTER the delta
    make_idprop_driver(obj, _frame_prev_prop, "frame", variables=[IDPropVariable('delta', obj, _frame_delta_prop)])
