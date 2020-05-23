# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ScribbleMapsConnector
 This plugin allows you to visualize your Scribble Maps data.
 copyright (C) 2020 by Scribble Maps
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'scribblemaps_connector_dialog_base.ui'))

class ScribbleMapsConnectorDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super(ScribbleMapsConnectorDialog, self).__init__(parent)
        self.setupUi(self)
