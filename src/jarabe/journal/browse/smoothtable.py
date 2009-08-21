# Copyright (C) 2009, Aleksey Lim
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import gtk
import gobject
import math
import bisect
import logging

class SmoothTable(gtk.Container):
    __gsignals__ = {
            'set-scroll-adjustments': (gobject.SIGNAL_RUN_FIRST, None,
                                      [gtk.Adjustment, gtk.Adjustment]),
            'fill-in': (gobject.SIGNAL_RUN_FIRST, None,
                       [gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT]),
            }

    def __init__(self, rows, columns, new_widget):
        assert(rows and columns)

        self._rows = []
        self._adj = None
        self._adj_value_changed_id = None
        self._bin_window = None
        self._bin_rows = 0
        self._cell_height = 0
        self._reordered = None
        self._last_allocation = None

        gtk.Container.__init__(self)

        cell_no = 0
        for y in range(rows + 2):
            row = []
            for x in range(columns):
                cell = new_widget()
                cell.set_parent(self)
                cell.size_allocate(gtk.gdk.Rectangle(-1, -1))
                cell_no += 1
                row.append(cell)
            self._rows.append(row)

    def get_columns(self):
        return len(self._rows[0])

    columns = property(get_columns)

    def get_rows(self):
        return len(self._rows) - 2

    rows = property(get_rows)

    def get_head(self):
        if self._adj is None:
            return 0
        return int(self._adj.value) - int(self._adj.value) % self._cell_height

    head = property(get_head)

    def set_count(self, count):
        self._bin_rows = max(0, math.ceil(float(count) / len(self._rows[0])))

        if self._adj is not None:
            self._setup_adjustment(force=True)
            if self.flags() & gtk.REALIZED:
                self._bin_window.resize(self.allocation.width,
                        int(self._adj.upper))

    def do_realize(self):
        self.set_flags(gtk.REALIZED)

        self.window = gtk.gdk.Window(
                self.get_parent_window(),
                window_type=gtk.gdk.WINDOW_CHILD,
                x=self.allocation.x,
                y=self.allocation.y,
                width=self.allocation.width,
                height=self.allocation.height,
                wclass=gtk.gdk.INPUT_OUTPUT,
                colormap=self.get_colormap(),
                event_mask=gtk.gdk.VISIBILITY_NOTIFY_MASK)
        self.window.set_user_data(self)

        self._bin_window = gtk.gdk.Window(
                self.window,
                window_type=gtk.gdk.WINDOW_CHILD,
                x=0,
                y=int(-self._adj.value),
                width=self.allocation.width,
                height=int(self._adj.upper),
                colormap=self.get_colormap(),
                wclass=gtk.gdk.INPUT_OUTPUT,
                event_mask=(self.get_events() | gtk.gdk.EXPOSURE_MASK |
                            gtk.gdk.SCROLL_MASK))
        self._bin_window.set_user_data(self)

        self.set_style(self.style.attach(self.window))
        self.style.set_background(self.window, gtk.STATE_NORMAL)
        self.style.set_background(self._bin_window, gtk.STATE_NORMAL)

        for row in self._rows:
            for cell in row:
                cell.set_parent_window(self._bin_window)

        self.queue_resize()

    def do_size_allocate(self, allocation):
        if self._reordered is not None:
            if allocation == self._reordered:
                self._reordered = None
                return
            self._reordered = None

        self.allocation = allocation
        self._cell_height = allocation.height / self.rows

        self._setup_adjustment(force=True)

        if self.flags() & gtk.REALIZED:
            self.window.move_resize(*allocation)
            self._bin_window.resize(allocation.width, int(self._adj.upper))

    def do_unrealize(self):
        self._bin_window.set_user_data(None)
        self._bin_window.destroy()
        self._bin_window = None
        gtk.Container.do_unrealize(self)

    def do_style_set(self, style):
        gtk.Widget.do_style_set(self, style)
        if self.flags() & gtk.REALIZED:
            self.style.set_background(self._bin_window, gtk.STATE_NORMAL)

    def do_expose_event(self, event):
        if event.window != self._bin_window:
            return False
        gtk.Container.do_expose_event(self, event)
        return False

    def do_map(self):
        self.set_flags(gtk.MAPPED)

        for row in self._rows:
            for cell in row:
                cell.map()

        self._bin_window.show()
        self.window.show()

    def do_size_request(self, req):
        req.width = 0
        req.height = 0

        for row in self._rows:
            for cell in row:
                cell.size_request()

    def do_forall(self, include_internals, callback, data):
        for row in self._rows:
            for cell in row:
                callback(cell, data)

    def do_add(self, widget):
        pass

    def do_remove(self, widget):
        pass

    def do_set_scroll_adjustments(self, hadjustment, vadjustment):
        if vadjustment is None or vadjustment == self._adj:
            return

        if self._adj is not None:
            self._adj.disconnect(self._adj_value_changed_id)

        self._adj = vadjustment
        self._setup_adjustment()

        self._adj_value_changed_id = vadjustment.connect('value-changed',
                self.__adjustment_value_changed_cb)

    def _setup_adjustment(self, force=False):
        self._adj.lower = 0
        self._adj.upper = self._bin_rows * self._cell_height
        self._adj.page_size = self.allocation.height
        self._adj.changed()

        max_value = max(0, self._adj.upper - self._adj.page_size)
        if self._adj.value > max_value:
            self._adj.value = max_value
            self._adj.value_changed()
        elif force:
            self._adj.value_changed()

    def _allocate_row(self, row, cell_y):
        cell_x = 0
        cell_no = cell_y / self._cell_height * self.columns

        for cell in row:
            self.emit('fill-in', cell, cell_no)

            callocation = gtk.gdk.Rectangle(cell_x, cell_y)
            callocation.width = self.allocation.width / self.columns
            callocation.height = self._cell_height
            cell.size_allocate(callocation)

            cell_x += callocation.width
            cell_no += 1

    def __adjustment_value_changed_cb(self, sender=None):
        if not self.flags() & gtk.REALIZED:
            return

        spare_rows = []
        visible_rows = []
        page_end = self._adj.value + self._adj.page_size

        if self._last_allocation != self.allocation:
            self._last_allocation = self.allocation
            spare_rows = [] + self._rows
        else:
            class IndexedRow:
                def __init__(self, row):
                    self.row = row

                def __lt__(self, other):
                    return self.row[0].allocation.y < other.row[0].allocation.y

            for row in self._rows:
                if row[0].allocation.y < 0 or \
                        row[0].allocation.y > page_end or \
                        (row[0].allocation.y + self._cell_height) < \
                        self._adj.value:
                    spare_rows.append(row)
                else:
                    bisect.insort_right(visible_rows, IndexedRow(row))

        if not visible_rows or \
                len(visible_rows) < self.rows + (self.head != visible_rows[0]):
            self._reordered = self.allocation

            def insert_spare_row(cell_y, end_y):
                while cell_y < end_y:
                    if not spare_rows:
                        logging.error('spare_rows should not be empty')
                        return
                    row = spare_rows.pop()
                    self._allocate_row(row, cell_y)
                    cell_y = cell_y + self._cell_height

            cell_y = self.head
            for i in visible_rows:
                insert_spare_row(cell_y, i.row[0].allocation.y)
                cell_y = i.row[0].allocation.y + i.row[0].allocation.height
            insert_spare_row(cell_y, page_end)

        self._bin_window.move(0, int(-self._adj.value))
        self.window.process_updates(True)

SmoothTable.set_set_scroll_adjustments_signal('set-scroll-adjustments')

if __name__ == '__main__':
    window = gtk.Window()

    scrolled = gtk.ScrolledWindow()
    scrolled.set_policy(gtk.POLICY_ALWAYS, gtk.POLICY_ALWAYS)
    window.add(scrolled)

    def cb(sender, button, offset):
        button.props.label = str(offset)
    table = SmoothTable(3, 3, gtk.Button)
    table.connect('fill-in', cb)
    table.set_count(100)
    scrolled.add(table)

    window.show_all()
    gtk.main()
