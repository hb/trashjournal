#!/usr/bin/env python
import pygtk
pygtk.require('2.0')
import gtk
import gio
import pynotify

class TrashJournal():
	""""A log """

def file_changed(filemonitor, file, other_file, event_type):
	if event_type == gio.FILE_MONITOR_EVENT_CREATED:
		notification = pynotify.Notification("Moved to Trash", file.get_basename(), icon=gtk.STOCK_DELETE)
		notification.show()

if __name__ == "__main__":
	pynotify.init("trashing monitor")
	
	fp = gio.File("trash://")
	monitor = fp.monitor_directory()
	monitor.connect("changed", file_changed)

	gtk.main()
