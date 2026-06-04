"""
Grasshopper Python component parameter setup helpers.

These helpers are intentionally tiny and defensive. Paste/run scripts can call
`ensure_io(...)` to add missing inputs/outputs and rename existing ones.
"""

from __future__ import annotations


def ensure_io(ghenv, inputs, outputs):
    """Ensure a Grasshopper Python component has named inputs and outputs.

    `inputs` and `outputs` are sequences of `(name, type_name, access)` tuples.
    Supported type_name values: generic, number, string, boolean, brep, curve,
    point. Supported access values: item, list.
    """

    try:
        import Grasshopper.Kernel as ghk
        import Grasshopper.Kernel.Parameters as ghp
    except Exception:
        return False

    if ghenv is None:
        return False

    component = ghenv.Component
    changed = False
    script_prototype = _find_script_param_prototype(component)

    while component.Params.Input.Count < len(inputs):
        spec = inputs[component.Params.Input.Count]
        name, type_name, access = spec[:3]
        try:
            component.Params.RegisterInputParam(
                _make_param(
                    ghp,
                    ghk,
                    name,
                    type_name,
                    access,
                    _is_optional(spec),
                    script_prototype,
                )
            )
            changed = True
        except Exception:
            break

    while component.Params.Output.Count < len(outputs):
        name, type_name, access = outputs[component.Params.Output.Count][:3]
        try:
            component.Params.RegisterOutputParam(
                _make_param(ghp, ghk, name, type_name, access, False, script_prototype)
            )
            changed = True
        except Exception:
            break

    while component.Params.Input.Count > len(inputs):
        param = _safe_param_at(component.Params.Input, component.Params.Input.Count - 1)
        if param is None:
            break
        try:
            component.Params.UnregisterInputParameter(param, True)
            changed = True
        except Exception:
            break

    while component.Params.Output.Count > len(outputs):
        param = _safe_param_at(component.Params.Output, component.Params.Output.Count - 1)
        if param is None:
            break
        try:
            component.Params.UnregisterOutputParameter(param, True)
            changed = True
        except Exception:
            break

    for index, spec in enumerate(inputs):
        param = _safe_param_at(component.Params.Input, index)
        if param is None:
            changed = True
            continue
        if not _is_script_variable_param(param):
            _replace_input_param(component, ghp, ghk, index, spec, script_prototype)
            changed = True
        else:
            changed = _apply_param_spec(param, spec) or changed

    for index, spec in enumerate(outputs):
        param = _safe_param_at(component.Params.Output, index)
        if param is None:
            changed = True
            continue
        if not _is_script_variable_param(param):
            _replace_output_param(component, ghp, ghk, index, spec, script_prototype)
            changed = True
        else:
            changed = _apply_param_spec(param, spec) or changed

    if changed:
        _commit_param_changes(component, expire=False)

    return changed


def io_matches(ghenv, inputs, outputs):
    """Return True when current component params already match the schema."""

    if ghenv is None:
        return False

    component = ghenv.Component
    if component.Params.Input.Count != len(inputs):
        return False
    if component.Params.Output.Count != len(outputs):
        return False

    for index, spec in enumerate(inputs):
        param = _safe_param_at(component.Params.Input, index)
        if param is None or not _param_matches(param, spec):
            return False

    for index, spec in enumerate(outputs):
        param = _safe_param_at(component.Params.Output, index)
        if param is None or not _param_matches(param, spec):
            return False

    return True


def schedule_ensure_io(ghenv, inputs, outputs):
    """Run ensure_io after the current solution to avoid RhinoCode index errors."""

    if ghenv is None:
        return False

    component = ghenv.Component
    document = component.OnPingDocument()
    if document is None:
        return ensure_io(ghenv, inputs, outputs)

    def callback(_document):
        """Helper for callback in gh component setup."""
        try:
            changed = ensure_io(ghenv, inputs, outputs)
            if changed and io_matches(ghenv, inputs, outputs):
                component.ExpireSolution(False)
        except Exception:
            pass

    try:
        document.ScheduleSolution(1, callback)
        return True
    except Exception:
        return ensure_io(ghenv, inputs, outputs)


def _apply_param_spec(param, spec):
    """Apply a parameter, load, or transformation to the current object."""
    name, type_name, access = spec[:3]
    changed = False

    if param.Name != name:
        param.Name = name
        changed = True
    if param.NickName != name:
        param.NickName = name
        changed = True
    if param.Description != name and not str(param.Description).startswith(
        "{} [type:".format(name)
    ):
        param.Description = name
        changed = True

    try:
        import Grasshopper.Kernel as ghk

        desired_access = _access(ghk, access)
        if param.Access != desired_access:
            param.Access = desired_access
            changed = True
    except Exception:
        pass

    try:
        desired_optional = _is_optional(spec)
        if param.Optional != desired_optional:
            param.Optional = desired_optional
            changed = True
    except Exception:
        pass

    changed = _apply_type_hint(param, type_name) or changed

    return changed


