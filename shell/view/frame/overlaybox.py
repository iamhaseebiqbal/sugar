import hippo

from sugar.graphics.iconbutton import IconButton

class OverlayBox(hippo.CanvasBox):
    def __init__(self, shell):
        hippo.CanvasBox.__init__(self, orientation=hippo.ORIENTATION_HORIZONTAL)

        self._shell = shell

        icon = IconButton(icon_name='theme:stock-chat')
        icon.connect('activated', self._overlay_clicked_cb)
        self.append(icon)

    def _overlay_clicked_cb(self, item):
        self._shell.toggle_chat_visibility()
