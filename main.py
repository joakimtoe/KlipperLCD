import getopt
import sys
import time
import base64
from threading import Thread
from datetime import timedelta

from printer import PrinterData
from lcd import LCD, _printerData

class KlipperLCD ():
    def __init__(self):
        self.lcd = LCD("/dev/ttyAMA0", callback=self.lcd_callback)
        self.lcd.start()
        self.printer = PrinterData('XXXXXX', URL=("127.0.0.1"), klippy_sock='/home/pi/printer_data/comms/klippy.sock', callback=self.printer_callback)
        self.running = False
        self.wait_probe = False
        self.thumbnail_inprogress = False

        progress_bar = 1
        while self.printer.update_variable() == False:
            progress_bar += 5
            self.lcd.boot_progress(progress_bar)
            time.sleep(1)

        self.printer.init_Webservices()
        gcode_store = self.printer.get_gcode_store()
        self.lcd.write_gcode_store(gcode_store)

        macros = self.printer.get_macros()
        self.lcd.write_macros(macros)

        print(self.printer.MACHINE_SIZE)
        print(self.printer.SHORT_BUILD_VERSION)
        self.lcd.write("information.size.txt=\"%s\"" % self.printer.MACHINE_SIZE)
        self.lcd.write("information.sversion.txt=\"%s\"" % self.printer.SHORT_BUILD_VERSION)
        self.lcd.write("page main")

    def start(self):
        print("KlipperLCD start")
        self.running = True
        #self.lcd.start()
        Thread(target=self.periodic_update).start()

    def periodic_update(self):
        while self.running:
            if self.wait_probe:
                print("Zpos=%f, Zoff=%f" % (self.printer.current_position.z, self.printer.BABY_Z_VAR))
                if self.printer.ishomed():
                        self.wait_probe = False
                        print("IsHomed")
                        self.lcd.probe_mode_start()

            self.printer.update_variable()
            data = _printerData()
            data.hotend_target = self.printer.thermalManager['temp_hotend'][0]['target']
            data.hotend        = self.printer.thermalManager['temp_hotend'][0]['celsius']
            data.bed_target    = self.printer.thermalManager['temp_bed']['target']
            data.bed           = self.printer.thermalManager['temp_bed']['celsius']
            data.state         = self.printer.getState()
            data.percent       = self.printer.getPercent()
            data.duration      = self.printer.duration()
            data.remaining     = self.printer.remain()
            data.feedrate      = self.printer.print_speed
            data.flowrate      = self.printer.flow_percentage
            data.fan           = self.printer.thermalManager['fan_speed'][0]
            data.x_pos         = self.printer.current_position.x
            data.y_pos         = self.printer.current_position.y
            data.z_pos         = self.printer.current_position.z
            data.z_offset      = self.printer.BABY_Z_VAR
            data.file_name     = self.printer.file_name
            data.max_velocity           = self.printer.max_velocity          
            data.max_accel              = self.printer.max_accel             
            data.max_accel_to_decel     = self.printer.max_accel_to_decel    
            data.square_corner_velocity = self.printer.square_corner_velocity

            self.lcd.data_update(data)
                
            time.sleep(2)

    def printer_callback(self, data, data_type):
        msg = self.lcd.format_console_data(data, data_type)
        if msg:
            self.lcd.write_console(msg)

    def show_thumbnail(self):
        if self.printer.file_path and (self.printer.file_name or self.lcd.files[self.lcd.selected_file]):
            file_name = ""
            if self.lcd.files:
                file_name = self.lcd.files[self.lcd.selected_file]
            elif self.printer.file_name:
                file_name = self.printer.file_name
            else:
                print("ERROR: gcode file not known")
            
            file = self.printer.file_path + "/" + file_name

            # Reading file
            print(file)
            f = open(file, "r")
            if not f:
                f.close()
                print("File could not be opened: %s" % file)
                return
            buf = f.readlines()
            if not f:
                f.close()
                print("File could not be read")
                return

            f.close()
            thumbnail_found = False
            b64 = ""

            for line in buf:
                if 'thumbnail begin' in line:
                    thumbnail_found = True
                elif 'thumbnail end' in line:
                    thumbnail_found = False
                    break
                elif thumbnail_found:
                    b64 += line.strip(' \t\n\r;')
        
            if len(b64):
                # Decode Base64
                img = base64.b64decode(b64)        
                
                # Write thumbnail to LCD
                self.lcd.write_thumbnail(img)
            else:
                self.lcd.clear_thumbnail()
                print("Aborting thumbnail, no image found")
        else:
            print("File path or name to gcode-files missing")
        
        self.thumbnail_inprogress = False

    def lcd_callback(self, evt, data=None):
        if evt == self.lcd.evt.HOME:
            self.printer.home(data)
        elif evt == self.lcd.evt.MOVE_X:
            self.printer.moveRelative('X', data, 4000)
        elif evt == self.lcd.evt.MOVE_Y:
            self.printer.moveRelative('Y', data, 4000)
        elif evt == self.lcd.evt.MOVE_Z:
            self.printer.moveRelative('Z', data, 600)
        elif evt == self.lcd.evt.MOVE_E:
            print(data)
            self.printer.moveRelative('E', data[0], data[1])
        elif evt == self.lcd.evt.Z_OFFSET:
            self.printer.setZOffset(data)
        elif evt == self.lcd.evt.NOZZLE:
            self.printer.setExtTemp(data)
        elif evt == self.lcd.evt.BED:
            self.printer.setBedTemp(data)
        elif evt == self.lcd.evt.FILES:
            files = self.printer.GetFiles(True)
            return files
        elif evt == self.lcd.evt.PRINT_START:
            self.printer.openAndPrintFile(data)
            if self.thumbnail_inprogress == False:
                self.thumbnail_inprogress = True
        elif evt == self.lcd.evt.THUMBNAIL:
            if self.thumbnail_inprogress == False:
                self.thumbnail_inprogress = True
                Thread(target=self.show_thumbnail).start()
        elif evt == self.lcd.evt.PRINT_STATUS:
            pass
        elif evt == self.lcd.evt.PRINT_STOP:
            self.printer.cancel_job()
        elif evt == self.lcd.evt.PRINT_PAUSE:
            self.printer.pause_job()
        elif evt == self.lcd.evt.PRINT_RESUME:
            self.printer.resume_job()
        elif evt == self.lcd.evt.PRINT_SPEED:
            self.printer.set_print_speed(data)
        elif evt == self.lcd.evt.FLOW:
            self.printer.set_flow(data)
        elif evt == self.lcd.evt.PROBE:
            if data == None:
                self.printer.probe_calibrate()
                self.wait_probe = True
            else:
                self.printer.probe_adjust(data)
        elif evt == self.lcd.evt.PROBE_COMPLETE:
            self.wait_probe = False
            print("Save settings!")
            self.printer.sendGCode('ACCEPT')
            self.printer.sendGCode('G1 F1000 Z15.0')
            print("Calibrate!")
            self.printer.sendGCode('BED_MESH_CALIBRATE PROFILE=default METHOD=automatic')
        elif evt == self.lcd.evt.PROBE_BACK:
            print("BACK!")
            self.printer.sendGCode('ACCEPT')
            self.printer.sendGCode('G1 F1000 Z15.0')
            self.printer.sendGCode('SAVE_CONFIG')
        elif evt == self.lcd.evt.BED_MESH:
            pass
        elif evt == self.lcd.evt.LIGHT:
            self.printer.set_led(data)
        elif evt == self.lcd.evt.FAN:
            self.printer.set_fan(data)
        elif evt == self.lcd.evt.MOTOR_OFF:
            self.printer.sendGCode('M18')
        elif evt == self.lcd.evt.ACCEL:
            #print("SET_VELOCITY_LIMIT ACCEL=%d" % data)
            self.printer.sendGCode("SET_VELOCITY_LIMIT ACCEL=%d" % data)
        elif evt == self.lcd.evt.ACCEL_TO_DECEL:
            #print("SET_VELOCITY_LIMIT ACCEL_TO_DECEL=%d" % data)
            self.printer.sendGCode("SET_VELOCITY_LIMIT ACCEL_TO_DECEL=%d" % data)
        elif evt == self.lcd.evt.VELOCITY:
            #print("SET_VELOCITY_LIMIT VELOCITY=%d" % data)
            self.printer.sendGCode("SET_VELOCITY_LIMIT VELOCITY=%d" % data)
        elif evt == self.lcd.evt.SQUARE_CORNER_VELOCITY:
            #print(data)
            print("SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY=%.1f" % data)
            self.printer.sendGCode("SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY=%.1f" % data)
        elif evt == self.lcd.evt.CONSOLE:
            self.printer.sendGCode(data)
        else:
            print("lcd_callback event not recognised %d" % evt)

if __name__ == "__main__":
    x = KlipperLCD()
    x.start()