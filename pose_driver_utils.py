import bpy
from math import *

driver_axis_types = ['ROT_X', 'ROT_Y', 'ROT_Z']

class PropertyNamespace:
    def __init__(self, prefix):
        self.prefix = prefix

    def is_prefix_data_path(self, data_path):
        if data_path.endswith(']'):
            path_from_id, sep, propstr = data_path.rpartition('[')
            if sep:
                return propstr[1:].startswith(self.prefix)
        else:
            path_from_id, sep, propstr = data_path.rpartition('.')
            if sep:
                return propstr.startswith(self.prefix)
            else:
                return data_path.startswith(self.prefix)
        return False

    @staticmethod
    def is_transform_data_path(data, data_path):
        transform_paths = [
            data.path_from_id("location"),
            data.path_from_id("rotation_axis_angle"),
            data.path_from_id("rotation_euler"),
            data.path_from_id("rotation_quaternion"),
            data.path_from_id("scale"),
        ]
        return any(data_path.startswith(tp) for tp in transform_paths)

    def clear_id_drivers(self, data : bpy.types.ID):
        anim_data = data.animation_data
        if anim_data:
            for d in anim_data.drivers:
                if not d.lock and self.is_prefix_data_path(d.data_path):
                    anim_data.drivers.remove(d)

    def clear_bone_drivers(self, data : bpy.types.PoseBone, clear_transform = True):
        anim_data = data.id_data.animation_data
        path_from_id = data.path_from_id()
        if anim_data:
            for d in anim_data.drivers:
                if not d.lock and d.data_path.startswith(path_from_id) and (self.is_prefix_data_path(d.data_path) or self.is_transform_data_path(data, d.data_path)):
                    anim_data.drivers.remove(d)

    def clear_id_properties(self, data : bpy.types.ID):
        rna_ui = data.get("_RNA_UI")
        for key, value in data.items():
            if key.startswith(self.prefix):
                if rna_ui and (key in rna_ui):
                    del rna_ui[key]
                del data[key]

    def clear_bone_properties(self, data : bpy.types.PoseBone):
        rna_ui = data.get("_RNA_UI")
        for key, value in data.items():
            if key.startswith(self.prefix):
                if rna_ui and (key in rna_ui):
                    del rna_ui[key]
                del data[key]


    # XXX Using the same id property name for different bones can cause dependency cycles,
    # because the depsgraph does not distinguish the different bone names.
    # Prefixing with the bone name avoids the problem
    def idprop_uuid(self, target, name):
        if isinstance(target, bpy.types.PoseBone):
            return self.prefix + target.name + "_" + name
        else:
            return self.prefix + name

    @classmethod
    def add_prop_driver(cls, target, prop, index=0):
        obj = target.id_data
        if not obj.animation_data:
            obj.animation_data_create()
        data_path = target.path_from_id(prop)
        fcurve = obj.animation_data.drivers.new(data_path, index=index)
        fcurve.driver.type = 'SCRIPTED'
        return fcurve.driver

    @classmethod
    def add_rotation_variable(cls, driver, target, target_axis):
        var = driver.variables.new()
        var.type = 'TRANSFORMS'

        tar = var.targets[0]
        tar.id = driver.id_data
        tar.bone_target = target.name
        tar.transform_type = driver_axis_types[target_axis]
        tar.transform_space = 'TRANSFORM_SPACE'
        tar.rotation_mode = 'AUTO'

        return var

    @classmethod
    def add_rotation_driver(cls, target, axis):
        target.rotation_mode = 'XYZ'
        return cls.add_prop_driver(target, "rotation_euler", axis)


    @staticmethod
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

    def add_idprop(self, target, prop, value, min, max):
        prop = self.idprop_uuid(target, prop)
        if target.get(prop) is None:
            target[prop] = value
        if target.get("_RNA_UI") is None:
            target["_RNA_UI"] = {}
        target["_RNA_UI"][prop] = { "default":value, "min":min, "max":max }

    def set_idprop(self, target, prop, value):
        prop = self.idprop_uuid(target, prop)
        if not prop in target.keys():
            raise Exception("ID property {} undefined".format(prop))
            return
        target[prop] = value

    def add_idprop_driver(self, target, prop):
        obj = target.id_data
        if not obj.animation_data:
            obj.animation_data_create()
        prop = self.idprop_uuid(target, prop)
        if isinstance(target, bpy.types.ID):
            data_path = '["{}"]'.format(prop)
        else:
            data_path = target.path_from_id() + '["{}"]'.format(prop)
        fcurve = obj.animation_data.drivers.new(data_path)
        fcurve.driver.type = 'SCRIPTED'
        return fcurve.driver

    def add_idprop_variable(self, driver, target, target_prop):
        var = driver.variables.new()
        var.type = 'SINGLE_PROP'

        tar = var.targets[0]
        tar.id_type = self._find_id_type(target)
        tar.id = driver.id_data
        propname = self.idprop_uuid(target, target_prop)
        if isinstance(target, bpy.types.PoseBone):
            tar.data_path = 'pose.bones["{}"]["{}"]'.format(target.name, propname)
        else:
            tar.data_path = '["{}"]'.format(propname)

        return var