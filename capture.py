"""Screenshot of the primary monitor, in physical pixels."""
import mss
from PIL import Image


def grab_primary():
    """Returns (PIL.Image RGB, monitor_dict)."""
    with mss.mss() as sct:
        mon = sct.monitors[1]
        shot = sct.grab(mon)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    return img, dict(mon)
