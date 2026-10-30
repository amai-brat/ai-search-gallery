import base64
import subprocess
import sys

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/fs", tags=["fs"])

# Windows: the standard Explorer folder dialog (IFileOpenDialog with
# FOS_PICKFOLDERS). It does not depend on Tcl/Tk, which is often broken in
# python.org installs. The dialog is owned by the current foreground window so
# it opens on top of the browser instead of behind it.
_WINDOWS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class FolderPicker
{
    [ComImport, Guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")]
    private class FileOpenDialogCom { }

    [ComImport, Guid("42F85136-DB7E-439C-85F1-E4075D135FC8"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IFileOpenDialog
    {
        [PreserveSig] int Show(IntPtr parent);
        void SetFileTypes(uint count, IntPtr types);
        void SetFileTypeIndex(uint index);
        void GetFileTypeIndex(out uint index);
        void Advise(IntPtr events, out uint cookie);
        void Unadvise(uint cookie);
        void SetOptions(uint options);
        void GetOptions(out uint options);
        void SetDefaultFolder(IShellItem item);
        void SetFolder(IShellItem item);
        void GetFolder(out IShellItem item);
        void GetCurrentSelection(out IShellItem item);
        void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string name);
        void GetFileName([MarshalAs(UnmanagedType.LPWStr)] out string name);
        void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string title);
        void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string text);
        void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string text);
        void GetResult(out IShellItem item);
    }

    [ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IShellItem
    {
        void BindToHandler(IntPtr bc, ref Guid bhid, ref Guid riid, out IntPtr ppv);
        void GetParent(out IShellItem item);
        void GetDisplayName(uint sigdn, [MarshalAs(UnmanagedType.LPWStr)] out string name);
        void GetAttributes(uint mask, out uint attrs);
        void Compare(IShellItem other, uint hint, out int order);
    }

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    public static string Pick(string title)
    {
        var dialog = (IFileOpenDialog)new FileOpenDialogCom();
        uint options;
        dialog.GetOptions(out options);
        // FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST
        dialog.SetOptions(options | 0x20 | 0x40 | 0x800);
        dialog.SetTitle(title);
        int hr = dialog.Show(GetForegroundWindow());
        if (hr == unchecked((int)0x800704C7)) return "";   // cancelled by the user
        if (hr != 0) Marshal.ThrowExceptionForHR(hr);
        IShellItem item;
        dialog.GetResult(out item);
        string path;
        item.GetDisplayName(0x80058000, out path);          // SIGDN_FILESYSPATH
        return path;
    }
}
'@
[FolderPicker]::Pick('Выберите папку с изображениями')
"""

# Linux/macOS: fall back to Tk where it is available.
_TK_SCRIPT = """
import tkinter
from tkinter import filedialog

root = tkinter.Tk()
root.withdraw()
root.attributes("-topmost", True)
path = filedialog.askdirectory(title="Выберите папку с изображениями", mustexist=True)
root.destroy()
print(path or "")
"""


class PickDirectoryResponse(BaseModel):
    path: str | None


def _command() -> list[str]:
    if sys.platform == "win32":
        encoded = base64.b64encode(_WINDOWS_SCRIPT.encode("utf-16-le")).decode()
        return [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-STA",  # COM dialogs need a single-threaded apartment
            "-ExecutionPolicy",
            "Bypass",
            "-EncodedCommand",
            encoded,
        ]
    return [sys.executable, "-X", "utf8", "-c", _TK_SCRIPT]


@router.post("/pick-directory", response_model=PickDirectoryResponse)
def pick_directory() -> PickDirectoryResponse:
    """Open the native folder dialog on the machine that runs the API.

    Works because the app is local: the browser and the server share a desktop.
    """
    try:
        result = subprocess.run(
            _command(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=408, detail="Диалог выбора папки закрыт по таймауту"
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=501,
            detail="Не удалось открыть диалог выбора папки. Введите путь вручную.",
        ) from exc

    if result.returncode != 0:
        raise HTTPException(
            status_code=501,
            detail="Не удалось открыть диалог выбора папки. Введите путь вручную.",
        )
    return PickDirectoryResponse(path=result.stdout.strip() or None)
