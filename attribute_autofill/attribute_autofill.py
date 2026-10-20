# -*- coding: utf-8 -*-
"""Main QGIS Plugin Builder class for Attribute Auto-Fill.

Copyright (C) 2026 Amlan Patnaik.
"""
import os

from qgis.PyQt.QtCore import QCoreApplication, QLocale, QTranslator
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsSettings

from .attribute_autofill_dialog import AttributeAutoFillDialog

AUTHOR_TEXT = "Author: Amlan Patnaik | © 2026 Amlan Patnaik"


class AttributeAutoFill:
    """QGIS plugin implementation."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = self.tr("&QGIS Attribute Auto-Fill")
        self.translator = None
        self.dialog = None

        locale = QgsSettings().value("locale/userLocale", QLocale().name())[0:2]
        locale_path = os.path.join(self.plugin_dir, "i18n", "{}.qm".format(locale))
        if os.path.exists(locale_path):
            self.translator = QTranslator()
            if self.translator.load(locale_path):
                QCoreApplication.installTranslator(self.translator)

    def tr(self, message):
        return QCoreApplication.translate("AttributeAutoFill", message)

    def add_action(self, icon_path, text, callback, parent=None):
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        action = QAction(icon, text, parent or self.iface.mainWindow())
        action.triggered.connect(callback)
        action.setStatusTip("Fill telecom GIS attributes. {}".format(AUTHOR_TEXT))
        action.setWhatsThis("Attribute Auto-Fill by Amlan Patnaik.")
        self.iface.addToolBarIcon(action)
        self.iface.addPluginToMenu(self.menu, action)
        self.actions.append(action)
        return action

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        self.add_action(icon_path, self.tr("Attribute Auto-Fill"), self.run,
                        parent=self.iface.mainWindow())

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        self.actions = []
        if self.translator is not None:
            QCoreApplication.removeTranslator(self.translator)
            self.translator = None

    def run(self):
        """Open the plugin dialog."""
        self.dialog = AttributeAutoFillDialog(self.iface, self.iface.mainWindow())
        self.dialog.exec_()