def _param_matches(param, spec):
    """Helper for param matches in gh component setup."""
    if not _is_script_variable_param(param):
        return False

    name, type_name, access = spec[:3]
    if param.Name != name:
        return False
    if param.NickName != name:
        return False

    try:
        import Grasshopper.Kernel as ghk

        if param.Access != _access(ghk, access):
            return False
    except Exception:
        pass

    try:
        if param.Optional != _is_optional(spec):
            return False
    except Exception:
        pass

    return True


def _make_param(ghp, ghk, name, type_name, access, optional=False, prototype=None):
    """Create a helper object used by the current workflow."""
    param = None
    if prototype is not None:
        try:
            import System

            param = System.Activator.CreateInstance(prototype.GetType())
        except Exception:
            param = None

    if param is None:
        param = _make_script_variable_param()

    if param is None:
        param = ghp.Param_GenericObject()

    param.Name = name
    param.NickName = name
    param.Description = name
    param.Access = _access(ghk, access)
    try:
        param.Optional = optional
    except Exception:
        pass
    _apply_type_hint(param, type_name)
    return param


def _replace_input_param(component, ghp, ghk, index, spec, prototype):
    """Return or install a replacement object while preserving required metadata."""
    name, type_name, access = spec[:3]
    sources = []
    old_param = _safe_param_at(component.Params.Input, index)
    if old_param is None:
        return
    try:
        sources = list(old_param.Sources)
    except Exception:
        pass
    component.Params.UnregisterInputParameter(old_param, True)
    param = _make_param(ghp, ghk, name, type_name, access, _is_optional(spec), prototype)
    component.Params.RegisterInputParam(param, _bounded_insert_index(component.Params.Input, index))
    for source in sources:
        try:
            param.AddSource(source)
        except Exception:
            pass


def _replace_output_param(component, ghp, ghk, index, spec, prototype):
    """Return or install a replacement object while preserving required metadata."""
    name, type_name, access = spec[:3]
    old_param = _safe_param_at(component.Params.Output, index)
    if old_param is None:
        return
    component.Params.UnregisterOutputParameter(old_param, True)
    param = _make_param(ghp, ghk, name, type_name, access, False, prototype)
    component.Params.RegisterOutputParam(param, _bounded_insert_index(component.Params.Output, index))


def _is_script_variable_param(param):
    """Return True when the value matches this internal predicate."""
    try:
        return param.GetType().FullName == "RhinoCodePluginGH.Parameters.ScriptVariableParam"
    except Exception:
        return False


def _find_script_param_prototype(component):
    """Find a matching item in the current Rhino or Grasshopper context."""
    for group in (component.Params.Input, component.Params.Output):
        for index in range(int(group.Count)):
            param = _safe_param_at(group, index)
            if _is_script_variable_param(param):
                return param
    return None


def _safe_param_at(group, index):
    """Safely access a value that may be absent in Grasshopper/Rhino runtime."""
    try:
        if index < 0 or index >= group.Count:
            return None
        return group[index]
    except Exception:
        return None


def _bounded_insert_index(group, index):
    """Clamp an index or value to the valid runtime range."""
    try:
        if index < 0:
            return 0
        if index > group.Count:
            return group.Count
        return index
    except Exception:
        return 0


def _make_script_variable_param():
    """Create a helper object used by the current workflow."""
    try:
        import System

        type_name = "RhinoCodePluginGH.Parameters.ScriptVariableParam, RhinoCodePluginGH"
        param_type = System.Type.GetType(type_name)
        if param_type is not None:
            return System.Activator.CreateInstance(param_type)
    except Exception:
        pass
    return None


def _is_optional(spec):
    """Return True when the value matches this internal predicate."""
    if len(spec) >= 4:
        return bool(spec[3])
    return spec[0] != "script_path"


