from asyncio.tasks import sleep
import threading
import errno
import select
import socket
import json
import requests
from requests.exceptions import ConnectionError
from json import JSONDecodeError
import atexit
import time
import asyncio
import os

class xyze_t:
	x = 0.0
	y = 0.0
	z = 0.0
	e = 0.0
	home_x = False
	home_y = False
	home_z = False
	updated = False

class AxisEnum:
	X_AXIS = 0
	A_AXIS = 0
	Y_AXIS = 1
	B_AXIS = 1
	Z_AXIS = 2
	C_AXIS = 2
	E_AXIS = 3
	X_HEAD = 4
	Y_HEAD = 5
	Z_HEAD = 6
	E0_AXIS = 3
	E1_AXIS = 4
	E2_AXIS = 5
	E3_AXIS = 6
	E4_AXIS = 7
	E5_AXIS = 8
	E6_AXIS = 9
	E7_AXIS = 10
	ALL_AXES = 0xFE
	NO_AXIS = 0xFF

class HMI_value_t:
	E_Temp = 0
	Bed_Temp = 0
	Fan_speed = 0
	print_speed = 100
	Max_Feedspeed = 0.0
	Max_Acceleration = 0.0
	Max_Jerk = 0.0
	Max_Step = 0.0
	Move_X_scale = 0.0
	Move_Y_scale = 0.0
	Move_Z_scale = 0.0
	Move_E_scale = 0.0
	offset_value = 0.0
	show_mode = 0  # -1: Temperature control    0: Printing temperature

class HMI_Flag_t:
	language = 0
	pause_flag = False
	pause_action = False
	print_finish = False
	done_confirm_flag = False
	select_flag = False
	home_flag = False
	heat_flag = False  # 0: heating done  1: during heating
	ETempTooLow_flag = False
	leveling_offset_flag = False
	feedspeed_axis = AxisEnum()
	acc_axis = AxisEnum()
	jerk_axis = AxisEnum()
	step_axis = AxisEnum()

class buzz_t:
	def tone(self, t, n):
		pass

class material_preset_t:
	def __init__(self, name, hotend_temp, bed_temp, fan_speed=100):
		self.name = name
		self.hotend_temp = hotend_temp
		self.bed_temp = bed_temp
		self.fan_speed = fan_speed

class KlippySocket:
	def __init__(self, uds_filename, callback=None):
		self.connected = False
		self.webhook_socket_create(uds_filename)
		self.lock = threading.Lock()
		self.poll = select.poll()
		self.stop_threads = False
		self.poll.register(self.webhook_socket, select.POLLIN | select.POLLHUP)
		self.socket_data = ""
		self.t = threading.Thread(target=self.polling)
		self.callback = callback
		self.lines = []
		self.t.start()
		atexit.register(self.klippyExit)

	def klippyExit(self):
		print("Shuting down Klippy Socket")
		self.stop_threads = True
		self.t.join()

	def webhook_socket_create(self, uds_filename):
		self.webhook_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		self.webhook_socket.setblocking(0)
		print("Waiting for connect to %s\n" % (uds_filename,))
		while 1:
			try:
				self.webhook_socket.connect(uds_filename)
			except socket.error as e:
				if e.errno == errno.ECONNREFUSED:
					time.sleep(0.1)
					continue
				print(
					"Unable to connect socket %s [%d,%s]\n" % (
						uds_filename, e.errno,
						errno.errorcode[e.errno]
					))
				exit(-1)
			break
		print("Connection.\n")
		self.connected = True

	def process_socket(self):
		data = None
		try:
			data = self.webhook_socket.recv(4096).decode()
		except:
			pass
		if not data:
			self.connected = False
			print("Socket closed\n")
			return False
		parts = data.split('\x03')
		parts[0] = self.socket_data + parts[0]
		self.socket_data = parts.pop()
		for line in parts:
			if self.callback:
				self.callback(line)

	def queue_line(self, line):
		with self.lock:
			self.lines.append(line)

	def send_line(self):
		if len(self.lines) == 0:
			return
		line = self.lines.pop(0).strip()
		if not line or line.startswith('#'):
			return
		try:
			m = json.loads(line)
		except JSONDecodeError:
			print("ERROR: Unable to parse line\n")
			return
		cm = json.dumps(m, separators=(',', ':'))
		wdm = '{}\x03'.format(cm)
		self.webhook_socket.send(wdm.encode())

	def polling(self):
		while True:
			if self.stop_threads:
				break
			res = self.poll.poll(1000.)
			for fd, event in res:
				self.process_socket()
			with self.lock:
				self.send_line()


