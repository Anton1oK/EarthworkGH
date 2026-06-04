"""
Generic Grasshopper Python 3 dynamic loader template.

Paste this file into one Rhino 8 Grasshopper Python 3 component. Connect a
File Path parameter to the component's first/default input and point it at an
external component script - one of the scripts in gh_components/, or the
example_component.py at the repository root.

The external script declares COMPONENT_INPUTS and COMPONENT_OUTPUTS. This
loader reads those declarations, updates the Grasshopper sockets, then executes
the external file. Editing the external file and recomputing Grasshopper updates
the component behavior without reopening the Grasshopper script editor.
"""

from __future__ import annotations

import ast
import importlib
import os
import sys


# Set this to the folder that contains this loader, gh_component_setup.py, and
# your external component scripts. Absolute file paths also work without it.
PROJECT_FOLDER = r"CHANGE_ME_TO_YOUR_PROJECT_FOLDER"

if PROJECT_FOLDER and PROJECT_FOLDER not in sys.path:
    sys.path.append(PROJECT_FOLDER)

import gh_component_setup

gh_component_setup = importlib.reload(gh_component_setup)


def _candidate_script_path():
    """Resolve the external component script path from the first GH input."""

    value = globals().get("script_path", None)
    if value is None:
        value = globals().get("x", None)
    if value is None:
        value = _first_input_value()
    if value is None:
        raise ValueError("Connect a Grasshopper File Path to the first input.")

    path = str(value)
    if path.startswith('"') and path.endswith('"'):
        path = path[1:-1]
    if not os.path.isabs(path):
        if not PROJECT_FOLDER or PROJECT_FOLDER.startswith("CHANGE_ME"):
            raise ValueError(
                "Use an absolute script path or set PROJECT_FOLDER in the loader."
            )
        path = os.path.join(PROJECT_FOLDER, path)
    if not os.path.exists(path):
        raise ValueError("Script file does not exist: {}".format(path))
    return path


def _first_input_value():
    """Read first GH input directly, independent of Python variable binding."""

    if "ghenv" not in globals():
        return None

    try:
        component = ghenv.Component
        if component.Params.Input.Count < 1:
            return None
        volatile_data = component.Params.Input[0].VolatileData
        for branch_index in range(volatile_data.BranchCount):
            branch = volatile_data.get_Branch(branch_index)
            if branch is None or branch.Count == 0:
                continue
            item = branch[0]
            return getattr(item, "Value", item)
    except Exception:
        return None

    return None


def _component_spec(path):
    """Read external component schema and source code."""

    with open(path, "r", encoding="utf-8") as file:
        source = file.read()

    inputs = None
    outputs = None
    tree = ast.parse(source, filename=path)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "COMPONENT_INPUTS":
                inputs = ast.literal_eval(node.value)
            if isinstance(target, ast.Name) and target.id == "COMPONENT_OUTPUTS":
                outputs = ast.literal_eval(node.value)

    if inputs is None or outputs is None:
        raise ValueError(
            "External script must define COMPONENT_INPUTS and COMPONENT_OUTPUTS."
        )

    return tuple(inputs), tuple(outputs), source


def _set_component_label(path):
    """Set the Grasshopper component label to the loaded script name."""

    if "ghenv" not in globals():
        return
    label = os.path.splitext(os.path.basename(path))[0]
    component = ghenv.Component
    component.Name = label
    component.NickName = label
    component.Message = label


def _execute_external(path, source, output_specs):
    """Execute the selected external component and copy declared outputs."""

    env = dict(globals())
    env["__file__"] = path
    env["__name__"] = "__grasshopper_external_component__"

    code = compile(source, path, "exec")
    exec(code, env)

    for name, _type_name, _access in output_specs:
        globals()[name] = env.get(name, None)


script_path_value = _candidate_script_path()
component_inputs, component_outputs, component_source = _component_spec(script_path_value)
_set_component_label(script_path_value)

loader_inputs = (("script_path", "string", "item"),) + tuple(component_inputs)
loader_outputs = tuple(component_outputs) + (
    ("loader_status", "string", "item"),
    ("loader_schema", "string", "item"),
)
loader_schema = "{} inputs / {} outputs from {}".format(
    len(loader_inputs),
    len(loader_outputs),
    os.path.basename(script_path_value),
)

changed = False
if "ghenv" in globals():
    if gh_component_setup.io_matches(
        ghenv,
        inputs=loader_inputs,
        outputs=loader_outputs,
    ):
        changed = False
    else:
        changed = gh_component_setup.schedule_ensure_io(
            ghenv,
            inputs=loader_inputs,
            outputs=loader_outputs,
        )

if not changed:
    _execute_external(script_path_value, component_source, component_outputs)
    loader_status = "Loaded {}".format(os.path.basename(script_path_value))
else:
    loader_status = "Updated IO for {}".format(os.path.basename(script_path_value))