def _apply_type_hint(param, type_name):
    """Best-effort Rhino 8 ScriptVariableParam type hint setter."""

    desired = _canonical_type_name(type_name)
    changed = False

    # RhinoCode ScriptVariableParam builds have changed names for this field.
    # Try common public property names first.
    for property_name in (
        "TypeHint",
        "TypeHintName",
        "Hint",
        "HintName",
        "VariableType",
        "ScriptVariableType",
    ):
        try:
            current = getattr(param, property_name)
        except Exception:
            continue

        for value in _type_hint_values(desired):
            try:
                if str(current) != str(value):
                    setattr(param, property_name, value)
                    changed = True
                param.Description = _description_with_type(param.Description, desired)
                return changed
            except Exception:
                continue

    # Try common setter methods.
    for method_name in (
        "SetTypeHint",
        "SetHint",
        "SetVariableType",
        "UpdateTypeHint",
    ):
        method = getattr(param, method_name, None)
        if method is None:
            continue
        for value in _type_hint_values(desired):
            try:
                method(value)
                param.Description = _description_with_type(param.Description, desired)
                return True
            except Exception:
                continue

    # Last real attempt: RhinoCode builds sometimes expose internal-looking
    # writable properties with names that include Hint/Type/DataType.
    for property_name in _reflected_type_hint_property_names(param):
        try:
            current = getattr(param, property_name)
        except Exception:
            continue
        for value in _type_hint_values(desired):
            try:
                if str(current) != str(value):
                    setattr(param, property_name, value)
                    changed = True
                param.Description = _description_with_type(param.Description, desired)
                return changed
            except Exception:
                continue

    # Fallback marker lets our own matcher know the desired type changed even
    # on Rhino builds where the real type-hint API is not public.
    try:
        param.Description = _description_with_type(param.Description, desired)
        return True
    except Exception:
        return changed


def _type_hint_matches(param, type_name):
    """Return type-hint metadata for Grasshopper parameter setup."""
    desired = _canonical_type_name(type_name)

    for property_name in (
        "TypeHint",
        "TypeHintName",
        "Hint",
        "HintName",
        "VariableType",
        "ScriptVariableType",
    ):
        try:
            current = getattr(param, property_name)
            if _canonical_type_name(str(current)) == desired:
                return True
        except Exception:
            pass

    try:
        return "[type:{}]".format(desired) in param.Description
    except Exception:
        return True


def _canonical_type_name(type_name):
    """Normalize a name to the canonical internal representation."""
    value = str(type_name or "generic").lower()
    aliases = {
        "float": "number",
        "double": "number",
        "int": "number",
        "integer": "number",
        "num": "number",
        "str": "string",
        "text": "string",
        "bool": "boolean",
        "brep": "brep",
        "surface": "brep",
        "curve": "curve",
        "point": "point",
        "point3d": "point",
        "mesh": "mesh",
        "generic": "generic",
        "object": "generic",
    }
    return aliases.get(value, value)


def _type_hint_values(type_name):
    """Return type-hint metadata for Grasshopper parameter setup."""
    values = [type_name]
    try:
        import System
        import Rhino.Geometry as rg

        system_types = {
            "number": System.Double,
            "string": System.String,
            "boolean": System.Boolean,
            "brep": rg.Brep,
            "curve": rg.Curve,
            "point": rg.Point3d,
            "mesh": rg.Mesh,
            "generic": System.Object,
        }
        if type_name in system_types:
            values.append(system_types[type_name])
    except Exception:
        pass
    return values


def _reflected_type_hint_property_names(param):
    """Helper for reflected type hint property names in gh component setup."""
    names = []
    try:
        properties = param.GetType().GetProperties()
    except Exception:
        return names

    accepted_fragments = (
        "hint",
        "paramtype",
        "valuetype",
        "datatype",
        "variabletype",
        "scriptvariabletype",
    )
    rejected_names = (
        "GetType",
        "ObjectType",
        "TypeName",
    )

    for prop in properties:
        try:
            name = prop.Name
            lower = name.lower()
            if name in rejected_names:
                continue
            if not prop.CanWrite:
                continue
            if any(fragment in lower for fragment in accepted_fragments):
                names.append(name)
        except Exception:
            pass
    return names


def _description_with_type(description, type_name):
    """Build a Grasshopper parameter description string."""
    base = description or ""
    marker_start = " [type:"
    if marker_start in base:
        base = base[: base.index(marker_start)]
    return "{} [type:{}]".format(base, type_name)


def _commit_param_changes(component, expire):
    """Commit changed Grasshopper parameters to the component runtime."""
    try:
        component.Params.OnParametersChanged()
    except Exception:
        pass

    for method_name in (
        "VariableParameterMaintenance",
        "AttributesChanged",
        "OnDisplayExpired",
    ):
        try:
            method = getattr(component, method_name, None)
            if method is not None:
                method()
        except Exception:
            pass

    try:
        component.Params.RepairParamAssociations()
    except Exception:
        pass

    try:
        component.Attributes.ExpireLayout()
    except Exception:
        pass

    try:
        component.Attributes.PerformLayout()
    except Exception:
        pass

    if expire:
        try:
            component.ExpireSolution(True)
        except Exception:
            pass


