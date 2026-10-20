# -*- coding: utf-8 -*-
"""Runtime-created dialog for QGIS Attribute Auto-Fill.

No .ui file is required; this keeps the Plugin Builder template easy to maintain.
Copyright (C) 2026 Amlan Patnaik.
"""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout, QLabel,
    QMessageBox, QPlainTextEdit, QPushButton, QRadioButton, QScrollArea,
    QVBoxLayout, QWidget
)
from qgis.core import QgsProject, QgsVectorLayer

from .autofill_core import STATIC_RULES, canonical_layer_name, run_autofill

AUTHOR_NAME = "Amlan Patnaik"
AUTHOR_FOOTER = "Author: Amlan Patnaik  |  © 2026 Amlan Patnaik"


def attributed(text):
    """Append visible copyright attribution to message-box content."""
    return "{}\n\n{}".format(text, AUTHOR_FOOTER)


class ResultsDialog(QDialog):
    """Show processing results and warnings."""

    def __init__(self, report, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Attribute Auto-Fill Results — Author: {}".format(AUTHOR_NAME))
        self.resize(760, 520)
        layout = QVBoxLayout(self)

        self.output = QPlainTextEdit(self)
        self.output.setReadOnly(True)
        self.output.setPlainText(report)
        layout.addWidget(self.output, 1)

        footer = QLabel(AUTHOR_FOOTER, self)
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #666666; padding: 5px; border-top: 1px solid #cccccc;")
        layout.addWidget(footer)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class AttributeAutoFillDialog(QDialog):
    """Layer chooser and configuration UI."""

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.project = QgsProject.instance()
        self.layer_checkboxes = []
        self.setWindowTitle("QGIS Attribute Auto-Fill — Author: {}".format(AUTHOR_NAME))
        self.resize(680, 760)
        self.setMinimumSize(590, 650)
        self._build_ui()
        self._populate_layers()
        self._update_control_states()

    def _build_ui(self):
        root = QVBoxLayout(self)
        intro = QLabel(
            "Choose the telecom/GIS layers to process. Select the attribute rules and "
            "choose whether Infinium IDs remain combined or are split into Infinium ID "
            "and HUB Number. Review the summary before confirming any changes."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        layer_group = QGroupBox("1. Layers to update", self)
        layer_layout = QVBoxLayout(layer_group)
        selection_buttons = QHBoxLayout()
        self.select_all_button = QPushButton("Select all loaded target layers", layer_group)
        self.select_none_button = QPushButton("Clear selection", layer_group)
        self.select_all_button.clicked.connect(self._select_all)
        self.select_none_button.clicked.connect(self._select_none)
        selection_buttons.addWidget(self.select_all_button)
        selection_buttons.addWidget(self.select_none_button)
        selection_buttons.addStretch(1)
        layer_layout.addLayout(selection_buttons)

        self.layer_scroll = QScrollArea(layer_group)
        self.layer_scroll.setWidgetResizable(True)
        self.layer_scroll.setMinimumHeight(170)
        self.layer_widget = QWidget(self.layer_scroll)
        self.layer_list_layout = QVBoxLayout(self.layer_widget)
        self.layer_list_layout.setContentsMargins(6, 6, 6, 6)
        self.layer_list_layout.setAlignment(Qt.AlignTop)
        self.layer_scroll.setWidget(self.layer_widget)
        layer_layout.addWidget(self.layer_scroll)
        root.addWidget(layer_group, 2)

        rules_group = QGroupBox("2. Attribute rules", self)
        rules_layout = QVBoxLayout(rules_group)
        self.apply_rules_check = QCheckBox(
            "Apply fixed and conditional rules from the field-report workbook", rules_group)
        self.apply_rules_check.setChecked(True)
        self.overwrite_fixed_check = QCheckBox(
            "Overwrite existing values for fixed rules (otherwise fill blanks only)", rules_group)
        self.overwrite_fixed_check.setChecked(False)
        self.overwrite_fixed_check.setToolTip(
            'Span Size is deliberately forced to 2" when the rules are enabled. '
            "Conditional rules such as Structures Handhole Size and Span Physical Status also apply."
        )
        rules_layout.addWidget(self.apply_rules_check)
        rules_layout.addWidget(self.overwrite_fixed_check)
        root.addWidget(rules_group)

        id_group = QGroupBox("3. Infinium ID and HUB Number", self)
        id_layout = QVBoxLayout(id_group)
        self.populate_infinium_check = QCheckBox(
            "Populate blank Infinium IDs from intersecting FDA Boundaries", id_group)
        self.populate_infinium_check.setChecked(True)
        self.overwrite_infinium_check = QCheckBox(
            "Replace existing Infinium IDs with the matching FDA value", id_group)
        self.overwrite_infinium_check.setChecked(False)
        id_layout.addWidget(self.populate_infinium_check)
        id_layout.addWidget(self.overwrite_infinium_check)

        mode_label = QLabel("Choose how the two ID fields should be handled:", id_group)
        id_layout.addWidget(mode_label)
        self.keep_combined_radio = QRadioButton(
            "Keep Infinium ID combined; do not split it or update HUB Number", id_group)
        self.split_id_radio = QRadioButton(
            "Split at the first hyphen: left side → infinium_id; right side → hub_number", id_group)
        self.split_id_radio.setChecked(True)
        id_layout.addWidget(self.keep_combined_radio)
        id_layout.addWidget(self.split_id_radio)

        self.create_hub_check = QCheckBox(
            "Create hub_number field if it does not exist", id_group)
        self.create_hub_check.setChecked(True)
        self.overwrite_hub_check = QCheckBox(
            "Overwrite a nonblank HUB Number when splitting", id_group)
        self.overwrite_hub_check.setChecked(False)
        id_layout.addWidget(self.create_hub_check)
        id_layout.addWidget(self.overwrite_hub_check)
        root.addWidget(id_group)

        safety_note = QLabel(
            "Safety: the default fills blank fixed-rule values and blank Infinium IDs only. "
            "Span Size is set to 2\" for all processed Span features while attribute rules are enabled. "
            "Changes to a layer already in edit mode are staged but not committed by this plugin. "
            "Back up the project before first use."
        )
        safety_note.setWordWrap(True)
        root.addWidget(safety_note)

        author_label = QLabel(AUTHOR_FOOTER, self)
        author_label.setAlignment(Qt.AlignCenter)
        author_label.setStyleSheet(
            "font-weight: bold; color: #555555; padding: 6px; border-top: 1px solid #cccccc;"
        )
        root.addWidget(author_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.run_button = QPushButton("Run Attribute Auto-Fill", self)
        self.run_button.setDefault(True)
        self.close_button = QPushButton("Close", self)
        self.run_button.clicked.connect(self._run)
        self.close_button.clicked.connect(self.reject)
        button_row.addWidget(self.run_button)
        button_row.addWidget(self.close_button)
        root.addLayout(button_row)

        self.populate_infinium_check.toggled.connect(self._update_control_states)
        self.split_id_radio.toggled.connect(self._update_control_states)
        self.apply_rules_check.toggled.connect(self._update_control_states)

    def _populate_layers(self):
        loaded = []
        if self.project is not None:
            for layer in self.project.mapLayers().values():
                if not isinstance(layer, QgsVectorLayer):
                    continue
                canonical = canonical_layer_name(layer.name())
                if canonical:
                    loaded.append((canonical, layer))

        for configured_name in STATIC_RULES:
            matching = [(name, layer) for name, layer in loaded if name == configured_name]
            if not matching:
                checkbox = QCheckBox("{} (not loaded)".format(configured_name), self.layer_widget)
                checkbox.setEnabled(False)
                checkbox.setToolTip("Load this target layer into the current QGIS project to enable it.")
                self.layer_list_layout.addWidget(checkbox)
                continue

            for _, layer in matching:
                label = layer.name()
                if len(matching) > 1:
                    source = layer.source().split("|")[0]
                    label = "{} — {}".format(layer.name(), source[-55:])
                checkbox = QCheckBox(label, self.layer_widget)
                checkbox.setChecked(False)
                checkbox.setProperty("layer_id", layer.id())
                checkbox.setToolTip("Layer: {}\nProvider: {}".format(layer.name(), layer.providerType()))
                self.layer_list_layout.addWidget(checkbox)
                self.layer_checkboxes.append(checkbox)

        if not self.layer_checkboxes:
            no_layers = QLabel("No supported target layers are currently loaded in this project.", self.layer_widget)
            no_layers.setWordWrap(True)
            self.layer_list_layout.addWidget(no_layers)
            self.run_button.setEnabled(False)

    def _select_all(self):
        for checkbox in self.layer_checkboxes:
            checkbox.setChecked(True)

    def _select_none(self):
        for checkbox in self.layer_checkboxes:
            checkbox.setChecked(False)

    def _update_control_states(self, *_args):
        populate = self.populate_infinium_check.isChecked()
        split = self.split_id_radio.isChecked()
        self.overwrite_infinium_check.setEnabled(populate)
        self.create_hub_check.setEnabled(split)
        self.overwrite_hub_check.setEnabled(split)
        self.overwrite_fixed_check.setEnabled(self.apply_rules_check.isChecked())

    def _selected_layers(self):
        selected_ids = {
            checkbox.property("layer_id")
            for checkbox in self.layer_checkboxes if checkbox.isChecked()
        }
        if self.project is None:
            return []
        return [layer for layer in self.project.mapLayers().values()
                if layer.id() in selected_ids]

    def _options(self):
        return {
            "apply_fixed_rules": self.apply_rules_check.isChecked(),
            "overwrite_fixed_values": self.overwrite_fixed_check.isChecked(),
            "populate_infinium": self.populate_infinium_check.isChecked(),
            "overwrite_infinium": self.overwrite_infinium_check.isChecked(),
            "split_infinium_hub": self.split_id_radio.isChecked(),
            "create_hub_field": self.create_hub_check.isChecked(),
            "overwrite_hub": self.overwrite_hub_check.isChecked(),
        }

    def _run(self):
        selected = self._selected_layers()
        if not selected:
            QMessageBox.warning(
                self, "No layers selected — Author: {}".format(AUTHOR_NAME),
                attributed("Tick at least one loaded target layer to update."))
            return

        options = self._options()
        summary = ["Selected layers:"]
        summary.extend(["  • {}".format(layer.name()) for layer in selected])
        summary.extend([
            "",
            "Fixed attribute rules: {}".format("On" if options["apply_fixed_rules"] else "Off"),
            "Overwrite fixed values: {}".format("Yes" if options["overwrite_fixed_values"] else "No"),
            "Populate Infinium ID from FDA Boundaries: {}".format("Yes" if options["populate_infinium"] else "No"),
            "Overwrite existing Infinium IDs: {}".format("Yes" if options["overwrite_infinium"] else "No"),
            "ID/HUB mode: {}".format(
                "Split at first hyphen" if options["split_infinium_hub"] else "Keep combined ID"),
        ])
        if options["split_infinium_hub"]:
            summary.append("Create HUB field if missing: {}".format(
                "Yes" if options["create_hub_field"] else "No"))
            summary.append("Overwrite existing HUB values: {}".format(
                "Yes" if options["overwrite_hub"] else "No"))

        answer = QMessageBox.question(
            self,
            "Confirm Attribute Auto-Fill — Author: {}".format(AUTHOR_NAME),
            attributed("The selected layers may be edited. Continue?\n\n" + "\n".join(summary)),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        self.run_button.setEnabled(False)
        self.close_button.setEnabled(False)
        try:
            _results, report = run_autofill(selected, options, self.project)
        except Exception as exc:
            QMessageBox.critical(
                self, "Attribute Auto-Fill failed — Author: {}".format(AUTHOR_NAME),
                attributed("The operation failed:\n{}".format(exc)))
            return
        finally:
            self.run_button.setEnabled(True)
            self.close_button.setEnabled(True)

        ResultsDialog(report + "\n\n" + AUTHOR_FOOTER, self).exec_()
