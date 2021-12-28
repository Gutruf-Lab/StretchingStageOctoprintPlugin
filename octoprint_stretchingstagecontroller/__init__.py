# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import re
import octoprint.plugin
from octoprint.util import RepeatedTimer
import serial.tools.list_ports
import os
from os import path
import threading
import serial


class CommunicationPort:
	stop = threading.Event()

	def __init__(self, port=None, logger=None, plugin_manager=None, identifier=None, baud=57600):
		self.port = port
		self._logger = logger
		self._plugin_manager = plugin_manager
		self._identifier = identifier
		self.f = None
		self.read_serial_data = False
		self.save_path = None
		self.com_connected = False
		self.ser = None
		self.baud = baud

	def __str__(self):
		return self.port

	def on_stop(self):
		self.stop.set()

	def serial_thread(self):
		# When this thread is initialized, open serial port
		try:
			self.ser = serial.Serial(
				port=self.port,
				baudrate=self.baud,
				parity=serial.PARITY_NONE,
				stopbits=serial.STOPBITS_ONE,
				bytesize=serial.EIGHTBITS,
				timeout=0)
			self._logger.info("Connected to COM port {} for data readout".format(self.port))
			self._plugin_manager.send_plugin_message(self._identifier, dict(message="ComConnected", port=self.port))
			self.com_connected = True
			self.stop.clear()
		except:
			self._logger.error("COM port {} could not be opened - data cannot be collected".format(self.port))
			self._plugin_manager.send_plugin_message(self._identifier, dict(message="ComNotConnected", port=self.port))
			self.com_connected = False
			return

		self.ser.flushInput()
		self.ser.flushOutput()

		while True:
			if self.read_serial_data:
				self.f.write(self.ser.readline().decode('utf-8'))
			# If GUI is closed, stop this thread so python can exit fully
			if self.stop.is_set():
				self.com_connected = False
				if self.f:
					self.f.close()
				self.ser.close()
				self._logger.info("The serial thread for port {} is being shut down.".format(self.port))
				return

	def on_event(self, event, payload):
		if event == octoprint.events.Events.PRINT_STARTED:
			if self.com_connected:
				if self.save_path is not None:
					self.f = open(self.save_path, "x")
					self.read_serial_data = True
					self._logger.info("Starting read from serial port {}...".format(self.port))
					self._plugin_manager.send_plugin_message(self._identifier, dict(message="data_collected"))
		if event in [octoprint.events.Events.PRINT_DONE,
					 octoprint.events.Events.PRINT_FAILED,
					 octoprint.events.Events.PRINT_CANCELLING]:
			if self.read_serial_data:
				self.read_serial_data = False
				self.ser.close()
				self.f.close()

	"""
		Takes the name of the com port we're using, such as '/dev/ttyUSB0' and uses a regex to escape all the characters
		which are not letters nor numbers. They are replaced with underscores. E.g. '/dev/ttyUSB0' -> '_dev_ttyUSB0'
		Then takes the existing save path, such as '/home/pi/example.txt' and inserts the escaped com port name
		before the extension '.txt'. E.g. '/home/pi/example.txt' -> '/home/pi/example_dev_ttyUSB0.txt'
		Finally, if that file name already exists, it creates an incremented version '/home/pi/example_dev_ttyUSB0__2.txt'
	"""

	def handle_save_path(self):
		escaped_port = re.sub('[^A-Za-z0-9]+', '_', self.port)
		dot_index = self.save_path.index(".")
		self.save_path = self.save_path[:dot_index] + escaped_port + self.save_path[dot_index:]

		append_num = 1
		dot_index = self.save_path.index(".")
		new_save_path = self.save_path

		while path.exists(new_save_path):
			new_save_path = self.save_path[:dot_index] + "__" + str(append_num) + self.save_path[dot_index:]
			append_num += 1
		self.save_path = new_save_path
		self._logger.info("New save path for com port {}: {}".format(self.port, self.save_path))


