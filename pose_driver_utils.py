import bpy
from math import *

driver_axis_types = ['ROT_X', 'ROT_Y', 'ROT_Z']


def clear_drivers(target):
    obj = target.id_data
    if not obj.animation_data:
        return
    if not isinstance(target, bpy.types.ID):
        base_path = target.path_from_id()
        for d in obj.animation_data.drivers:
            if d.data_path.startswith(base_path):
                obj.animation_data.drivers.remove(d)

def add_prop_driver(target, prop, index=0):
    obj = target.id_data
    if not obj.animation_data:
        obj.animation_data_create()
    data_path = target.path_from_id(prop)
    fcurve = obj.animation_data.drivers.new(data_path, index=index)
    fcurve.driver.type = 'SCRIPTED'
    return fcurve.driver

def add_rotation_variable(driver, varname, target, target_axis):
    var = driver.variables.new()
    var.name = varname
    var.type = 'TRANSFORMS'

    tar = var.targets[0]
    tar.id = driver.id_data
    tar.bone_target = target.name
    tar.transform_type = driver_axis_types[target_axis]
    tar.transform_space = 'TRANSFORM_SPACE'
    tar.rotation_mode = 'AUTO'


# XXX Using the same id property name for different bones can cause dependency cycles,
# because the depsgraph does not distinguish the different bone names.
# Prefixing with the bone name avoids the problem
def _idprop_uuid(target, name):
    if isinstance(target, bpy.types.PoseBone):
        return target.name + "_" + name
    else:
        return name

def _find_id_type(target):
    # TODO add more ID types as needed
    id_map = {
        bpy.types.Object : 'OBJECT',
        bpy.types.Scene : 'SCENE',
    }
    for key, value in id_map.items():
        if isinstance(target.id_data, key):
            return value
    assert(False)

def add_idprop(target, prop, value, min, max):
    prop = _idprop_uuid(target, prop)
    if target.get(prop) is None:
        target[prop] = value
    if target.get("_RNA_UI") is None:
        target["_RNA_UI"] = {}
    target["_RNA_UI"][prop] = { "default":value, "min":min, "max":max }

def set_idprop(target, prop, value):
    prop = _idprop_uuid(target, prop)
    target[prop] = value

def add_idprop_driver(target, prop):
    obj = target.id_data
    if not obj.animation_data:
        obj.animation_data_create()
    prop = _idprop_uuid(target, prop)
    if isinstance(target, bpy.types.ID):
        data_path = '["{}"]'.format(prop)
    else:
        data_path = target.path_from_id() + '["{}"]'.format(prop)
    fcurve = obj.animation_data.drivers.new(data_path)
    fcurve.driver.type = 'SCRIPTED'
    return fcurve.driver

def add_idprop_variable(driver, varname, target, target_prop):
    var = driver.variables.new()
    var.name = varname
    var.type = 'SINGLE_PROP'

    tar = var.targets[0]
    tar.id_type = _find_id_type(target)
    tar.id = driver.id_data
    propname = _idprop_uuid(target, target_prop)
    if isinstance(target, bpy.types.PoseBone):
        tar.data_path = 'pose.bones["{}"]["{}"]'.format(target.name, propname)
    else:
        tar.data_path = '["{}"]'.format(propname)
