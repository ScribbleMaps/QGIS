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

# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    from .scribblemaps_connector import ScribbleMapsConnector
    return ScribbleMapsConnector(iface)
