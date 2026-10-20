# -*- coding: utf-8 -*-
"""Core attribute autofill logic for the QGIS Attribute Auto-Fill plugin.

Copyright (C) 2026 Amlan Patnaik.
"""
from qgis.core import (QgsProject, QgsField, QgsFeature, QgsGeometry,
                       QgsSpatialIndex, QgsCoordinateTransform)
from qgis.PyQt.QtCore import QVariant

FDA_LAYER_NAME = "FDA Boundaries"
FDA_ID_FIELD = "infinium_id"
FDA_CATEGORY_FIELD = "category"
HUB_FIELD_NAME = "hub_number"

STATIC_RULES = {
    "Equipment": [("mounttype", "Handhole"), ("physical_status", "New Build"),
                  ("type", "DTC"), ("size", "2"), ("category", "F2")],
    "Slackloop": [("cable_length", 30), ("category", "F2")],
    "Splice Closure": [("case_size", "450A"), ("mounttype", "Handhole"),
                       ("type", "MCA"), ("physical_status", "New Build"),
                       ("category", "F2")],
    "Structures": [("physical_status", "New Build"), ("category", "F2")],
    "Span": [("install_me", "Dir Bore"), ("size", '2"'),
             ("install_type", "Underground"), ("category", "F2"),
             ("count", "1")],
    "Fiber Cable": [("placementtype", "Underground"),
                    ("physical_status", "New Build"),
                    ("inventory_status", "Planned")],
    "Labor Units": [("type", "Bore Pit"), ("category", "F2")],
}


def norm(value):
    if value is None:
        return ""
    try:
        if hasattr(value, "isNull") and value.isNull():
            return ""
    except Exception:
        pass
    text = str(value).strip()
    return "" if text.casefold() in ("", "null", "none") else text.casefold()


def is_blank(value):
    return norm(value) == ""


def canonical_layer_name(name):
    clean = " ".join(str(name).strip().split()).casefold()
    if clean in ("labor units", "labour units"):
        return "Labor Units"
    for configured_name in STATIC_RULES:
        if clean == configured_name.casefold():
            return configured_name
    return None


def find_field_name(layer, requested_name):
    wanted = str(requested_name).strip().casefold()
    for field in layer.fields():
        if field.name().strip().casefold() == wanted:
            return field.name()
    return None


def find_first_field(layer, candidates):
    for candidate in candidates:
        actual = find_field_name(layer, candidate)
        if actual is not None:
            return actual
    return None


def ensure_hub_field(layer):
    actual = find_field_name(layer, HUB_FIELD_NAME)
    if actual is not None:
        return actual
    if find_field_name(layer, "infinium_id") is None:
        return None
    try:
        ok = layer.addAttribute(QgsField(HUB_FIELD_NAME, QVariant.String, "text", 255))
        layer.updateFields()
    except Exception as exc:
        raise RuntimeError("Could not create hub_number field: {}".format(exc))
    if not ok:
        raise RuntimeError("Could not create hub_number field")
    actual = find_field_name(layer, HUB_FIELD_NAME)
    if actual is None:
        raise RuntimeError("hub_number field creation was not confirmed")
    return actual


def build_boundary_index(boundary_layer, target_layer, boundary_rows, project):
    index = QgsSpatialIndex()
    geometries_by_id = {}
    order_by_id = {}
    transform = None
    if boundary_layer.crs() != target_layer.crs():
        transform = QgsCoordinateTransform(
            boundary_layer.crs(), target_layer.crs(), project.transformContext())
    for order, row in enumerate(boundary_rows):
        fid = row["fid"]
        geom = QgsGeometry(row["geometry"])
        if geom.isNull() or geom.isEmpty():
            continue
        if transform is not None:
            geom.transform(transform)
        index_feature = QgsFeature()
        index_feature.setId(fid)
        index_feature.setGeometry(geom)
        index.addFeature(index_feature)
        geometries_by_id[fid] = geom
        order_by_id[fid] = order
    return index, geometries_by_id, order_by_id


