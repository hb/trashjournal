#!/usr/bin/env python
import pygtk
pygtk.require('2.0')
import gtk
import gio
import gobject
import pynotify

import datetime

class TrashJournal():
    """"A journal for the trash."""
    def __init__(self):
        pynotify.init("trashing monitor")
        
        fp = gio.File("trash://")
        monitor = fp.monitor_directory()
        monitor.connect("changed", self.file_changed)

        # window
        self.main_window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.main_window.connect("destroy", gtk.main_quit)
        self.main_window.set_size_request(500,300)
        
        # vbox
        main_vbox = gtk.VBox(False, 2)
        self.main_window.add(main_vbox)

        # horizonal pane
        pane = gtk.HPaned()
        main_vbox.pack_start(pane)

        # list for days
        scrolledwin = gtk.ScrolledWindow()
        scrolledwin.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        pane.add1(scrolledwin)
        
        model = gtk.ListStore(str, int)
        treeview = gtk.TreeView(model)
        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Time", renderer, text=0)
        treeview.append_column(column)
        treeview.set_headers_visible(True)
        scrolledwin.add(treeview)
        selection_days = treeview.get_selection()
        selection_days.set_mode(gtk.SELECTION_MULTIPLE)
        selection_days.connect("changed", self._days_view_selection_changed_cb)
        self._days_model = model
        
        # list for files
        scrolledwin = gtk.ScrolledWindow()
        scrolledwin.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        pane.add2(scrolledwin)
        
        model = gtk.ListStore(str, str, object)
        treeview = gtk.TreeView(model)
        treeview.connect("button-press-event", self._files_view_button_pressed_cb);

        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Filename", renderer, text=0)
        column.set_clickable(True)
        column.set_expand(True)
        column.set_resizable(True)
        column.set_sort_column_id(0)
        treeview.append_column(column)
        
        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Deletion Timestamp", renderer, text=1)
        column.set_clickable(True)
        column.set_expand(True)
        column.set_resizable(True)
        column.set_sort_column_id(1)
        treeview.append_column(column)
        
        treeview.set_headers_visible(True)
        scrolledwin.add(treeview)
        selection = treeview.get_selection()
        selection.set_mode(gtk.SELECTION_MULTIPLE)
        self._files_view = treeview
        self._files_model = model
        
        # query trash
        self._trash_content = self._sort_trash_content(self._get_trash_content())
        self._update_trash_content()

        # select first row in days view
        selection_days.select_iter(self._days_model.get_iter_first())

        main_vbox.show_all()
        self.main_window.show()
        gtk.main()

    def _files_view_button_pressed_cb(self, view, event):
        if event.type == gtk.gdk.BUTTON_PRESS and event.button == 3:
            # Figure out which item they right clicked on
            path = view.get_path_at_pos(int(event.x),int(event.y))
            selection = view.get_selection()
            # Get the selected path(s)
            (model, paths) = selection.get_selected_rows()
            # If the right click was not on a currently selected row, change the selection
            if path[0] not in paths:
                selection.unselect_all()
                selection.select_path(path[0])
            self._files_view_popup_menu(event)
            return True
        
    def _files_view_popup_menu(self, event):
        menu = gtk.Menu()
        item = gtk.MenuItem(label="Do Something")
        item.connect("activate", self._files_view_popup_do_something)
        menu.append(item)
        menu.show_all()
        menu.popup(None, None, None, event.button, event.get_time())
        
    
    def _files_view_popup_do_something(self, item):
        print 'Do Something cb!'
        selection = self._files_view.get_selection()
        (model, pathlist) = selection.get_selected_rows()
        for path in pathlist:
            iter = model.get_iter(path)
            fileinfo = model.get_value(iter, 2)
            print fileinfo
        
    def _days_view_selection_changed_cb(self, selection):
        """Days selection changed; build up file list to display"""
        (model, pathlist) = selection.get_selected_rows()
        for path in pathlist:
            iter = model.get_iter(path)
            days = model.get_value(iter, 1)
            self._files_model.clear()
            if days in self._trash_content:
                for fileinfo in self._trash_content[days]:
                    deletion_date = fileinfo.get_attribute_as_string("trash::deletion-date")
                    if deletion_date:
                        ts = self._get_datetime_from_deletion_date_string(deletion_date)
                    else:
                        ts = "<unknown>"
                    self._files_model.append((fileinfo.get_attribute_as_string("standard::name").decode('string_escape'), ts, fileinfo))
                
    
    def _update_trash_content(self):
        keys = self._trash_content.keys()
        keys.sort()
        if not keys:
            keys= []
        for days in keys:
            if days == -2:
                period_string = "Unknown"
            elif days == -1:
                period_string == "Future"
            elif days == 0:
                period_string = "Today"
            elif days == 1:
                period_string = "Yesterday"
            else:
                period_string = str(days) + " days ago"
            iter = self._days_model.append([period_string, days])
                
        
        
    def _sort_trash_content(self, trash_content):
        """Return a hash with integers as keys - 0 means today, 1 yesterday, 2 days ago etc."""
        hash = {}
        today = datetime.date.today()
        for fileinfo in trash_content:
            deletion_date_string = fileinfo.get_attribute_string("trash::deletion-date")
            if deletion_date_string:
                deldate = self._get_datetime_from_deletion_date_string(deletion_date_string)
                dt = today - deldate.date()
                # sort faulty timestamps into a "future" value of .1 
                if dt.days < 0:
                    days = -1
                else:
                    days = dt.days
            else:
                days = -2

            if days not in hash:
                hash[days] = []
            hash[days].append(fileinfo)
        return hash
    
    def _get_datetime_from_deletion_date_string(self, string):
        return datetime.datetime.strptime(string, "%Y-%m-%dT%H:%M:%S")
        
    
    def _get_trash_content(self):
        """Returns a list of FileInfos of the trash folder"""
        fp = gio.File("trash://")
        enumerator = fp.enumerate_children("standard::name,trash::orig-path,trash::deletion-date")
        return list(enumerator)
            
    def file_changed(self,filemonitor, file, other_file, event_type):
        if event_type == gio.FILE_MONITOR_EVENT_CREATED:
            notification = pynotify.Notification("Moved to Trash", file.get_basename(), icon=gtk.STOCK_DELETE)
            notification.show()
            

if __name__ == "__main__":
    mainwin = TrashJournal()
