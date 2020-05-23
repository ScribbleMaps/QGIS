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
from qgis.core import *

from .resources import *
from .scribblemaps_connector_dialog import ScribbleMapsConnectorDialog
from .scribblemaps_publish_dialog import ScribbleMapsPublishDialog
from .scribblemaps_webview_dialog import ScribbleMapsWebViewDialog
from .scribblemaps_shareview_dialog import ScribbleMapsShareViewDialog

import os
import uuid
import requests
import ssl
import threading
import json
import linecache
import sys
from tempfile import NamedTemporaryFile

class ScribbleMapsConnector:

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)

        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'ScribbleMapsConnector_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        self.actions = []
        self.menu = self.tr(u'&Scribble Maps Connector')

        self.instance_uuid = str(uuid.uuid4())
        self.current_token = False
        self.lastPublishedMapCode = False
        self.pendingErrorDisplay = False

        # Set up connector dialog:
        self.loadDlg = ScribbleMapsConnectorDialog()

        # Link account is the same action as refresh map list; since refreshing map list will check auth first anyway
        self.loadDlg.pbLink.clicked.connect(self.authAndRefreshMapList)
        self.loadDlg.pbUnlink.clicked.connect(self.clearAuth)
        self.loadDlg.pbRefresh.clicked.connect(self.authAndRefreshMapList)
        self.loadDlg.pbLoadSelected.clicked.connect(self.authAndLoadSelectedMap)
        self.loadDlg.chbRequestThumbs.toggled.connect(self.authAndRefreshMapList)

        # Set up publishing dialog:
        self.publishDlg = ScribbleMapsPublishDialog()
        self.successDialog = ScribbleMapsShareViewDialog()
        self.publishDlg.cmbMapType.clear()
        self.publishDlg.cmbMapType.addItem('Hybrid')
        self.publishDlg.cmbMapType.addItem('Road')
        self.publishDlg.cmbMapType.addItem('Satellite')
        self.publishDlg.cmbMapType.addItem('Terrain')
        self.publishDlg.cmbMapType.addItem('Scribble Maps Road')
        self.publishDlg.cmbMapType.addItem('Scribble Maps Topo')
        self.publishDlg.cmbMapType.addItem('Scribble Maps White')        

        self.publishDlg.pbClose.clicked.connect(self.closePublishDlg)
        self.publishDlg.pbPublish.clicked.connect(self.publishMap)
        
    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('ScribbleMapsConnector', message)

    def handleException(self, e):
        exc_type, exc_obj, tb = sys.exc_info()
        f = tb.tb_frame
        lineno = tb.tb_lineno
        filename = f.f_code.co_filename
        linecache.checkcache(filename)
        line = linecache.getline(filename, lineno, f.f_globals)
        QgsMessageLog.logMessage('EXCEPTION IN ({}, LINE {} "{}"): {}'.format(filename, lineno, line.strip(), exc_obj), "Error Report")

    def add_action(self, icon_path, text, callback, enabled_flag=True, add_to_menu=True, add_to_toolbar=True, status_tip=None, whats_this=None, parent=None):
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToWebMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        self.add_action(':/plugins/scribblemaps_connector/icon_download.png', text=self.tr(u'Load Data from Scribble Maps'), callback=self.showLoadDlg, parent=self.iface.mainWindow())
        self.add_action(':/plugins/scribblemaps_connector/icon_upload.png', text=self.tr(u'Publish to Scribble Maps'), callback=self.showPublishDlg, parent=self.iface.mainWindow())

    def unload(self):
        for action in self.actions:
            self.iface.removePluginWebMenu(
                self.tr(u'&Scribble Maps Connector'),
                action)
            self.iface.removeToolBarIcon(action)

    def checkAuth(self, authOKCallback):
        try:
            progressBar = QProgressDialog('Checking authentication...', None, 0, 100)
            progressBar.setWindowTitle('Please Wait...')
            progressBar.setWindowModality(Qt.WindowModal)
            progressBar.setAutoClose(False)
            progressBar.setMinimumDuration(100)
            progressBar.setWindowFlags(progressBar.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
            progressBar.show()
            progressBar.raise_()
            progressBar.activateWindow()
            progressBar.setValue(0)
            progressBar.setMaximum(100)

            thread = threading.Thread(target = self._checkAuthInternal)
            thread.start()
            while thread.is_alive():
                QApplication.processEvents()
                thread.join(0.2)
                progressBar.setValue((progressBar.value() + 1 % 100))

            progressBar.close()

            if ("validToken" in self.lastThreadResponse or "redirectTo" in self.lastThreadResponse):
                if (self.lastThreadResponse["validToken"]):
                    self.current_token = self.lastThreadResponse["token"]
                    self.loadDlg.pbLink.setEnabled(False)
                    self.loadDlg.pbUnlink.setEnabled(True)
                    self.loadDlg.pbRefresh.setEnabled(True)

                    authOKCallback()
                else:
                    connectDlg = ScribbleMapsWebViewDialog()
                    connectDlg.setPage(self.lastThreadResponse["redirectTo"])
                    dialogResult = connectDlg.exec_()
                    if (dialogResult == 1):
                        self.checkAuth(authOKCallback)
            else:
                QMessageBox.information(None, "Unable to Load Data", "We were unable to check your authentication! Please make sure you have an active internet connection.", QMessageBox.Ok)
        
        except Exception as e:
            self.handleException(e)

    def _checkAuthInternal(self):
        url = 'https://labs.strategiccode.com/scribble-maps-api/auth/' + self.instance_uuid
        # Most people won't have run Python/Install Certificates.command on mac... may be an issue on other platforms?
        try:
            _create_unverified_https_context = ssl._create_unverified_context
        except AttributeError:
            pass
        else:
            ssl._create_default_https_context = _create_unverified_https_context
        result = requests.get(url)
        self.lastThreadResponse = result.json()
    
    def clearAuth(self):
        self.current_token = False
        self.instance_uuid = str(uuid.uuid4())
        self.loadDlg.pbLink.setEnabled(True)
        self.loadDlg.pbUnlink.setEnabled(False)
        self.loadDlg.pbRefresh.setEnabled(False)
        self.loadDlg.tblMaps.setEnabled(False)
        self.loadDlg.pbLoadSelected.setEnabled(False)

    def authAndRefreshMapList(self):
        # Before any operation, we'll re-check our authentication in case the server refreshed our token for us
        self.checkAuth(self.refreshMapList)

    def refreshMapList(self):
        try:
            if (not self.loadDlg.pbRefresh.isEnabled):
                return

            progressBar = QProgressDialog('Loading map list...', None, 0, 100)
            progressBar.setWindowTitle('Please Wait...')
            progressBar.setWindowModality(Qt.WindowModal)
            progressBar.setAutoClose(False)
            progressBar.setMinimumDuration(100)
            progressBar.setWindowFlags(progressBar.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
            progressBar.show()
            progressBar.raise_()
            progressBar.activateWindow()
            progressBar.setValue(0)
            progressBar.setMaximum(100)

            thread = threading.Thread(target = self._refreshMapListInternal)
            thread.start()
            while thread.is_alive():
                QApplication.processEvents()
                thread.join(0.2)
                progressBar.setValue((progressBar.value() + 1 % 100))

            result = self.lastThreadResponse

            if ("mapList" in result):
                self.loadDlg.tblMaps.setColumnCount(7)
                self.loadDlg.tblMaps.setHorizontalHeaderLabels(['Map Code', 'Title', 'Description', 'Created', 'Thumbnail', 'Edit', 'Share'])
                self.loadDlg.tblMaps.setRowCount(len(result["mapList"]))

                for i, map in enumerate(result["mapList"]):
                    parsedCreateDate = QDateTime.fromString(map["created"], Qt.ISODate)

                    thumbLabel = QLabel()
                    if ("thumbBytes" in map):
                        thumb = QPixmap()
                        thumb.loadFromData(map["thumbBytes"])
                        thumbLabel.setPixmap(thumb.scaled(100, 100))

                    self.loadDlg.tblMaps.setItem(i, 0, QTableWidgetItem(map["mapCode"]))
                    self.loadDlg.tblMaps.setItem(i, 1, QTableWidgetItem(map["title"]))
                    self.loadDlg.tblMaps.setItem(i, 2, QTableWidgetItem(map["description"]))
                    self.loadDlg.tblMaps.setItem(i, 3, QTableWidgetItem(parsedCreateDate.toString('ddd MMMM d yyyy h:m ap')))
                    self.loadDlg.tblMaps.setCellWidget(i, 4, thumbLabel)

                    editLabel = QLabel()
                    editLabel.setText("<a href='https://www.scribblemaps.com/create/#id=" + map["mapCode"] + "'>Edit on Scribble Maps</a>")
                    editLabel.setOpenExternalLinks(True)
                    self.loadDlg.tblMaps.setCellWidget(i, 5, editLabel)

                    if (map["shareUrl"][0] == '/'):
                        map["shareUrl"] = 'https:' + map["shareUrl"]
                    shareLabel = QLabel()
                    shareLabel.setText("<a href='" + map["shareUrl"] + "'>Share Link</a>")
                    shareLabel.setOpenExternalLinks(True)
                    self.loadDlg.tblMaps.setCellWidget(i, 6, shareLabel)
                    
                self.loadDlg.tblMaps.resizeColumnsToContents()
                self.loadDlg.tblMaps.resizeRowsToContents()
                self.loadDlg.tblMaps.setSelectionBehavior(QAbstractItemView.SelectRows)

                if (len(result["mapList"]) > 0):
                    self.loadDlg.tblMaps.setCurrentCell(0, 0)
                    self.loadDlg.pbLoadSelected.setEnabled(True)
            else:
                QMessageBox.information(None, "Unable to Load List", "Unable to load the map list! There was no data returned.", QMessageBox.Ok)

            progressBar.close()
        
        except Exception as e:
            self.handleException(e)

    def _refreshMapListInternal(self):
        result = requests.get('https://www.scribblemaps.com/api/user/maps/', headers={ 'Authorization': 'Bearer ' + self.current_token})
        self.lastThreadResponse = result.json()

        if (self.loadDlg.chbRequestThumbs.isChecked()):
            for i, map in enumerate(self.lastThreadResponse["mapList"]):
                if (map["thumbUrl"][0] == '/'):
                    map["thumbUrl"] = 'https:' + map["thumbUrl"]
                map["thumbBytes"] = requests.get(map["thumbUrl"]).content

    def authAndLoadSelectedMap(self):
        # Before any operation, we'll re-check our authentication in case the server refreshed our token for us
        self.checkAuth(self.loadSelectedMap)

    def loadSelectedMap(self):
        try:
            self.lastSelectedMapCode = str(self.loadDlg.tblMaps.item(self.loadDlg.tblMaps.currentRow(), 0).text())

            progressBar = QProgressDialog('Loading map data...', None, 0, 100)
            progressBar.setWindowTitle('Please Wait...')
            progressBar.setWindowModality(Qt.WindowModal)
            progressBar.setAutoClose(False)
            progressBar.setMinimumDuration(100)
            progressBar.setWindowFlags(progressBar.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
            progressBar.show()
            progressBar.raise_()
            progressBar.activateWindow()
            progressBar.setValue(0)
            progressBar.setMaximum(100)

            thread = threading.Thread(target = self._loadSelectedMapInternal)
            thread.start()
            while thread.is_alive():
                QApplication.processEvents()
                thread.join(0.2)
                progressBar.setValue((progressBar.value() + 1 % 100))

            if (len(self.lastLoadedMap) > 0):
                tempKML = NamedTemporaryFile()
                tempKML.write(self.lastLoadedMap)
                tempKML.flush()
                
                # Convert it to in-memory datasets of each type, so we can 1) delete our temp file and not reference a weird temp file, and 2) get each geometry type
                srcLayer = QgsVectorLayer(tempKML.name, "data", "ogr")
                
                destPoint = QgsVectorLayer("Point?crs=epsg:4326",  'Points: ' + str(self.loadDlg.tblMaps.item(self.loadDlg.tblMaps.currentRow(), 1).text()), "memory")
                destLine = QgsVectorLayer("LineString?crs=epsg:4326",  'Lines: ' + str(self.loadDlg.tblMaps.item(self.loadDlg.tblMaps.currentRow(), 1).text()), "memory")
                destPoly = QgsVectorLayer("Polygon?crs=epsg:4326",  'Polygons: ' + str(self.loadDlg.tblMaps.item(self.loadDlg.tblMaps.currentRow(), 1).text()), "memory")

                QgsProject.instance().addMapLayer(destPoint)
                QgsProject.instance().addMapLayer(destLine)
                QgsProject.instance().addMapLayer(destPoly)

                # Add attributes:
                srcAtts = srcLayer.dataProvider().fields().toList()

                destPointData = destPoint.dataProvider()
                destPointData.addAttributes(srcAtts)
                destPoint.updateFields()

                destLineData = destLine.dataProvider()
                destLineData.addAttributes(srcAtts)
                destLine.updateFields()

                destPolyData = destPoly.dataProvider()
                destPolyData.addAttributes(srcAtts)
                destPoly.updateFields()

                # Add the features themselves:
                for feat in srcLayer.getFeatures():
                    if QgsWkbTypes.flatType(feat.geometry().wkbType()) == QgsWkbTypes.Point:
                        destPointData.addFeatures([feat])
                    elif QgsWkbTypes.flatType(feat.geometry().wkbType()) == QgsWkbTypes.LineString:
                        destLineData.addFeatures([feat])
                    elif QgsWkbTypes.flatType(feat.geometry().wkbType()) == QgsWkbTypes.Polygon:
                        destPolyData.addFeatures([feat])

                # Clean up
                del srcLayer
                # Close (and automatically delete) file:
                tempKML.close() 

                # Make sure it's visible:
                self.iface.mapCanvas().zoomToFullExtent()

                # TODO: Longer term - pull SMJSON instead and convert directly, possibly including published styles, so the map looks exactly the same
            else:
                QMessageBox.information(None, "Unable to Load", "Unable to load the map! There was no data returned.", QMessageBox.Ok)

            progressBar.close()

        except Exception as e:
            self.handleException(e)

    def _loadSelectedMapInternal(self):
        mapResult = requests.get('https://www.scribblemaps.com/api/maps/' + self.lastSelectedMapCode + '/kml', headers={ 'Authorization': 'Bearer ' + self.current_token})
        self.lastLoadedMap = mapResult.content

    def showLoadDlg(self):
        self.loadDlg.show()
        self.loadDlg.raise_()
        self.loadDlg.activateWindow()

    def showPublishDlg(self):
        self.publishDlg.lstLayers.clear()
        for layer in QgsProject.instance().mapLayers().values():
            newItem = QListWidgetItem(layer.name(), self.publishDlg.lstLayers)
            newItem.setCheckState(Qt.Checked)
            self.publishDlg.lstLayers.addItem(newItem)

        if (self.publishDlg.lstLayers.count() == 0):
            QMessageBox.information(None, "No Layers", "There are no layers in your map yet! Please add some data first before publishing.")
            return

        self.publishDlg.show()
        self.publishDlg.raise_()
        self.publishDlg.activateWindow()

    def closePublishDlg(self):
        self.publishDlg.hide()

    def publishMap(self):
        self.checkAuth(self.publishMapInternal)
        
        # Check to see if we need to show a message box - has to be done in main therad, or QGIS will hard crash, at least on OSX
        if self.pendingErrorDisplay:
            QMessageBox.information(None, "Error Encountered", self.pendingErrorDisplay)
            self.pendingErrorDisplay = False

        # Display share URL for the map in a success modal - have to do this in main thread:
        if self.lastPublishedMapCode:
            self.successDialog.lblLink.setText('<a href="https://www.scribblemaps.com/maps/view/' + self.lastPublishedMapCode + '">https://www.scribblemaps.com/maps/view/' + self.lastPublishedMapCode + '</a>')
            self.successDialog.lblLink.setTextFormat(Qt.RichText)
            self.successDialog.lblLink.setTextInteractionFlags(Qt.TextBrowserInteraction)
            self.successDialog.lblLink.setOpenExternalLinks(True)
            self.successDialog.pbClose.clicked.connect(self.closeShareViewDialog)
            self.successDialog.pbCopyLink.clicked.connect(self.copyShareViewLink)
            self.successDialog.pbVisitMap.clicked.connect(self.navigateToShareViewLink)
            self.successDialog.show()
            self.successDialog.raise_()
            self.successDialog.activateWindow()

    def publishMapInternal(self):
        try:
            # Export all the selected layers to KML to handle in turn:
            self.pendingConversionTempFiles = []
            LatLongCRS = QgsCoordinateReferenceSystem("EPSG:4326")

            for i in range(self.publishDlg.lstLayers.count()):
                if (self.publishDlg.lstLayers.item(i).checkState() == Qt.Checked):
                    tempKML = NamedTemporaryFile()
                    tempKMLName = tempKML.name + ".kml"
                    tempKML.close()
                    tempLyr = QgsProject.instance().mapLayersByName(self.publishDlg.lstLayers.item(i).text())[0]
                    options = QgsVectorFileWriter.SaveVectorOptions()
                    options.driverName = "KML"
                    (errCode, errMsg) = QgsVectorFileWriter.writeAsVectorFormatV2(tempLyr, tempKMLName, QgsCoordinateTransformContext(), options)
                    if errCode == QgsVectorFileWriter.NoError and os.path.isfile(tempKMLName):
                        self.pendingConversionTempFiles.append(tempKMLName)
                    else:
                        self.pendingErrorDisplay = "Error Exporting Layer", "We were uanble to export a layer! Aborting. The error message was: " + errMsg
                        return

            # Fire off a new thread to convert these to SMJSON and do the rest of the magic:
            progressBar = QProgressDialog('Processing map for upload...', None, 0, 100)
            progressBar.setWindowTitle('Please Wait...')
            progressBar.setWindowModality(Qt.WindowModal)
            progressBar.setAutoClose(False)
            progressBar.setMinimumDuration(100)
            progressBar.setWindowFlags(progressBar.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
            progressBar.show()
            progressBar.raise_()
            progressBar.activateWindow()
            progressBar.setValue(0)
            progressBar.setMaximum(100)
            thread = threading.Thread(target = self._publishMapInternal)
            thread.start()
            while thread.is_alive():
                QApplication.processEvents()
                thread.join(0.2)
                progressBar.setValue((progressBar.value() + 1 % 100))

            progressBar.close()
        except Exception as e:
            self.handleException(e)

    def closeShareViewDialog(self):
        self.successDialog.hide()
    
    def copyShareViewLink(self):
        cb = QApplication.clipboard()
        cb.clear(mode=cb.Clipboard)
        cb.setText('https://www.scribblemaps.com/maps/view/' + self.lastPublishedMapCode, mode=cb.Clipboard)

    def navigateToShareViewLink(self):
        QDesktopServices.openUrl(QUrl('https://www.scribblemaps.com/maps/view/' + self.lastPublishedMapCode))

    def _publishMapInternal(self):
        self.lastPublishedMapCode = False

        # Convert our KML files to SMJSON strings:
        try:
            mergedSMJSON = False
            for kmlTempFile in self.pendingConversionTempFiles:
                with open(kmlTempFile, "rb") as kmlFileReader:
                    files = {'file': ('data.kml', kmlFileReader, 'application/vnd.google-earth.kml+xml', {'Expires': '0'})}
                    result = requests.post('https://www.scribblemaps.com/api/import/kml', files=files)
                    thisLayer = result.json()
                    if (not mergedSMJSON):
                        mergedSMJSON = thisLayer
                    else:
                        # Merge it all into one SMJSON file - outer overlays object can contain each layer as a separate overlay entry
                        for overlay in thisLayer["overlays"]:
                            mergedSMJSON["overlays"].append(overlay)

                    kmlFileReader.close()
                    os.unlink(kmlTempFile)

            # Get center of all data in the map:
            fullExtentsCenter = self.iface.mapCanvas().fullExtent().center()

            # At this poing we have mergedSMJSON that has all the features from all our layers - update our map type:
            if not "view" in mergedSMJSON:
                mergedSMJSON["view"] = { 
                    'mapType': self.publishDlg.cmbMapType.currentText().lower().replace('scribble maps ', 'sm_'),
                    'zoom': 10,
                    'center': [
                        fullExtentsCenter.y(),
                        fullExtentsCenter.x()
                    ]
                }
            else:
                mergedSMJSON["view"]["mapType"] = self.publishDlg.cmbMapType.currentText().lower().replace('scribble maps ', 'sm_')
                mergedSMJSON["view"]["zoom"] = 10
                mergedSMJSON["view"]["center"] = [
                    fullExtentsCenter.y(),
                    fullExtentsCenter.x()
                ]

            # Next, Call the get new map code to get a valid map code - note no bearer token needed here
            response = requests.get('https://www.scribblemaps.com/api/maps/newCode')
            self.lastPublishedMapCode = str(response.text).replace('"', '')

            # Lastly, save SMJSON - new stream, then save stream portion

            # Create new stream:
            response = requests.post('https://www.scribblemaps.com/api/maps/' + self.lastPublishedMapCode + '/stream/new', headers={ 'Authorization': 'Bearer ' + self.current_token}, data={
                'title': self.publishDlg.txtMapTitle.text(),
                'description': self.publishDlg.plntxtMapDescription.toPlainText(),
                'password': None,
                'format': "smjsonUTF8",
                'lang': "en",
                'lat': fullExtentsCenter.y(),
                'lng': fullExtentsCenter.x(),
                'mapTypeId': 0,
                'baseMap': self.publishDlg.cmbMapType.currentText().lower().replace('scribble maps ', 'sm_'),
                'listed': 0,
                'secure': 0,
                'version': "2.1",
                'charLength': len(json.dumps(mergedSMJSON))
            })
            
            if response.status_code == 402:
                # 402 = too many maps (spec = reserved for future use)
                self.pendingErrorDisplay = "We were unable to publish your map. You appear to be using the maximum number of maps allowed under the free plan.";
                self.lastPublishedMapCode = False
                return

            if not response.status_code == 200:
                QgsMessageLog.logMessage('Getting Map Code - ' + str(response.status_code) + ': ' + response.text, 'Debug Output')
                self.pendingErrorDisplay = "We were unable to retrieve a map code to publish! Please check the 'Debug Output' tab for any relevant messages."
                self.lastPublishedMapCode = False
                return

            responseJSON = response.json()
            if not responseJSON or not "streamCode" in responseJSON:
                QgsMessageLog.logMessage('Creating Stream - ' + str(response.status_code) + ': ' + response.text, 'Debug Output')
                self.pendingErrorDisplay = "We were unable to retrieve a map code to publish! Please check the 'Debug Output' tab for any relevant messages."
                self.lastPublishedMapCode = False
                return

            createStreamResultGUID = responseJSON["streamCode"]          

            # Save SMJSON to stream:
            response = requests.post('https://www.scribblemaps.com/api/maps/' + self.lastPublishedMapCode + '/stream', headers={ 'Authorization': 'Bearer ' + self.current_token}, data={
                'streamCode': createStreamResultGUID,
                'data': json.dumps(mergedSMJSON)
            })
            if not response.status_code == 200:
                QgsMessageLog.logMessage('Publishing SMJSON to Stream - ' + str(response.status_code) + ': ' + response.text, 'Debug Output')
                QgsMessageLog.logMessage('JSON body being published: ' + json.dumps(mergedSMJSON), 'Debug Output')
                self.pendingErrorDisplay = "We did not receive a successful status when publishing map data! Please check the 'Debug Output' tab for any relevant messages."
                self.lastPublishedMapCode = False
                return

            # TODO: Version 2 or 3 perhaps - include any styling info present in QGIS, pushing into SMJSON
        except Exception as e:
            self.handleException(e)
