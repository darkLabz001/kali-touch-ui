#!/usr/bin/env python3
"""A separate browser with a persistent touch return bar and optional keyboard."""
import fcntl
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from entertainment import SITES


def main():
    site = sys.argv[1]
    if site not in SITES:
        raise SystemExit('Unknown site')
    browser_bin = shutil.which('chromium') or shutil.which('chromium-browser')
    if not browser_bin or not shutil.which('xdotool'):
        raise SystemExit('Chromium and xdotool are required')
    profile = Path.home() / '.config/kali-touch-social'
    profile.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (profile / 'launcher.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    root = tk.Tk(); root.title('Kali Social Controls')
    width, height = root.winfo_screenwidth(), root.winfo_screenheight()
    root.overrideredirect(True); root.attributes('-topmost', True)
    root.geometry(f'{width}x56+0+0'); root.configure(bg='#101b26')
    browser = keyboard = None
    browser_window = None
    kiosk_ids = []
    closing = False

    def xdo(*args):
        return subprocess.run(['xdotool', *map(str, args)], capture_output=True, text=True, timeout=3)

    def finish():
        nonlocal closing
        if closing:
            return
        closing = True
        for proc in (keyboard, browser):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
        for wid in kiosk_ids:
            xdo('windowmap', wid, 'windowraise', wid, 'windowfocus', wid)
        root.destroy()

    def focus_browser():
        if browser_window and not closing:
            xdo('windowfocus', browser_window)

    def toggle_keyboard():
        nonlocal keyboard
        if keyboard and keyboard.poll() is None:
            keyboard.terminate(); keyboard.wait(timeout=3); keyboard = None
            key_button.configure(text='Keyboard')
        else:
            executable = shutil.which('onboard')
            if not executable:
                label.configure(text='Install Onboard to use the touch keyboard')
                return
            keyboard = subprocess.Popen([executable, '--allow-multiple-instances',
                '--size', f'{width}x180', '-x', '0', '-y', str(height - 180)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            key_button.configure(text='Hide keyboard')
        root.after(500, focus_browser)

    options = dict(bg='#1d3345', fg='#d7ffe5', activebackground='#2e6344',
                   activeforeground='white', relief='flat', font=('sans', 14), padx=14)
    tk.Button(root, text='‹ Back to Kali', command=finish, **options).pack(side='left', padx=6, pady=5, fill='y')
    key_button = tk.Button(root, text='Keyboard', command=toggle_keyboard, **options)
    key_button.pack(side='right', padx=6, pady=5, fill='y')
    label = tk.Label(root, text=site.title(), bg='#101b26', fg='#7cffad', font=('sans', 14))
    label.pack(expand=True, fill='both')
    signal.signal(signal.SIGTERM, lambda *_: root.after(0, finish))
    signal.signal(signal.SIGINT, lambda *_: root.after(0, finish))
    try:
        kiosk_ids = xdo('search', '--onlyvisible', '--name', '^Kali Touch UI$').stdout.split()
        for wid in kiosk_ids:
            xdo('windowunmap', wid)
        browser = subprocess.Popen([browser_bin, '--user-data-dir=' + str(profile),
            '--class=KaliTouchSocial', '--no-first-run', '--no-default-browser-check',
            '--disable-session-crashed-bubble', '--touch-events=enabled',
            '--window-position=0,56', f'--window-size={width},{height - 56}',
            '--app=' + SITES[site]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        root.update()
        print('READY', flush=True)
        attempts = 0
        def check():
            nonlocal attempts, browser_window
            if closing:
                return
            if browser.poll() is not None:
                finish(); return
            # Set exact panel dimensions once Chromium has created its window.
            if attempts < 30:
                windows = xdo('search', '--onlyvisible', '--class', 'KaliTouchSocial').stdout.split()
                if windows:
                    wid = browser_window = windows[-1]
                    subprocess.run(['xprop', '-id', wid, '-f', '_MOTIF_WM_HINTS', '32c',
                        '-set', '_MOTIF_WM_HINTS', '0x2,0x0,0x0,0x0,0x0'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
                    xdo('windowsize', wid, width, height - 56, 'windowmove', wid, 0, 56, 'windowraise', wid, 'windowfocus', wid)
                    attempts = 30
                else:
                    attempts += 1
            # A bare X11 session has no window manager to restore input focus
            # after Onboard opens. Leave browser popups and other focused windows alone.
            if browser_window and xdo('getwindowfocus').stdout.strip() in ('0', '1'):
                focus_browser()
            root.after(500, check)
        root.after(500, check)
        root.mainloop()
    finally:
        if not closing:
            finish()
        lock.close()


if __name__ == '__main__':
    main()
