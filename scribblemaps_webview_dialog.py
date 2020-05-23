#!/usr/bin/env python

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

from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtWebKit import *
from qgis.PyQt.QtWebKitWidgets import *
from qgis.core import *
import math

class ScribbleMapsWebViewDialog(QDialog):

    def __init__(self):
        super(ScribbleMapsWebViewDialog, self).__init__()
        
        self.setWindowTitle('Link to Scribble Maps')
        
        QBtn = QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.webView = QWebView()
        self.webView.loadStarted.connect(self.showOverlay)
        self.webView.loadFinished.connect(self.hideOverlay)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.webView)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)

        self.overlay = Overlay(self)
        self.overlay.hide()

    def setPage(self, page):
        self.webView.load(QUrl(page))
        self.webView.frame = self.webView.page().currentFrame()

    def resizeEvent(self, event):
        self.overlay.resize(event.size())
        event.accept()

    def showOverlay(self):
        self.overlay.show()

    def hideOverlay(self):
        self.overlay.hide()

class Overlay(QWidget):
    def __init__(self, parent = None):
    
        QWidget.__init__(self, parent)
        palette = QPalette(self.palette())
        palette.setColor(palette.Background, Qt.transparent)
        self.setPalette(palette)
    
    def paintEvent(self, event):
        painter = QPainter()
        painter.begin(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(event.rect(), QBrush(QColor(255, 255, 255, 127)))
        painter.setPen(QPen(Qt.NoPen))

        for i in range(6):
            if self.activeDot == i:
                painter.setBrush(QBrush(QColor(255, 0, 0)))
            else:
                painter.setBrush(QBrush(QColor(127, 127, 127)))
            painter.drawEllipse(
                self.width()/2 + 30 * math.cos(2 * math.pi * i / 6.0) - 10,
                self.height()/2 + 30 * math.sin(2 * math.pi * i / 6.0) - 10,
                20, 20)
        
        painter.end()
    
    def showEvent(self, event):
        self.timer = self.startTimer(50)
        self.counter = 0
        self.activeDot = 0

    def hideEvent(self, event):
        if (self.timer > 0):
            self.killTimer(self.timer)
            self.timer = 0
    
    def timerEvent(self, event):
        self.counter += 1
        if (self.counter % 5 == 0):
            self.activeDot += 1
            if (self.activeDot > 5):
                self.activeDot = 0
        self.update()