def _access(ghk, access):
    """Helper for access in gh component setup."""
    if access == "list":
        return ghk.GH_ParamAccess.list
    return ghk.GH_ParamAccess.item


# --- Value-list (drop-down) helpers ---------------------------------------
# Attach a GH_ValueList drop-down to inputs that have no source, so the user
# picks from predefined options instead of typing. Idempotent and fully
# defensive: any failure leaves the component working without the drop-down.


def schedule_value_lists(ghenv, specs):
    """Attach a drop-down (GH_ValueList) to inputs that currently have no source.

    ``specs`` is a list of ``(target, items)`` where ``target`` is an input name
    (str) or index (int) and ``items`` is a list of ``(display, expression)``
    pairs (expression is the GH value, e.g. ``'"RU"'`` for text or ``'1'`` for a
    number). An input that already has a non-value-list source is left alone; a
    value list we previously made is refreshed only when its items differ.
    Returns True when work was scheduled (so the caller can avoid reporting an
    "empty input" error). Runs the change after the current solution.
    """

    if ghenv is None:
        return False
    try:
        import Grasshopper  # noqa: F401  (presence check)
    except Exception:
        return False

    component = ghenv.Component
    document = component.OnPingDocument()
    if document is None:
        return False

    # Decide synchronously what needs doing - this prevents reschedule loops.
    pending = []
    for target, items in specs:
        param = _resolve_input_param(component, target)
        if param is None or not items:
            continue
        if _value_list_state(param, items) in ("create", "update"):
            pending.append((target, list(items)))
    if not pending:
        return False

    def callback(_document):
        """Attach/refresh the value lists once the solution has finished."""
        try:
            for target, items in pending:
                param = _resolve_input_param(component, target)
                if param is not None:
                    _attach_or_update_value_list(param, items, _document)
            component.ExpireSolution(False)
        except Exception:
            pass

    try:
        document.ScheduleSolution(1, callback)
        return True
    except Exception:
        return False


def value_list_items(values, as_string):
    """Turn plain values into ``(display, expression)`` pairs for a value list."""

    items = []
    for value in values:
        text = str(value)
        expression = '"{}"'.format(text) if as_string else text
        items.append((text, expression))
    return items


def _resolve_input_param(component, target):
    try:
        group = component.Params.Input
        if isinstance(target, int):
            return _safe_param_at(group, target)
        for index in range(int(group.Count)):
            param = _safe_param_at(group, index)
            if param is not None and param.Name == target:
                return param
    except Exception:
        return None
    return None


def _existing_value_list(param):
    try:
        for source in param.Sources:
            if type(source).__name__ == "GH_ValueList":
                return source
    except Exception:
        pass
    return None


def _value_list_state(param, items):
    """'create' (no source), 'update' (our list differs), or 'skip'."""
    try:
        if int(param.SourceCount) > 0:
            value_list = _existing_value_list(param)
            if value_list is None:
                return "skip"  # the user wired something else - never override it
            return "skip" if _value_list_items_match(value_list, items) else "update"
    except Exception:
        return "skip"
    return "create"


def _value_list_items_match(value_list, items):
    try:
        existing = list(value_list.ListItems)
        if len(existing) != len(items):
            return False
        for got, (display, expression) in zip(existing, items):
            if str(got.Name) != str(display) or str(got.Expression) != str(expression):
                return False
        return True
    except Exception:
        return False


def _attach_or_update_value_list(param, items, document):
    try:
        from Grasshopper.Kernel.Special import GH_ValueList, GH_ValueListItem
    except Exception:
        return

    value_list = _existing_value_list(param)
    created = False
    if value_list is None:
        try:
            if int(param.SourceCount) > 0:
                return  # non-value-list source present; do not override
        except Exception:
            return
        value_list = GH_ValueList()
        created = True

    try:
        value_list.ListItems.Clear()
        for display, expression in items:
            value_list.ListItems.Add(GH_ValueListItem(str(display), str(expression)))
        try:
            value_list.NickName = param.Name
        except Exception:
            pass
        value_list.SelectItem(0)
    except Exception:
        return

    if created:
        try:
            value_list.CreateAttributes()
            import System.Drawing as _sd

            pivot = param.Attributes.Pivot
            value_list.Attributes.Pivot = _sd.PointF(float(pivot.X) - 230.0, float(pivot.Y) - 10.0)
        except Exception:
            pass
        try:
            document.AddObject(value_list, False)
            param.AddSource(value_list)
        except Exception:
            return

    try:
        value_list.ExpireSolution(True)
    except Exception:
        pass
