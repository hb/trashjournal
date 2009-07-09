#!/usr/bin/env python
import pygtk
pygtk.require('2.0')
import gtk
import gio
import gobject
import gconf

import datetime
import subprocess
import pickle
import os.path

class TrashJournal():
    """"A journal for the trash."""

    # constants
    DAYS_MODEL_COLUMNS = (str, int)
    DAYS_MODEL_COLUMN_DISPLAY_STRING = 0
    DAYS_MODEL_COLUMN_DAYS = 1
    
    FILES_MODEL_COLUMNS = (object, str, str, str)
    FILES_MODEL_COLUMN_GFILE = 0
    FILES_MODEL_COLUMN_FILENAME = 1
    FILES_MODEL_COLUMN_DELETION_TIMESTAMP = 2
    FILES_MODEL_COLUMN_FORMER_PATH = 3
    
    def __init__(self):
        self._config_file = os.path.expanduser('~') + '/.trashjournal'
        
        # window
        self.main_window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.main_window.connect("delete_event", self._save_state)
        self.main_window.connect("destroy", gtk.main_quit)
        self.main_window.set_size_request(800,300)
        
        # vbox
        main_vbox = gtk.VBox(False, 2)
        self.main_window.add(main_vbox)

        # horizonal pane
        pane = gtk.HPaned()
        self._pane_tree_views = pane
        main_vbox.pack_start(pane)
        
        # days list
        scrolledwin = gtk.ScrolledWindow()
        scrolledwin.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        pane.add1(scrolledwin)
        model = gtk.ListStore(*TrashJournal.DAYS_MODEL_COLUMNS)
        treeview = gtk.TreeView(model)
        renderer = gtk.CellRendererText()
        # column "Time"
        column = gtk.TreeViewColumn("Time", renderer, text=TrashJournal.DAYS_MODEL_COLUMN_DISPLAY_STRING)
        treeview.append_column(column)
        # done with columns
        treeview.set_headers_visible(True)
        scrolledwin.add(treeview)
        selection_days = treeview.get_selection()
        selection_days.set_mode(gtk.SELECTION_SINGLE)
        selection_days.connect("changed", self._days_view_selection_changed_cb)
        treeview.connect("button-press-event", self._days_view_button_pressed_cb);
        self._days_view = treeview
        self._days_model = model

        # tree for files
        scrolledwin = gtk.ScrolledWindow()
        scrolledwin.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        pane.add2(scrolledwin)
        model = gtk.TreeStore(*TrashJournal.FILES_MODEL_COLUMNS)
        treeview = gtk.TreeView(model)
        treeview.connect("button-press-event", self._files_view_button_pressed_cb);
        treeview.connect("row-activated", self._files_view_row_activated_cb);
        treeview.connect("row-expanded", self._files_view_row_expanded_cb)
        # column "Filename"
        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Filename", renderer, text=TrashJournal.FILES_MODEL_COLUMN_FILENAME)
        column.set_clickable(True)
        column.set_expand(True)
        column.set_resizable(True)
        column.set_sort_column_id(TrashJournal.FILES_MODEL_COLUMN_FILENAME)
        treeview.append_column(column)
        # column "Deletion Timestamp"
        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Deletion Timestamp", renderer, text=TrashJournal.FILES_MODEL_COLUMN_DELETION_TIMESTAMP)
        column.set_clickable(True)
        column.set_expand(True)
        column.set_resizable(True)
        column.set_sort_column_id(TrashJournal.FILES_MODEL_COLUMN_DELETION_TIMESTAMP)
        treeview.append_column(column)
        # column "Former Path"
        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn("Former Path", renderer, text=TrashJournal.FILES_MODEL_COLUMN_FORMER_PATH)
        column.set_clickable(True)
        column.set_expand(True)
        column.set_resizable(True)
        column.set_sort_column_id(TrashJournal.FILES_MODEL_COLUMN_FORMER_PATH)
        treeview.append_column(column)
        # done with columns
        treeview.set_headers_visible(True)
        scrolledwin.add(treeview)
        selection = treeview.get_selection()
        selection.set_mode(gtk.SELECTION_MULTIPLE)
        self._files_view = treeview
        self._files_model = model

        # register changed handler for trash
        fp = gio.File("trash://")
        self._trash_monitor = fp.monitor_directory()
        self._trash_monitor.connect("changed", self._trash_changed)

        # update trash
        self._update_trash_content()
        self._select_standard_days_row()

        self._restore_state()
        
        main_vbox.show_all()
        self.main_window.show()

    def _get_current_window_state(self):
        (pos_x, pos_y) = self.main_window.get_position()
        (width, height) = self.main_window.get_size()
        config = { 'pos_x' : pos_x, 'pos_y' : pos_y,
                   'width': width, 'height': height}
        return config
        
    def _restore_state(self):
        config = self._get_current_window_state()
        try:
            fp = open(self._config_file, "r")
        except IOError:
            return
        saved_config = pickle.load(fp)
        fp.close()
        for key in saved_config:
            config[key] = saved_config[key]
        self.main_window.move(config['pos_x'], config['pos_y'])
        self.main_window.resize(config['width'], config['height'])
        if 'pane_tree_views_position' in config:
            self._pane_tree_views.set_position(config['pane_tree_views_position'])
    
    def _save_state(self, widget, event):
        config = self._get_current_window_state()
        config['pane_tree_views_position'] = self._pane_tree_views.get_position()
        try:
            fp = open(self._config_file, "w")
            pickle.dump(config, fp)
        except IOError:
            print 'IOError: Could not save state.'
        return False


    def _get_confirm_trash(self):
        client = gconf.client_get_default()
        return client.get_bool('/apps/nautilus/preferences/confirm_trash')
        
    def _select_standard_days_row(self):
        iter = self._days_model.get_iter_first()
        if iter:
            selection = self._days_view.get_selection()
            selection.select_iter(iter)
        

    def _get_child_gfile_from_fileinfo(self, file, fileinfo):
        child = file.get_child(fileinfo.get_attribute_as_string("standard::name").decode('string_escape'))
        if not child.query_exists():
            child = file.get_child(fileinfo.get_attribute_as_string("standard::display-name"))
            print 'needed display name: ' + fileinfo.get_attribute_as_string("standard::display-name")
        if not child.query_exists():
            print 'still not existing'
            return None
        return child
        
    def _update_trash_content(self):
        self._days_model.clear()
        self._files_model.clear()
        fp = gio.File("trash://")
        enumerator = fp.enumerate_children("standard::name,standard::display-name,standard::type,trash::orig-path,trash::deletion-date")
        # hash "days ago (int)" -> "gfile"
        # special key values:
        #  -1 : future
        #  -2 : unknown (deletion date not set) 
        self._days_hash = {}
        today = datetime.date.today()
        for fileinfo in enumerator:
            child = self._get_child_gfile_from_fileinfo(fp, fileinfo)
            if not child:
                continue
            deletion_date_string = fileinfo.get_attribute_string("trash::deletion-date")
            if deletion_date_string:
                deldate = self._get_datetime_from_deletion_date_string(deletion_date_string)
                dt = today - deldate.date()
                # sort faulty timestamps into a "future" value of -1 
                if dt.days < 0:
                    days = -1
                else:
                    days = dt.days                
            else:
                # unknown timestamps (deletion-date attribute not set)
                days = -2
            if not days in self._days_hash:
                self._days_hash[days] = []
            self._days_hash[days].append(child)
        
        # transform hash into model
        keys = self._days_hash.keys()
        keys.sort()
        if not keys:
            keys = []
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
            
            self._days_model.append([period_string, days])


    def _get_datetime_from_deletion_date_string(self, string):
        return datetime.datetime.strptime(string, "%Y-%m-%dT%H:%M:%S")

    def _add_file_to_files_model(self, file, fileinfo, parent_iter=None):
        deletion_date = fileinfo.get_attribute_as_string("trash::deletion-date")
        if deletion_date:
            ts = self._get_datetime_from_deletion_date_string(deletion_date)
        else:
            ts = "<unknown>"
        orig_path = fileinfo.get_attribute_as_string("trash::orig-path")
        if not orig_path:
            orig_path = "<unknown>"
        iter = self._files_model.append(parent_iter, (file,
                                                      fileinfo.get_attribute_as_string("standard::display-name").decode('string_escape'),
                                                      ts,
                                                      orig_path.decode('string_escape')))
        
        # add a dummy child if this is a directory
        if fileinfo.get_file_type() == gio.FILE_TYPE_DIRECTORY:
            self._files_model.append(iter, (None, "Loading ...", "", ""))


    def _add_directory_to_files_model(self, directory, parent_iter):
        enumerator = directory.enumerate_children("standard::name,standard::display-name,standard::type,trash::orig-path,trash::deletion-date")
        for fileinfo in enumerator:
            child = self._get_child_gfile_from_fileinfo(directory, fileinfo)
            self._add_file_to_files_model(child, fileinfo, parent_iter)


    def _days_view_selection_changed_cb(self, selection):
       """Days selection changed; build up file list to display"""
       (model, pathlist) = selection.get_selected_rows()
       for path in pathlist:
            iter = model.get_iter(path)
            days = model.get_value(iter, TrashJournal.DAYS_MODEL_COLUMN_DAYS)
            self._files_model.clear()
            if days in self._days_hash:
                trash_fp = gio.File("trash://")
                for file in self._days_hash[days]:
                    fileinfo = file.query_info("standard::display-name,standard::name,standard::type,trash::orig-path,trash::deletion-date")
                    self._add_file_to_files_model(file, fileinfo)
 
        
    def _trash_changed(self,filemonitor, file, other_file, event_type):
        if event_type == gio.FILE_MONITOR_EVENT_CREATED or event_type == gio.FILE_MONITOR_EVENT_DELETED:
            self._update_trash_content()
            self._select_standard_days_row()
    
    
    def _fix_selection_after_button_press(self, view, event):
        # Figure out which item they right clicked on
        path = view.get_path_at_pos(int(event.x),int(event.y))
        selection = view.get_selection()
        # Get the selected path(s)
        (model, paths) = selection.get_selected_rows()
        # If the right click was not on a currently selected row, change the selection
        if path[0] not in paths:
            selection.unselect_all()
            selection.select_path(path[0])        


    def _days_view_button_pressed_cb(self, view, event):
        if event.type == gtk.gdk.BUTTON_PRESS and event.button == 3:
            self._fix_selection_after_button_press(view, event)
            self._days_view_popup_menu(event)
            return True


    def _days_view_popup_menu(self,event):
        menu = gtk.Menu()
        item = gtk.MenuItem(label="Delete permanently")
        item.connect("activate", self._days_view_popup_delete)
        menu.append(item)
        menu.show_all()
        menu.popup(None, None, None, event.button, event.get_time())


    def _confirm_delete(self, files):
        # check if confirmation is required
        if not self._get_confirm_trash():
            return True
        
        dialog = gtk.MessageDialog(self.main_window, 
                                   gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_QUESTION, 
                                   gtk.BUTTONS_NONE, self._get_deletion_confirmation_msg(files))
        dialog.add_buttons(gtk.STOCK_CANCEL, 0, gtk.STOCK_DELETE, 1)
        ret = dialog.run()
        dialog.destroy()
        return ret == 1
       
    def _get_deletion_confirmation_msg(self, files):
        if len(files) == 1:
            fileinfo = files[0].query_info("standard::display-name")
            msg = ['Are you sure that you want to delete "',
                   fileinfo.get_attribute_as_string("standard::display-name").decode('string_escape'),
                   '" permanently from the trash?']
        else:
            msg = ["Are you sure that you want to delete the ",
                   str(len(files)),
                   " selected objects permanently from the trash?"]
        msg.append("\n\nDirectories will be deleted including containing files and subdirectories.\n\nThis action cannot be undone.")
        return "".join(msg)
        
    def _days_view_popup_delete(self, item):
        self._delete_files_from_trash(self._get_file_list_from_days_view_selection(self._days_view.get_selection()))

    def _delete_files_from_trash(self, files):
        if self._confirm_delete(files):
            errors = []
            for file in files:
                displayname = file.query_info("standard::display-name").get_attribute_as_string("standard::display-name").decode('string_escape')
                try:
                    file.delete()
                except:
                    errors.append(displayname)
            if errors:
                msg = ["The following files could not be deleted:\n"]
                for error in errors:
                    msg.append(error)
                dialog = gtk.MessageDialog(self.main_window,
                                           gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_ERROR,
                                           gtk.BUTTONS_CLOSE, "".join(msg))
                dialog.run()
                dialog.destroy()
            
    
    def _files_view_button_pressed_cb(self, view, event):
        if event.type == gtk.gdk.BUTTON_PRESS and event.button == 3:
            self._fix_selection_after_button_press(view, event)
            self._files_view_popup_menu(event)
            return True


    def _files_view_popup_menu(self, event):
        menu = gtk.Menu()
        item = gtk.MenuItem(label="Delete permanently")
        item.connect("activate", self._files_view_popup_delete)
        menu.append(item)
        menu.show_all()
        menu.popup(None, None, None, event.button, event.get_time())
        

    def _files_view_popup_delete(self, item):
        self._delete_files_from_trash(self._get_file_list_from_files_view_selection(self._files_view.get_selection()))

    def _files_view_row_activated_cb(self, view, path, col):
        print 'TODO: files row activated'

    def _files_view_row_expanded_cb(self, view, parent_iter, path):
        # check if first child has a GFile associated with it
        iter = self._files_model.iter_nth_child(parent_iter, 0)
        file = self._files_model.get_value(iter, TrashJournal.FILES_MODEL_COLUMN_GFILE)
        if not file:
            directory = self._files_model.get_value(parent_iter, TrashJournal.FILES_MODEL_COLUMN_GFILE)
            self._add_directory_to_files_model(directory, parent_iter)
            # remove dummy "Loading" entry
            self._files_model.remove(iter)


    def _get_file_list_from_files_view_selection(self, selection):
        (model, pathlist) = selection.get_selected_rows()
        files = []
        for path in pathlist:
            iter = model.get_iter(path)
            files.append(model.get_value(iter, TrashJournal.FILES_MODEL_COLUMN_GFILE))
        return files

    def _get_file_list_from_days_view_selection(self, selection):
        (model, pathlist) = selection.get_selected_rows()
        files = []
        for path in pathlist:
            iter = model.get_iter(path)
            days = model.get_value(iter, TrashJournal.DAYS_MODEL_COLUMN_DAYS)
            files.extend(self._days_hash[days])
        return files


if __name__ == "__main__":
    mainwin = TrashJournal()
    gtk.main()