class StretchingStagePlugin(octoprint.plugin.StartupPlugin,
							octoprint.plugin.TemplatePlugin,
							octoprint.plugin.AssetPlugin,
							octoprint.plugin.EventHandlerPlugin,
							octoprint.plugin.SettingsPlugin,
							octoprint.plugin.SimpleApiPlugin):
	stop = threading.Event()
	comPorts = []
	filesize_timer = None

	def on_shutdown(self):
		self.stop.set()

	def on_stop(self):
		self.stop.set()

	def on_after_startup(self):
		self._logger.info("Stretching Stage controller starting up...")
		self.filesize_timer = RepeatedTimer(10.0, self.fetch_file_sizes)

	def get_assets(self):
		return dict(
			js=["js/stretchingstagecontroller.js"],
			css=["css/stretchingstagecontroller.css"]
		)

	def start_serial_thread(self, port):
		threading.Thread(target=port.serial_thread).start()

	def stop_all_coms(self):
		self.filesize_timer.cancel()
		# We iterate over a copy of the list. Deleting while iterating across a list leads to some funky behavior.
		for p in self.comPorts[:]:
			self._plugin_manager.send_plugin_message(self._identifier, dict(message="com_disconnected", port=p.port))
			p.stop.set()
			self.comPorts.remove(p)

	def on_event(self, event, payload):
		for p in self.comPorts:
			p.on_event(event, payload)
		if event == octoprint.events.Events.PRINT_STARTED:
			self._logger.info("Print started.")
		if event == octoprint.events.Events.PRINT_DONE:
			self._logger.info("Print completed successfully.")
			self.stop_all_coms()
		if event == octoprint.events.Events.PRINT_FAILED:
			self._logger.info("Print failed.")
			self.stop_all_coms()
		if event == octoprint.events.Events.PRINT_CANCELLING:
			self._logger.info("Print cancelled.")
			self.stop_all_coms()

	def get_template_configs(self):
		return [
			dict(type="settings", custom_bindings=False),
			dict(type="tab", custom_bindings=False)
		]

	def get_settings_defaults(self):
		return dict(
			stretchingstagecontroller_baud_rate=57600
		)

	def get_api_commands(self):
		return dict(
			fetchPorts=["type"],
			validateSettings=["file_name"],
			connectCOM=["serial_read_ports"],
			disconnectCOM=[]
		)

	def fetch_file_sizes(self):
		file_data = []
		for p in self.comPorts:
			port = {
				"path": p.save_path,
				"file_size": os.path.getsize(p.save_path)
			}
			file_data.extend(port)

		self._plugin_manager.send_plugin_message(
			self._identifier,
			dict(
				message="file_sizes_fetched",
				file_data=file_data,
			)
		)

	def on_api_command(self, command, data):
		# Two different types of fetching ports:
		# 1. List all com ports that we are able to establish a connection with
		# 2. List all ports that we have already established a connection with
		if command == "fetchPorts":
			list_of_ports = []
			if data["type"] == "available":
				list_of_ports = [p.__dict__ for p in serial.tools.list_ports.comports()]
			elif data["type"] == "currently_connected":
				list_of_ports = [p.port for p in self.comPorts if p.com_connected]

			self._plugin_manager.send_plugin_message(
				self._identifier,
				dict(
					message="ports_fetched",
					ports=list_of_ports,
					type=data["type"]))

		# Mostly retaining Megan's code. We run validate_save_path() to handle existing files, duplicates, and to
		# create a distinct logfile for each com port that we're connected to.
		if command == "validateSettings":
			if "save_path" in data:
				self._logger.info("Save path is /home/pi/stretchingStage/".format(**data))
				os.makedirs("/home/pi/stretchingStage/", exist_ok=True)
				self._logger.info("New file(s) being created.")
				self._plugin_manager.send_plugin_message(self._identifier, dict(message="valid_filename"))
				for p in self.comPorts:
					p.save_path = "/home/pi/stretchingStage/{file_name}".format(**data)
					p.handle_save_path()

		# The data from the plugin controls is sent across as a list. We separate and create new objs for each.
		if command == "connectCOM":
			if "serial_read_ports" in data:
				ports = [p for p in data["serial_read_ports"]]
				self._logger.info("connectCOM called. Port(s) detected: {}".format(ports))
				for p in ports:
					new_com = CommunicationPort(
						p,
						self._logger,
						self._plugin_manager,
						self._identifier,
						self._settings.get_int(["stretchingstagecontroller_baud_rate"])
					)
					self.comPorts.append(new_com)
				for p in self.comPorts:
					self.start_serial_thread(p)
				self.filesize_timer.start()

		if command == "disconnectCOM":
			self.stop_all_coms()


__plugin_name__ = "Stretching Stage Controller"
__plugin_pythoncompat__ = ">=2.7,<4"
__plugin_implementation__ = StretchingStagePlugin()
