# -*- coding: utf-8 -*-
#
# Copyright © 2008-2022 Saeed Rasooli <saeed.gnu@gmail.com> (ilius)
# This file is part of PyGlossary project, https://github.com/ilius/pyglossary
#
# This program is a free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program. Or on Debian systems, from /usr/share/common-licenses/GPL
# If not, see <http://www.gnu.org/licenses/gpl.txt>.

import logging
import sys
import os

from .plugin_prop import PluginProp
from .glossary_utils import (
	splitFilenameExt,
)
from . import core
from .core import (
	pluginsDir,
)

log = logging.getLogger("pyglossary")


class PluginManager(object):
	plugins = {}  # type: Dict[str, PluginProp]
	pluginByExt = {}  # type: Dict[str, PluginProp]
	loadedModules = set()

	formatsReadOptions = {}  # type: Dict[str, OrderedDict[str, Any]]
	formatsWriteOptions = {}  # type: Dict[str, OrderedDict[str, Any]]
	# for example formatsReadOptions[format][optName] gives you the default value

	readFormats = []  # type: List[str]
	writeFormats = []  # type: List[str]

	@classmethod
	def loadPluginsFromJson(cls: "ClassVar", jsonPath: str) -> None:
		import json
		from os.path import dirname, join

		with open(jsonPath) as _file:
			data = json.load(_file)

		for attrs in data:
			moduleName = attrs["module"]
			cls.loadPluginByDict(
				attrs=attrs,
				modulePath=join(pluginsDir, moduleName),
			)
			cls.loadedModules.add(moduleName)

	@classmethod
	def loadPlugins(
		cls: "ClassVar",
		directory: str,
		skipDisabled: bool = True,
	) -> None:
		"""
		executed on startup. as name implies, loads plugins from directory
		it skips importing plugin modules that are already loaded
		"""
		import pkgutil
		from os.path import isdir

		# log.debug(f"Loading plugins from directory: {directory!r}")
		if not isdir(directory):
			log.critical(f"Invalid plugin directory: {directory!r}")
			return

		moduleNames = [
			moduleName
			for _, moduleName, _ in pkgutil.iter_modules([directory])
			if moduleName not in cls.loadedModules and
			moduleName not in ("paths", "formats_common")
		]
		moduleNames.sort()

		sys.path.append(directory)
		for moduleName in moduleNames:
			cls.loadPlugin(moduleName, skipDisabled=skipDisabled)
		sys.path.pop()

	@classmethod
	def loadPluginByDict(
		cls: "ClassVar",
		attrs: "Dict[str, Any]",
		modulePath: str,
	) -> None:
		format = attrs["name"]

		extensions = attrs["extensions"]
		prop = PluginProp.fromDict(
			attrs=attrs,
			modulePath=modulePath,
		)

		cls.plugins[format] = prop
		cls.loadedModules.add(attrs["module"])

		if not prop.enable:
			return

		for ext in extensions:
			if ext.lower() != ext:
				log.error(f"non-lowercase extension={ext!r} in {moduleName} plugin")
			cls.pluginByExt[ext.lstrip(".")] = prop
			cls.pluginByExt[ext] = prop

		if attrs["canRead"]:
			cls.formatsReadOptions[format] = attrs["readOptions"]
			cls.readFormats.append(format)

		if attrs["canWrite"]:
			cls.formatsWriteOptions[format] = attrs["writeOptions"]
			cls.writeFormats.append(format)

		if log.level <= core.TRACE:
			prop.module  # to make sure importing works

	@classmethod
	def loadPlugin(
		cls: "ClassVar",
		moduleName: str,
		skipDisabled: bool = True,
	) -> None:
		log.debug(f"importing {moduleName} in loadPlugin")
		try:
			module = __import__(moduleName)
		except ModuleNotFoundError as e:
			log.warning(f"Module {e.name!r} not found, skipping plugin {moduleName!r}")
			return
		except Exception as e:
			log.exception(f"Error while importing plugin {moduleName}")
			return

		enable = getattr(module, "enable", False)
		if skipDisabled and not enable:
			# log.debug(f"Plugin disabled or not a module: {moduleName}")
			return

		name = module.format

		prop = PluginProp.fromModule(module)

		cls.plugins[name] = prop
		cls.loadedModules.add(moduleName)

		if not enable:
			return

		for ext in prop.extensions:
			if ext.lower() != ext:
				log.error(f"non-lowercase extension={ext!r} in {moduleName} plugin")
			cls.pluginByExt[ext.lstrip(".")] = prop
			cls.pluginByExt[ext] = prop

		if prop.canRead:
			options = prop.getReadOptions()
			cls.formatsReadOptions[name] = options
			cls.readFormats.append(name)

		if prop.canWrite:
			options = prop.getWriteOptions()
			cls.formatsWriteOptions[name] = options
			cls.writeFormats.append(name)

	@classmethod
	def findPlugin(cls, query: str) -> "Optional[PluginProp]":
		"""
			find plugin by name or extension
		"""
		plugin = cls.plugins.get(query)
		if plugin:
			return plugin
		plugin = cls.pluginByExt.get(query)
		if plugin:
			return plugin
		return None

	@classmethod
	def detectInputFormat(
		cls,
		filename: str,
		format: str = "",
		quiet: bool = False,
	) -> "Optional[Tuple[str, str, str]]":
		"""
			returns (filename, format, compression) or None
		"""

		def error(msg: str) -> None:
			if not quiet:
				log.critical(msg)
			return None

		filenameOrig = filename
		filenameNoExt, filename, ext, compression = splitFilenameExt(filename)

		plugin = None
		if format:
			plugin = cls.plugins.get(format)
			if plugin is None:
				return error(f"Invalid format {format!r}")
		else:
			plugin = cls.pluginByExt.get(ext)
			if not plugin:
				plugin = cls.findPlugin(filename)
				if not plugin:
					return error("Unable to detect input format!")

		if not plugin.canRead:
			return error(f"plugin {plugin.name} does not support reading")

		if compression in plugin.readCompressions:
			compression = ""
			filename = filenameOrig

		return filename, plugin.name, compression

	@classmethod
	def detectOutputFormat(
		cls,
		filename: str = "",
		format: str = "",
		inputFilename: str = "",
		quiet: bool = False,
		addExt: bool = False,
	) -> "Optional[Tuple[str, str, str]]":
		"""
		returns (filename, format, compression) or None
		"""
		from os.path import splitext

		def error(msg: str) -> None:
			if not quiet:
				log.critical(msg)
			return None

		plugin = None
		if format:
			plugin = cls.plugins.get(format)
			if not plugin:
				return error(f"Invalid format {format}")
			if not plugin.canWrite:
				return error(f"plugin {plugin.name} does not support writing")

		if not filename:
			if not inputFilename:
				return error(f"Invalid filename {filename!r}")
			if not plugin:
				return error("No filename nor format is given for output file")
			filename = splitext(inputFilename)[0] + plugin.ext
			return filename, plugin.name, ""

		filenameOrig = filename
		filenameNoExt, filename, ext, compression = splitFilenameExt(filename)

		if not plugin:
			plugin = cls.pluginByExt.get(ext)
			if not plugin:
				plugin = cls.findPlugin(filename)

		if not plugin:
			return error("Unable to detect output format!")

		if not plugin.canWrite:
			return error(f"plugin {plugin.name} does not support writing")

		if compression in getattr(plugin.writerClass, "compressions", []):
			compression = ""
			filename = filenameOrig

		if addExt:
			if not filenameNoExt:
				if inputFilename:
					ext = plugin.ext
					filename = splitext(inputFilename)[0] + ext
				else:
					log.error("inputFilename is empty")
			if not ext and plugin.ext:
				filename += plugin.ext

		return filename, plugin.name, compression
