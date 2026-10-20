# -*- coding: utf-8 -*-
"""QGIS Attribute Auto-Fill plugin entry point.

Copyright (C) 2026 Amlan Patnaik.
"""


def classFactory(iface):  # pylint: disable=invalid-name
    """Load the plugin class used by QGIS."""
    from .attribute_autofill import AttributeAutoFill
    return AttributeAutoFill(iface)
