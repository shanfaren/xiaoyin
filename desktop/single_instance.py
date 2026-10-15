"""One classroom companion per Windows login, across folders and ports.

Kernel handles expire automatically after a crash; no stale PID/lock files.
An auto-reset event asks the existing UI to show itself on its own UI thread.
"""
import ctypes
from ctypes import wintypes as wt

INSTANCE_NAME = r'Local\ForestDoctor.Classroom.Desktop.v1'


class SingleInstance:
    def __init__(self, name=INSTANCE_NAME):
        self.name = name
        self.mutex = self.event = None
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
        self.kernel.CreateMutexW.restype = wt.HANDLE
        self.kernel.CreateEventW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.BOOL, wt.LPCWSTR]
        self.kernel.CreateEventW.restype = wt.HANDLE
        self.kernel.SetEvent.argtypes = [wt.HANDLE]
        self.kernel.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
        self.kernel.WaitForSingleObject.restype = wt.DWORD
        self.kernel.CloseHandle.argtypes = [wt.HANDLE]

    def acquire(self):
        # Open the event first so a second click during startup is retained.
        self.event = self.kernel.CreateEventW(None, False, False, self.name + '.Activate')
        if not self.event:
            raise ctypes.WinError(ctypes.get_last_error())
        ctypes.set_last_error(0)
        self.mutex = self.kernel.CreateMutexW(None, False, self.name)
        error = ctypes.get_last_error()
        if not self.mutex:
            self.close()
            raise ctypes.WinError(error)
        return error != 183  # ERROR_ALREADY_EXISTS

    def activate_existing(self):
        if self.event:
            self.kernel.SetEvent(self.event)

    def activation_requested(self):
        return bool(self.event and self.kernel.WaitForSingleObject(self.event, 0) == 0)

    def close(self):
        for field in ('event', 'mutex'):
            handle = getattr(self, field)
            if handle:
                self.kernel.CloseHandle(handle)
                setattr(self, field, None)
