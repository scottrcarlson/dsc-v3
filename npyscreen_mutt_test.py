#!/usr/bin/env python
import npyscreen
import time
import string
from threading import Thread


class KeyboardCommandHandler(npyscreen.ActionControllerSimple):
	def create(self):
		self.add_action(u'^.*', self.handle_keyboard_command, False)

	def handle_keyboard_command(self, command_line, widget_proxy, live):
		# self.parent.value.set_filter(command_line[1:])
		# self.parent.wMain.values = self.parent.value.get()
		if command_line == "/help":
			self.parent.wMain.buffer(["help command results:", "  result1", "  result2"], scroll_end=False)  # scroll_end must default to True
			self.parent.wMain.display()	 # .DISPLAY() to reset terminal
		elif command_line == "/exit":
			# self.parent.editing = False
			exit("pow")
		else:
			self.parent.wMain.buffer([time.strftime('%H:%M:%S ') + "[me	     ] " + command_line], scroll_end=False)  # scroll_end must default to True
			self.parent.wMain.display()  # TODO: why aren't long lines wrapped?


class AnyInputCommandWidget(npyscreen.fmFormMuttActive.TextCommandBoxTraditional):
	BEGINNING_OF_COMMAND_LINE_CHARS = tuple(string.printable)


class ChatForm(npyscreen.FormMuttActiveTraditionalWithMenus):
	ACTION_CONTROLLER = KeyboardCommandHandler  # default: ActionControllerSimple
	# DATA_CONTROLLER = 	#  default: npysNPSFilteredData.NPSFilteredDataList
	COMMAND_WIDGET_CLASS = AnyInputCommandWidget  # default: TextCommandBoxTraditional
	MAIN_WIDGET_CLASS = npyscreen.BufferPager
	
	DEFAULT_LINES = 20
	DEFAULT_COLUMNS = 54
	
	
class TestApp(npyscreen.NPSApp):
	def main(self):
		self.form = ChatForm()
		self.form.wStatus1.value = "Message log: "
		self.form.wStatus2.value = "Enter message to send or '/help': "
		self.form.value.set_values([time.strftime('%H:%M:%S ') + "------ Console startup ------"])
		self.form.wMain.values = self.form.value.get()
		# form.wCommand
		# m = self.form.new_menu("adsf")
		# m.addItem("zxcv")
		self.form.edit()  # allow the user to interact with the form
		

def threaded_function(app):
	for i in range(20):
		time.sleep(4)
		# print dir(arg)
		app.form.wMain.buffer([time.strftime('%H:%M:%S ') + "[steve   ] simulated msg %d of 20" % (i)], scroll_end=False)  # append_to_chat_log("FIZZ")
		app.form.wMain.display()
		

if __name__ == "__main__":
	# see https://github.com/fritz-smh/domogik-interface-chat/blob/master/bin/chat.py for ideas on wrapping this whole UI as a class
	# thread.join()
	# print "thread finished...exiting"

	app = TestApp()
	thread = Thread(target=threaded_function, args=(app, ))
	thread.start()
	app.run()