class MoonrakerSocket:
	def __init__(self, address, port, api_key):
		self.s = requests.Session()
		self.s.headers.update({
			'X-Api-Key': api_key,
			'Content-Type': 'application/json'
		})
		self.base_address = 'http://' + address + ':' + str(port)


class PrinterData:
	event_loop = None
	HAS_HOTEND = True
	HOTENDS = 1
	HAS_HEATED_BED = True
	HAS_FAN = False
	HAS_ZOFFSET_ITEM = True
	HAS_ONESTEP_LEVELING = False
	HAS_PREHEAT = True
	HAS_BED_PROBE = False
	PREVENT_COLD_EXTRUSION = True
	EXTRUDE_MINTEMP = 170
	EXTRUDE_MAXLENGTH = 200

	HEATER_0_MAXTEMP = 275
	HEATER_0_MINTEMP = 5
	HOTEND_OVERSHOOT = 15

	MAX_E_TEMP = (HEATER_0_MAXTEMP - (HOTEND_OVERSHOOT))
	MIN_E_TEMP = HEATER_0_MINTEMP

	BED_OVERSHOOT = 10
	BED_MAXTEMP = 150
	BED_MINTEMP = 5

	BED_MAX_TARGET = (BED_MAXTEMP - (BED_OVERSHOOT))
	MIN_BED_TEMP = BED_MINTEMP

	X_MIN_POS = 0.0
	Y_MIN_POS = 0.0
	Z_MIN_POS = 0.0
	Z_MAX_POS = 200

	Z_PROBE_OFFSET_RANGE_MIN = -20
	Z_PROBE_OFFSET_RANGE_MAX = 20

	buzzer = buzz_t()

	material_preset = [
		material_preset_t('PLA', 200, 60),
		material_preset_t('ABS', 210, 100)
	]
	files = None
	MACHINE_SIZE = "220x220x250"
	SHORT_BUILD_VERSION = "1.00"
	CORP_WEBSITE_E = "https://www.klipper3d.org/"

	LED = []

	def __init__(self, API_Key, URL='127.0.0.1', callback=None):
		self.response_callback = callback
		self.BABY_Z_VAR       = 0
		self.print_speed      = 100
		self.flow_percentage  = 100
		self.led_percentage   = 0
		self.temphot          = 0
		self.tempbed          = 0
		self.HMI_ValueStruct  = HMI_value_t()
		self.HMI_flag         = HMI_Flag_t()
		self.current_position = xyze_t()
		self.gcm              = None
		self.z_offset         = 0
		self.z_requested      = 0
		self.thermalManager   = {
			'temp_bed': {'celsius': 20, 'target': 120},
			'temp_hotend': [{'celsius': 20, 'target': 120}],
			'fan_speed': [100]
		}
		self.job_Info               = None
		self.file_path              = None
		self.file_name              = None
		self.status                 = None
		self.print_time             = None
		self.print_percent			= None
		self.last_percent_update	= None
		self.max_velocity           = None
		self.max_accel              = None
		self.minimum_cruise_ratio   = None
		self.square_corner_velocity = None
		
		self.op = MoonrakerSocket(URL, 80, API_Key)
		print(self.op.base_address)

		# try to find klippy sock in Moonraker config or use generic value
		info = None
		while info is None:
			info = self.getREST("/server/config")
			time.sleep(1)

		klippy_sock_found = False
		if 'result' in info:
			if 'config' in info['result']:
				if 'server' in info['result']['config']:
					if 'klippy_uds_address' in info['result']['config']['server']:
						self.klippy_sock = os.path.expanduser(info['result']['config']['server']['klippy_uds_address'])
						klippy_sock_found = True

		if not klippy_sock_found:
			self.klippy_sock = os.path.expanduser("~/printer_data/comms/klippy.sock")


		self.klippy_start()

		self.init_features()

		self.event_loop = asyncio.new_event_loop()
		threading.Thread(target=self.event_loop.run_forever, daemon=True).start()

	# ------------- Klipper Function ----------
	def klippy_start(self):
		self.ks = KlippySocket(self.klippy_sock, callback=self.klippy_callback)
		subscribe = {
			"id": 4001,
			"method": "objects/subscribe",
			"params": {
				"objects": {
					"toolhead": [
						"position"
					]
				},
				"response_template": {}
			}
		}
		self.klippy_z_offset = '{"id": 4002, "method": "objects/query", "params": {"objects": {"configfile": ["config"]}}}'
		self.klippy_home = '{"id": 4003, "method": "objects/query", "params": {"objects": {"toolhead": ["homed_axes"]}}}'
		self.gcode = '{"id": 4004, "method": "gcode/subscribe_output", "params": {"response_template":{}}}'

		self.ks.queue_line(json.dumps(subscribe))
		self.ks.queue_line(self.klippy_z_offset)
		self.ks.queue_line(self.klippy_home)
		self.ks.queue_line(self.gcode)

	def klippy_callback(self, line):
		klippyData = json.loads(line)
		#print("klippy_callback:")
		#print(json.dumps(klippyData, indent=2))
		status = None
		if 'result' in klippyData:
			if 'status' in klippyData['result']:
				status = klippyData['result']['status']
		if 'params' in klippyData:
			if 'status' in klippyData['params']:
				status = klippyData['params']['status']
			if 'response' in klippyData['params']:
				if self.response_callback:
					resp = klippyData['params']['response']
					if 'B:' in resp and 'T0:' in resp:
						pass ## Filter out temperature responses
					else:
						self.response_callback(resp, 'response')

		if status:
			if 'toolhead' in status:
				if 'position' in status['toolhead']:
					if self.current_position.x != status['toolhead']['position'][0]:
						self.current_position.x = status['toolhead']['position'][0]
						self.current_position.updated = True
					if self.current_position.y != status['toolhead']['position'][1]:
						self.current_position.y = status['toolhead']['position'][1]
						self.current_position.updated = True
					if self.current_position.z != status['toolhead']['position'][2]:
						self.current_position.z = status['toolhead']['position'][2]
						self.current_position.updated = True
					if self.current_position.e != status['toolhead']['position'][3]:
						self.current_position.e = status['toolhead']['position'][3]
						self.current_position.updated = True
					
				if 'homed_axes' in status['toolhead']:
					if 'x' in status['toolhead']['homed_axes']:
						self.current_position.home_x = True
					else:
						self.current_position.home_x = False
					if 'y' in status['toolhead']['homed_axes']:
						self.current_position.home_y = True
					else:
						self.current_position.home_y = False
					if 'z' in status['toolhead']['homed_axes']:
						self.current_position.home_z = True
					else:
						self.current_position.home_z = False
				
				if 'max_velocity' in status['toolhead']:
					if self.max_velocity != status['toolhead']['max_velocity']:
						self.max_velocity = status['toolhead']['max_velocity']
				if 'max_accel' in status['toolhead']:
					if self.max_accel != status['toolhead']['max_accel']:
						self.max_accel = status['toolhead']['max_accel']
				if 'minimum_cruise_ratio' in status['toolhead']:
					if self.minimum_cruise_ratio != status['toolhead']['minimum_cruise_ratio']:
						self.minimum_cruise_ratio = status['toolhead']['minimum_cruise_ratio']
				if 'square_corner_velocity' in status['toolhead']:
					if self.square_corner_velocity != status['toolhead']['square_corner_velocity']:
						self.square_corner_velocity = status['toolhead']['square_corner_velocity']

			if 'configfile' in status:
				if 'config' in status['configfile']:
					if 'bltouch' in status['configfile']['config']:
						if 'z_offset' in status['configfile']['config']['bltouch']:
							if status['configfile']['config']['bltouch']['z_offset']:
								self.BABY_Z_VAR = float(status['configfile']['config']['bltouch']['z_offset'])
					if 'virtual_sdcard' in status['configfile']['config']:
						if 'path' in status['configfile']['config']['virtual_sdcard']:
							self.file_path = status['configfile']['config']['virtual_sdcard']['path']

	def init_features(self):
		try:
			objects = self.getREST('/printer/objects/list')['result']['objects']
		except:
			print("Could not read printer features objects!")
		
		for obj in objects:
			if 'led' in obj:
				led = obj.split(' ')[1]
				self.LED.append(led)

	def ishomed(self):
		if self.current_position.home_x and self.current_position.home_y and self.current_position.home_z:
			return True
		else:
			self.ks.queue_line(self.klippy_home)
			return False

	def offset_z(self, new_offset):
		self.BABY_Z_VAR = new_offset
		self.sendGCode('ACCEPT')

	def add_mm(self, axs, new_offset):
		gc = 'TESTZ Z={}'.format(new_offset)
		print(axs, gc)
		self.sendGCode(gc)

	def probe_adjust(self, change):
		if change > 0:
			strchange = "+{}".format(change)
		else:
			strchange = str(change)

		gc = 'SET_GCODE_OFFSET Z_ADJUST={} MOVE=1'.format(strchange)
		print(gc)
		self.sendGCode(gc)

	def probe_calibrate(self):
		if self.ishomed() == False:
			self.sendGCode('G28')
		self.sendGCode('PROBE_CALIBRATE')
		self.sendGCode('G1 Z0.0')

	# ------------- OctoPrint Function ----------

	def getREST(self, path):
		r = self.op.s.get(self.op.base_address + path)
		d = r.content.decode('utf-8')
		try:
			return json.loads(d)
		except JSONDecodeError:
			print('Decoding JSON has failed')
		return None

	async def _postREST(self, path, json):
		self.op.s.post(self.op.base_address + path, json=json)

	def postREST(self, path, json):
		self.event_loop.call_soon_threadsafe(asyncio.create_task,self._postREST(path,json))

	def init_Webservices(self):
		try:
			requests.get(self.op.base_address)
		except ConnectionError:
			print('Web site does not exist')
			return
		else:
			print('Web site exists')
		if self.getREST('/api/printer') is None:
			return
		self.update_variable()

		#alternative approach
		#full_version = self.getREST('/printer/info')['result']['software_version']
		#self.SHORT_BUILD_VERSION = '-'.join(full_version.split('-',2)[:2])
		self.SHORT_BUILD_VERSION = self.getREST('/machine/update/status?refresh=false')['result']['version_info']['klipper']['version']

		data = self.getREST('/printer/objects/query?toolhead')['result']['status']
		#print(json.dumps(data, indent=2))
		toolhead = data['toolhead']
		volume = toolhead['axis_maximum'] #[x,y,z,w]
		self.MACHINE_SIZE = "{}x{}x{}".format(
			int(volume[0]),
			int(volume[1]),
			int(volume[2])
		)
		self.X_MAX_POS = int(volume[0])
		self.Y_MAX_POS = int(volume[1])
		self.max_velocity           = toolhead['max_velocity']
		self.max_accel              = toolhead['max_accel']
		self.minimum_cruise_ratio   = toolhead['minimum_cruise_ratio']
		self.square_corner_velocity = toolhead['square_corner_velocity']

	def get_gcode_store(self, count=100):
		gcode_store = None
		try:
			gcode_store = self.getREST('/server/gcode_store?count=%d' % count)['result']['gcode_store']
		except:
			print("GCode store read failed!")
		
		return gcode_store
	
	def get_macros(self, filter_internal = True):
		macros = []
		try:
			objects = self.getREST('/printer/objects/list')['result']['objects']
		except:
			print("Could not read macro objects!")
		
		for obj in objects:
			if 'gcode_macro' in obj:
				macro = obj.split(' ')[1]
				if filter_internal:
					if macro[0] != '_':
						macros.append(macro)
				else:
					macros.append(macro)
		return macros	

	def GetFiles(self, refresh=False):
		if not self.files or refresh:
			try:
				self.files = self.getREST('/server/files/list')["result"]
			except:
				print("Exception 418")
		names = []
		for fl in self.files:
			names.append(fl["path"])
		return names

	def update_variable(self):
		if self.ks.connected == False:
			self.ks.klippyExit()
			self.klippy_start()
			return False
		query = '/printer/objects/query?extruder&heater_bed&gcode_move&fan&print_stats&motion_report&toolhead&display_status'

		if len(self.LED) > 0:
			query = query + '&led %s' % self.LED[0]

		try:
			data = self.getREST(query)['result']['status']
		except:
			print("Exception 431")
			return False

		#print("update_variable:")
		#print(json.dumps(data, indent=2))

		self.gcm = data['gcode_move']
		self.z_offset = self.gcm['homing_origin'][2] #z offset
		self.z_requested = data['gcode_move']['gcode_position'][2] #requested Z position
		self.flow_percentage = self.gcm['extrude_factor'] * 100 #flow rate percent
		self.absolute_moves = self.gcm['absolute_coordinates'] #absolute or relative
		self.absolute_extrude = self.gcm['absolute_extrude'] #absolute or relative
		self.speed = self.gcm['speed'] #current speed in mm/s
		self.print_speed = self.gcm['speed_factor'] * 100 #print speed percent
		self.bed = data['heater_bed'] #temperature, target
		self.extruder = data['extruder'] #temperature, target
		self.fan = data['fan']
		if self.LED and 'led %s' % self.LED[0] in data:
			self.led_percentage = int(data['led %s' % self.LED[0]]['color_data'][0][3] * 256)
		self.toolhead = data['toolhead']
		Update = False
		try:
			if self.thermalManager['temp_bed']['celsius'] != int(self.bed['temperature']):
				self.thermalManager['temp_bed']['celsius'] = int(self.bed['temperature'])
				Update = True
			if self.thermalManager['temp_bed']['target'] != int(self.bed['target']):
				self.thermalManager['temp_bed']['target'] = int(self.bed['target'])
				Update = True
			if self.thermalManager['temp_hotend'][0]['celsius'] != int(self.extruder['temperature']):
				self.thermalManager['temp_hotend'][0]['celsius'] = int(self.extruder['temperature'])
				Update = True
			if self.thermalManager['temp_hotend'][0]['target'] != int(self.extruder['target']):
				self.thermalManager['temp_hotend'][0]['target'] = int(self.extruder['target'])
				Update = True
			if self.thermalManager['fan_speed'][0] != int((self.fan['speed'] * 100) + 0.5):
				self.thermalManager['fan_speed'][0] = int((self.fan['speed'] * 100) + 0.5)
				Update = True
			if self.BABY_Z_VAR != self.z_offset:
				self.BABY_Z_VAR = self.z_offset
				self.HMI_ValueStruct.offset_value = self.z_offset * 100
				Update = True
			
			if self.max_velocity != self.toolhead['max_velocity']:
				self.max_velocity = self.toolhead['max_velocity']
				Update = True
			if self.max_accel != self.toolhead['max_accel']:
				self.max_accel = self.toolhead['max_accel']
				Update = True
			if self.minimum_cruise_ratio != self.toolhead['minimum_cruise_ratio']:
				self.minimum_cruise_ratio = self.toolhead['minimum_cruise_ratio']
				Update = True
			if self.square_corner_velocity != self.toolhead['square_corner_velocity']:
				self.square_corner_velocity = self.toolhead['square_corner_velocity']
				Update = True
		except:
			pass #missing key, shouldn't happen, fixes misses on conditionals ¯\_(ツ)_/¯
		try:
			self.job_Info = self.getREST('/printer/objects/query?virtual_sdcard&print_stats')['result']['status']
		except:
			print("Exception 470")
			return False
		
		if data['display_status']:
			if self.print_percent is not None:
				if int(self.print_percent*100) is not int(data['display_status']['progress']*100):
					self.last_percent_update = time.time()
			else:
				self.last_percent_update = time.time()
			self.print_percent = data['display_status']['progress']

		if self.job_Info:
			self.file_name = self.job_Info['print_stats']['filename']
			self.status = self.job_Info['print_stats']['state']
			self.print_time = self.job_Info['print_stats']['total_duration']

		if self.job_Info:
			self.HMI_flag.print_finish = self.getPercent() == 100.0

		return Update

	def getState(self):
		if self.job_Info:
			return self.job_Info['print_stats']['state']
		else:
			return None

	def printingIsPaused(self):
		if self.job_Info:
			return self.job_Info['print_stats']['state'] == "paused" or self.job_Info['print_stats']['state'] == "pausing"
		else:
			return None

	def getPercent(self):
		if self.print_percent is not None:
			return self.print_percent*100
		return 0

	def duration(self):
		if self.job_Info:
			if self.job_Info['virtual_sdcard']['is_active']:
				return self.job_Info['print_stats']['print_duration']
		return 0
	
	def timeSinceUpdate(self):
		if self.last_percent_update is not None:
			return time.time() - self.last_percent_update
		return 0

	def remain(self):
		percent = self.getPercent()
		duration = self.duration() - self.timeSinceUpdate()
		if percent:
			total = duration / (percent / 100)
			return total - (duration + self.timeSinceUpdate())
		return 0

	def openAndPrintFile(self, filenum):
		self.file_name = self.files[filenum]['path']
		self.postREST('/printer/print/start', json={'filename': self.file_name})

	def cancel_job(self): #fixed
		print('Canceling job:')
		self.postREST('/printer/print/cancel', json=None)

	def pause_job(self): #fixed
		print('Pausing job:')
		self.postREST('/printer/print/pause', json=None)

	def resume_job(self): #fixed
		print('Resuming job:')
		self.postREST('/printer/print/resume', json=None)

	def set_print_speed(self, fr):
		self.print_speed = fr
		self.sendGCode('M220 S%d' % fr)

	def set_flow(self, fl):
		self.flow_percentage = fl
		self.sendGCode('M221 S%d' % fl)

	def set_led(self, led_power):
		self.led_percentage = led_power

		for led_name in self.LED:
			self.sendGCode('SET_LED LED=%s WHITE=%f SYNC=0 TRANSMIT=1' % (led_name, led_power/256))

	def set_fan(self, fan):
		self.fan_percentage = fan
		self.sendGCode('M106 S%s' % (int)(fan*255/100))

	def home(self, axis): #fixed using gcode
		GCode = 'G28 '
		if axis == 'X' or axis == 'Y' or axis == 'Z' or axis == 'X Y Z':
			GCode += axis
		else:
			print("home: parameter not recognised" + axis)
			return

		self.sendGCode(GCode)

	def moveRelative(self, axis, distance, speed):
		self.sendGCode('%s \n%s %s%s F%s%s' % ('G91', 'G1', axis, distance, speed,
			'\nG90' if self.absolute_moves else ''))

	def moveAbsolute(self, axis, position, speed):
		self.sendGCode('%s \n%s %s%s F%s%s' % ('G90', 'G1', axis, position, speed,
			'\nG91' if not self.absolute_moves else ''))

	def sendGCode(self, gcode):
		self.postREST('/printer/gcode/script', json={'script': gcode})
		if self.response_callback:
			self.response_callback(gcode, 'command')

	def disable_all_heaters(self):
		self.setExtTemp(0)
		self.setBedTemp(0)

	def zero_fan_speeds(self):
		pass

	def preheat(self, profile):
		if profile == "PLA":
			self.preHeat(self.material_preset[0].bed_temp, self.material_preset[0].hotend_temp)
		elif profile == "ABS":
			self.preHeat(self.material_preset[1].bed_temp, self.material_preset[1].hotend_temp)

	def save_settings(self):
		print('saving settings')
		return True

	def setExtTemp(self, target, toolnum=0):
		self.sendGCode('M104 T%s S%s' % (toolnum, target))

	def setBedTemp(self, target):
		self.sendGCode('M140 S%s' % target)

	def preHeat(self, bedtemp, exttemp, toolnum=0):
		self.setBedTemp(bedtemp)
		self.setExtTemp(exttemp)

	def setZOffset(self, offset):
		self.sendGCode('SET_GCODE_OFFSET Z=%s MOVE=1' % offset)