def find_infinium_for_feature(feature, category_value, spatial_index,
                              geometries_by_id, order_by_id, boundary_by_id,
                              use_f1_fallback=True):
    geom = feature.geometry()
    if geom is None or geom.isNull() or geom.isEmpty():
        return None
    candidate_ids = spatial_index.intersects(geom.boundingBox())
    candidate_ids.sort(key=lambda item: order_by_id.get(item, 10**18))
    intersecting = []
    for boundary_id in candidate_ids:
        boundary_geom = geometries_by_id.get(boundary_id)
        if boundary_geom is None:
            continue
        try:
            if geom.intersects(boundary_geom):
                intersecting.append(boundary_id)
        except Exception:
            continue
    wanted_category = norm(category_value)
    if wanted_category:
        for boundary_id in intersecting:
            row = boundary_by_id[boundary_id]
            if norm(row["category"]) == wanted_category and not is_blank(row["infinium_id"]):
                return str(row["infinium_id"]).strip()
    if use_f1_fallback:
        for boundary_id in intersecting:
            row = boundary_by_id[boundary_id]
            if norm(row["category"]) == "f1" and not is_blank(row["infinium_id"]):
                return str(row["infinium_id"]).strip()
    for boundary_id in intersecting:
        row = boundary_by_id[boundary_id]
        if not is_blank(row["infinium_id"]):
            return str(row["infinium_id"]).strip()
    return None


def add_rule_value(layer, feature, planned, field_name, desired,
                   overwrite_existing=False, force_rule=False, missing_fields=None):
    actual_name = find_field_name(layer, field_name)
    if actual_name is None:
        if missing_fields is not None:
            missing_fields.add(field_name)
        return
    field_index = layer.fields().indexFromName(actual_name)
    current = planned.get(field_index, feature[field_index])
    if (force_rule or overwrite_existing or is_blank(current)) and current != desired:
        planned[field_index] = desired


def effective_value(layer, feature, planned, field_name):
    actual_name = find_field_name(layer, field_name)
    if actual_name is None:
        return None
    field_index = layer.fields().indexFromName(actual_name)
    return planned.get(field_index, feature[field_index])


def load_boundary_data(project, log):
    matches = project.mapLayersByName(FDA_LAYER_NAME)
    boundary_layer = matches[0] if matches else None
    boundary_rows, boundary_by_id = [], {}
    if boundary_layer is None:
        log.append("WARNING: '{}' layer not found. Spatial Infinium ID lookup is unavailable.".format(FDA_LAYER_NAME))
        return None, boundary_rows, boundary_by_id
    id_actual = find_field_name(boundary_layer, FDA_ID_FIELD)
    category_actual = find_field_name(boundary_layer, FDA_CATEGORY_FIELD)
    if id_actual is None or category_actual is None:
        log.append("WARNING: FDA Boundaries needs fields '{}' and '{}'. Spatial lookup is unavailable.".format(FDA_ID_FIELD, FDA_CATEGORY_FIELD))
        return None, boundary_rows, boundary_by_id
    for f in boundary_layer.getFeatures():
        row = {"fid": f.id(), "geometry": QgsGeometry(f.geometry()),
               "infinium_id": f[id_actual], "category": f[category_actual]}
        boundary_rows.append(row)
        boundary_by_id[row["fid"]] = row
    log.append("Loaded {} FDA Boundaries features.".format(len(boundary_rows)))
    return boundary_layer, boundary_rows, boundary_by_id


