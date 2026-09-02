#!/usr/bin/env python
# License: GPLv3 Copyright: 2020, Kovid Goyal <kovid at kovidgoyal.net>


from typing import TYPE_CHECKING

from .base import MATCH_WINDOW_OPTION, ArgsType, Boss, PayloadGetType, PayloadType, RCOptions, RemoteCommand, ResponseType, Window

if TYPE_CHECKING:
    from kitty.cli_stub import FocusWindowRCOptions as CLIOptions


class FocusWindow(RemoteCommand):
    protocol_spec = __doc__ = '''
    match/str: The window to focus
    dont_activate_os_window/bool: Boolean indicating whether to leave the OS Window unactivated
    '''

    short_desc = 'Focus the specified window'
    desc = 'Focus the specified window, if no window is specified, focus the window this command is run inside.'
    options_spec = MATCH_WINDOW_OPTION + '''\n\n
--dont-activate-os-window
type=bool-set
Change only which window is focused inside kitty, leaving the OS Window that contains it
unactivated and unraised. Useful for scripts that need to move the focus in a background
kitty without pulling the user away from whatever they are doing, possibly from another desktop.


--no-response
type=bool-set
default=false
Don't wait for a response from kitty. This means that even if no matching window is found,
the command will exit with a success code.
'''

    def message_to_kitty(self, global_opts: RCOptions, opts: 'CLIOptions', args: ArgsType) -> PayloadType:
        return {'match': opts.match, 'dont_activate_os_window': opts.dont_activate_os_window}

    def response_from_kitty(self, boss: Boss, window: Window | None, payload_get: PayloadGetType) -> ResponseType:
        for window in self.windows_for_match_payload(boss, window, payload_get):
            if window:
                boss.set_active_window(window, switch_os_window_if_needed=not payload_get('dont_activate_os_window'))
                break
        return None


focus_window = FocusWindow()
