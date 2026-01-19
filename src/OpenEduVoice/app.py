import os
os.environ.setdefault("TYPEGUARD_DISABLE", "1")

import tkinter as tk
from OpenEduVoice.gui.main_window import App

def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