def process_layer(layer, options, boundary_layer, boundary_rows, boundary_by_id, project, log):
    layer_label = layer.name()
    log.append("\nProcessing: {}".format(layer_label))
    if not layer.isValid():
        log.append("  SKIPPED: layer is invalid.")
        return {"layer": layer_label, "status": "skipped-invalid", "changed": 0, "features": 0}
    owns_edit_session = not layer.isEditable()
    if owns_edit_session and not layer.startEditing():
        log.append("  SKIPPED: could not start editing (read-only or unsupported provider).")
        return {"layer": layer_label, "status": "skipped-not-editable", "changed": 0, "features": 0}

    changed_attributes = 0
    changed_features = set()
    missing_fields = set()
    warnings = []
    try:
        canonical_name = canonical_layer_name(layer.name())
        split_ids = bool(options.get("split_infinium_hub", True))
        hub_actual = None
        if split_ids and options.get("create_hub_field", True):
            hub_actual = ensure_hub_field(layer)
        elif split_ids:
            hub_actual = find_field_name(layer, HUB_FIELD_NAME)
            if hub_actual is None and find_field_name(layer, "infinium_id") is not None:
                warnings.append("hub_number is missing; splitting cannot save HUB values unless the field is created.")

        fixed_rules_enabled = bool(options.get("apply_fixed_rules", True))
        overwrite_fixed = bool(options.get("overwrite_fixed_values", False))
        features = list(layer.getFeatures())
        pending = {}
        spatial_bundle = None
        if options.get("populate_infinium", True) and boundary_layer is not None and boundary_rows:
            try:
                spatial_bundle = build_boundary_index(boundary_layer, layer, boundary_rows, project)
            except Exception as exc:
                warnings.append("Could not build FDA spatial index: {}".format(exc))

        for feature in features:
            planned = {}
            if fixed_rules_enabled and canonical_name in STATIC_RULES:
                for field_name, desired in STATIC_RULES[canonical_name]:
                    # Span Size is intentionally forced to 2" as requested.
                    force = canonical_name == "Span" and field_name == "size"
                    add_rule_value(layer, feature, planned, field_name, desired,
                                   overwrite_existing=overwrite_fixed, force_rule=force,
                                   missing_fields=missing_fields)

            # Structures: if Type is Handhole, force Size to 2x3.
            if canonical_name == "Structures" and fixed_rules_enabled:
                type_field = find_first_field(layer, ["type", "structure_type", "structuretype"])
                if type_field is None:
                    missing_fields.add("type (needed for Handhole size rule)")
                elif norm(effective_value(layer, feature, planned, type_field)) == "handhole":
                    add_rule_value(layer, feature, planned, "size", "2x3",
                                   force_rule=True, missing_fields=missing_fields)

            # Fiber Cable: a blank naming field means Size=1; then size 1 -> Drop.
            if canonical_name == "Fiber Cable" and fixed_rules_enabled:
                naming_field = find_first_field(layer, ["naming", "cable_name", "name"])
                if naming_field is None:
                    warnings.append("No naming field found (tried naming, cable_name, name); skipped blank-naming Size rule.")
                elif is_blank(effective_value(layer, feature, planned, naming_field)):
                    add_rule_value(layer, feature, planned, "size", "1",
                                   force_rule=True, missing_fields=missing_fields)
                size_value = effective_value(layer, feature, planned, "size")
                desired_category = "Drop" if norm(size_value) in ("1", "1.0") else "F2"
                add_rule_value(layer, feature, planned, "cable_category", desired_category,
                               force_rule=True, missing_fields=missing_fields)

            # Span: Aerial - Overlash is Existing; other methods are New Build.
            if canonical_name == "Span" and fixed_rules_enabled:
                install_method = effective_value(layer, feature, planned, "install_me")
                status = "Existing" if norm(install_method) == "aerial - overlash" else "New Build"
                add_rule_value(layer, feature, planned, "physical_status", status,
                               force_rule=True, missing_fields=missing_fields)

            # Populate Infinium ID spatially from FDA Boundaries when selected.
            if options.get("populate_infinium", True):
                infinium_field = find_field_name(layer, "infinium_id")
                if infinium_field is not None and spatial_bundle is not None:
                    current_infinium = effective_value(layer, feature, planned, infinium_field)
                    should_lookup = options.get("overwrite_infinium", False) or is_blank(current_infinium)
                    if should_lookup:
                        if canonical_name == "Fiber Cable":
                            category_field, use_f1_fallback = "cable_category", False
                        else:
                            category_field, use_f1_fallback = "category", True
                        category_value = effective_value(layer, feature, planned, category_field)
                        try:
                            sindex, geom_map, order_map = spatial_bundle
                            matched_id = find_infinium_for_feature(
                                feature, category_value, sindex, geom_map, order_map,
                                boundary_by_id, use_f1_fallback=use_f1_fallback)
                        except Exception as exc:
                            matched_id = None
                            warnings.append("Spatial Infinium lookup failed: {}".format(exc))
                        if matched_id is not None:
                            add_rule_value(layer, feature, planned, "infinium_id", matched_id,
                                           overwrite_existing=options.get("overwrite_infinium", False),
                                           missing_fields=missing_fields)

            # Optional split at first hyphen. Never create mismatched ID/HUB values.
            if split_ids and hub_actual is not None:
                infinium_value = effective_value(layer, feature, planned, "infinium_id")
                if not is_blank(infinium_value):
                    infinium_text = str(infinium_value).strip()
                    if "-" in infinium_text:
                        infinium_part, hub_part = infinium_text.split("-", 1)
                        infinium_part = infinium_part.strip()
                        hub_part = hub_part.strip()
                        current_hub = effective_value(layer, feature, planned, hub_actual)

                        if not infinium_part or not hub_part:
                            warnings.append(
                                "Feature ID {}: combined Infinium ID {!r} has an empty part; split skipped.".format(
                                    feature.id(), infinium_text))
                        else:
                            hub_is_blank = is_blank(current_hub)
                            hub_matches = (not hub_is_blank and
                                           str(current_hub).strip().casefold() == hub_part.casefold())
                            overwrite_hub = bool(options.get("overwrite_hub", False))

                            if hub_is_blank or hub_matches or overwrite_hub:
                                add_rule_value(layer, feature, planned, "infinium_id", infinium_part,
                                               overwrite_existing=True, force_rule=True,
                                               missing_fields=missing_fields)
                                add_rule_value(layer, feature, planned, hub_actual, hub_part,
                                               overwrite_existing=overwrite_hub,
                                               missing_fields=missing_fields)
                            else:
                                warnings.append(
                                    "HUB conflict on feature ID {}: combined Infinium ID {!r} implies "
                                    "hub_number={!r}, but existing hub_number={!r}. Split skipped to avoid "
                                    "conflicting values. Enable HUB overwrite to replace it.".format(
                                        feature.id(), infinium_text, hub_part, str(current_hub).strip()))

            pending[feature.id()] = planned

        for feature_id, planned in pending.items():
            for field_index, new_value in planned.items():
                if layer.changeAttributeValue(feature_id, field_index, new_value):
                    changed_attributes += 1
                    changed_features.add(feature_id)
                else:
                    field_name = layer.fields()[field_index].name()
                    raise RuntimeError("QGIS rejected update for feature ID {}, field '{}'".format(feature_id, field_name))

        if owns_edit_session:
            if not layer.commitChanges():
                errors = "; ".join(layer.commitErrors())
                layer.rollBack()
                raise RuntimeError("Commit failed: {}".format(errors or "unspecified provider error"))
            status = "committed"
        else:
            status = "staged-in-existing-edit-session"

        log.append("  Features updated: {}".format(len(changed_features)))
        log.append("  Attribute values changed: {}".format(changed_attributes))
        if missing_fields:
            log.append("  Missing fields: {}".format(", ".join(sorted(missing_fields))))
        for warning in sorted(set(warnings)):
            log.append("  WARNING: {}".format(warning))
        log.append("  Result: {}".format(status))
        return {"layer": layer_label, "status": status, "changed": changed_attributes,
                "features": len(changed_features), "missing_fields": sorted(missing_fields),
                "warnings": sorted(set(warnings))}
    except Exception as exc:
        if owns_edit_session and layer.isEditable():
            layer.rollBack()
        log.append("  ERROR: {}".format(exc))
        return {"layer": layer_label, "status": "error", "changed": changed_attributes,
                "features": len(changed_features), "error": str(exc)}


def run_autofill(selected_layers, options, project=None):
    """Run all selected rules for the selected QgsVectorLayer objects."""
    project = project or QgsProject.instance()
    if project is None:
        raise RuntimeError("No QGIS project is open.")
    if not selected_layers:
        raise RuntimeError("Select at least one layer to process.")
    log = []
    if options.get("populate_infinium", True):
        boundary_layer, boundary_rows, boundary_by_id = load_boundary_data(project, log)
    else:
        boundary_layer, boundary_rows, boundary_by_id = None, [], {}
    results = []
    for layer in selected_layers:
        results.append(process_layer(layer, options, boundary_layer, boundary_rows,
                                     boundary_by_id, project, log))
    log.append("\n================ AUTO-FILL SUMMARY ================")
    log.append("Selected layers: {}".format(len(selected_layers)))
    log.append("Attribute values changed: {}".format(sum(item.get("changed", 0) for item in results)))
    for item in results:
        log.append("- {}: {} ({} changes)".format(item["layer"], item["status"], item.get("changed", 0)))
    log.append("===================================================")
    return results, "\n".join(log)
