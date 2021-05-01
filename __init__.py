# MIT License
#
# Copyright (c) 2021 Lukas Toenne
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

bl_info = {
    "name": "Gear Sim",
    "author": "Lukas Toenne",
    "version": (0, 1),
    "blender": (2, 92, 0),
    "location": "",
    "description": "Set up drivers and properties to simulate geared mechanisms",
    "warning": "",
    "doc_url": "",
    "category": "Object",
}

import bpy
from . import pose_driver_utils, node_value, node_tree, nodes, builder

if "bpy" in locals():
    import importlib
    importlib.reload(pose_driver_utils)
    importlib.reload(node_value)
    importlib.reload(node_tree)
    importlib.reload(nodes)
    importlib.reload(builder)

def register():
    node_tree.register()

def unregister():
    node_tree.unregister()

if __name__ == "__main__":
    register()
