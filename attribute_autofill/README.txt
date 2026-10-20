QGIS Attribute Auto-Fill — Version 1.0.2
Author: Amlan Patnaik | Copyright (C) 2026 Amlan Patnaik

INSTALL DIRECTLY IN QGIS
1. Open QGIS.
2. Go to Plugins > Manage and Install Plugins > Install from ZIP.
3. Select QGIS_Attribute_AutoFill_Installable_v1_0_2.zip.
4. Enable QGIS Attribute Auto-Fill if QGIS has not enabled it automatically.
5. Open it from the Plugins menu or toolbar.

PLUGIN BUILDER SOURCE FILES
The main source files used by this plugin are:
  __init__.py
  attribute_autofill.py
  attribute_autofill_dialog.py
  autofill_core.py
  metadata.txt
  icon.png
The UI is created at runtime; attribute_autofill_dialog_base.ui is retained for the generated Plugin Builder template.

IMPORTANT ID/HUB SAFETY UPDATE
When Split at first hyphen is selected, the plugin now checks the existing hub_number.
- If HUB is blank, it fills the parsed HUB value.
- If HUB already matches the parsed suffix, it splits the Infinium ID safely.
- If HUB differs and HUB overwrite is disabled, it leaves the combined Infinium ID intact and reports the conflict.
- If HUB overwrite is enabled, it replaces the existing HUB value and splits the Infinium ID.
Malformed combined values with an empty prefix or suffix are not split.

DATA SAFETY
- Back up your project before the first run.
- Default fixed rules fill blank values, except intentional conditional rules and Span Size=2" while rules are enabled.
- The plugin has been syntax-checked, but must still be tested in your own QGIS session and against copies of your layers.
- `FDA Boundaries` must contain `infinium_id` and `category` for spatial Infinium ID population.

SUPPORTED RULE LAYERS
Equipment, Slackloop, Splice Closure, Structures, Span, Fiber Cable, Labor Units (also accepts Labour Units spelling).
