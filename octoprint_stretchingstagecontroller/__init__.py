# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import re

import octoprint.plugin
import serial.tools.list_ports
import os
import os.path
from os import path
import threading
import serial

global all_coms_opened


class StretchingStagePlugin(octoprint.plugin.StartupPlugin,
							octoprint.plugin.TemplatePlugin,
							octoprint.plugin.AssetPlugin,
							octoprint.plugin.EventHandlerPlugin,
							octoprint.plugin.SettingsPlugin,
							octoprint.plugin.SimpleApiPlugin):
	stop = threading.Event()
	read_serial_data = False
	com_connected = False
	save_path = None

	comPorts = {}

	def on_shutdown(self):
		self.stop.set()

	def on_stop(self):
		self.stop.set()

	def start_serial_thread(self, port):
		threading.Thread(target=self.serial_thread, args=(port,)).start()

	def serial_thread(self, port):
		global all_coms_opened
		current_com = self.comPorts[port]

		# When this thread is initialized, open serial port
		try:
			current_com.ser = serial.Serial(
				port=port,
				baudrate=57600,
				parity=serial.PARITY_NONE,
				stopbits=serial.STOPBITS_ONE,
				bytesize=serial.EIGHTBITS,
				timeout=0)
			self._logger.info("Connected to COM port {x} for data readout".format(x=port))
			self._plugin_manager.send_plugin_message(self._identifier, dict(message="ComConnected", port=port))
			current_com["com_connected"] = True
		except:
			self._logger.error("COM port {x} could not be opened - data cannot be collected".format(x=port))
			self._plugin_manager.send_plugin_message(self._identifier, dict(message="ComNotConnected", port=port))
			current_com["com_connected"] = False
			all_coms_opened = False
			return

		current_com.ser.flushInput()
		current_com.ser.flushOutput()

		if not all_coms_opened:
			self._logger.error("One of the other com ports failed to connect or lost connection.")
			return

		self.validate_save_path(port)

		# if self.f:
		# 	self.f.close()

		current_com.f = open(current_com.save_path, "x")

		while True:
			if not all_coms_opened:
				self._logger.error("One of the com ports failed to connect or lost connection.")
				return

			if current_com.read_serial_data:
				current_com.f.write(current_com.ser.readline().decode('utf-8'))

			# If GUI is closed, stop this thread so python can exit fully
			if self.stop.is_set():
				self._logger.info("The serial thread for port {} is being shut down.".format(port))
				current_com.f.close()
				current_com.com_connected = False
				return

	def on_after_startup(self):
		self._logger.info("Stretching Stage controller starting up...")

	def get_assets(self):
		return dict(
			js=["js/stretchingstagecontroller.js"]
		)

	def on_event(self, event, payload):
		if event == octoprint.events.Events.PRINT_STARTED:
			for p in self.comPorts:
				curr_com = self.comPorts[p]
				if curr_com["com_connected"]:
					if curr_com["save_path"] is not None:
						if not curr_com["f"]:
							curr_com["f"] = open(curr_com["save_path"].save_path, "x")
						curr_com["ead_serial_data"] = True
						self._logger.info("Starting read from serial port {}...".format(p))
						self._plugin_manager.send_plugin_message(self._identifier, dict(message="data_collected"))

		if event == octoprint.events.Events.PRINT_DONE:
			for p in self.comPorts:
				curr_com = self.comPorts[p]
				if curr_com["read_serial_data"]:
					curr_com["read_serial_data"] = False
					curr_com["f"].close()
			self._logger.info("Print complete.")

		if event == octoprint.events.Events.PRINT_FAILED:
			for p in self.comPorts:
				curr_com = self.comPorts[p]
				if curr_com["read_serial_data"]:
					curr_com["read_serial_data"] = False
					curr_com["f"].close()
					self._logger.info("Print failed.")

		if event == octoprint.events.Events.PRINT_CANCELLING:
			for p in self.comPorts:
				curr_com = self.comPorts[p]
				if curr_com["read_serial_data"]:
					curr_com["read_serial_data"] = False
					curr_com["f"].close()
				self._logger.info("Print cancelled.")

	def get_template_configs(self):
		return [
			dict(type="settings", custom_bindings=False),
			dict(type="tab", custom_bindings=False)
		]

	def get_settings_defaults(self):
		return dict(
			save_path="/home/pi"
			# port_options = [comport.device for comport in serial.tools.list_ports.comports()],
			# serial_read_port = ""

		)

	def get_api_commands(self):
		return dict(
			validateSettings=["save_path", "file_name"],
			connectCOM=["serial_read_port"],
			disconnectCOM=["serial_read_port"]
		)

	def on_api_command(self, command, data):
		if command == "validateSettings":
			if "save_path" in data:
				self._logger.info("Parameters Received. Save path is {save_path}".format(**data))
				parameter = "set"
				dir_exists = path.exists("{save_path}".format(**data))
				file_exists = path.exists("{save_path}{file_name}".format(**data))
				if "{save_path}".format(**data)[-1] != "/":
					self._plugin_manager.send_plugin_message(self._identifier, dict(message="path_missing_slash"))
				else:
					if dir_exists:
						self._logger.info("Settings directory exists and is ready for readout")
						if file_exists:
							self._logger.info(
								"*******WARNING******** File you are attempting to write to already exists- file will be appended")
							self._plugin_manager.send_plugin_message(self._identifier, dict(message="invalid_filename"))
						else:
							self._logger.info("New file being created.")
							self._plugin_manager.send_plugin_message(self._identifier, dict(message="valid_filename"))
							self.save_path = "{save_path}{file_name}".format(**data)
					else:
						self._logger.info(
							"*******WARNING******** Save directory for Stretching Stage Controller does not exist!"
							" Please pick a valid save directory")
						self._plugin_manager.send_plugin_message(self._identifier, dict(message="path_does_not_exist"))

		if command == "connectCOM":
			if "serial_read_port" in data:
				port_list = data["serial_read_port"].split(',')
				ports = [p.strip() for p in port_list]
				self._logger.info(ports)
				self._logger.info("connectCOM called. Port(s) detected: {}".format(ports))
				global all_coms_opened
				all_coms_opened = True
				for p in ports:
					data["serial_read_port"] = p
					self.start_serial_thread("{serial_read_port}".format(**data))

		if command == "disconnectCOM":
			self.stop.set()
			self._plugin_manager.send_plugin_message(self._identifier, dict(message="com_disconnected"))

	def validate_save_path(self, port):
		escaped_port = re.sub('[^A-Za-z0-9]+', '_', port)
		ext_index = self.save_path.index(".")
		self.save_path = self.save_path[:ext_index] + escaped_port + self.save_path[ext_index:]
		self._logger.info("Save path modified for com port: {}".format(self.save_path))
		append_num = 1
		ext_index = self.save_path.index(".")
		new_save_path = self.save_path
		while path.exists(new_save_path):
			new_save_path = self.save_path[:ext_index] + "(" + str(append_num) + ")" + self.save_path[ext_index:]
			append_num += 1
		self.save_path = new_save_path
		self._logger.info("Final save paths: {}".format(self.save_path))


__plugin_name__ = "Stretching Stage Controller"
__plugin_pythoncompat__ = ">=2.7,<4"
__plugin_implementation__ = StretchingStagePlugin()
