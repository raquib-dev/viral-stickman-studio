"""Build a stand-in 'animation pack' from the CC0 rig for tests: Unreal-mannequin bone names, pack-style clip
names, and the whole model turned 180 degrees. Retargeting must undo all three."""
import json
import struct
import sys
from pathlib import Path

RENAME = {"Hips": "pelvis", "Neck": "neck_01", "Head": "head"}
for side, s in (("L", "l"), ("R", "r")):
    RENAME.update({f"UpperArm.{side}": f"upperarm_{s}", f"LowerArm.{side}": f"lowerarm_{s}", f"Palm2.{side}": f"hand_{s}",
                   f"UpperLeg.{side}": f"thigh_{s}", f"LowerLeg.{side}": f"calf_{s}", f"Foot.{side}": f"foot_{s}"})
CLIPS = {"Idle": "Idle_Loop", "Walking": "Walk_Loop", "Running": "Jog_Fwd_Loop"}


def make(src: Path, dst: Path) -> Path:
    b = src.read_bytes()
    jlen = struct.unpack("<I", b[12:16])[0]
    g = json.loads(b[20:20 + jlen])
    joints = set(g["skins"][0]["joints"])
    for i in joints:
        n = g["nodes"][i]
        n["name"] = RENAME.get(n["name"], n["name"])
    for a in g["animations"]:
        a["name"] = CLIPS.get(a["name"], a["name"])
    root = g["scenes"][0]["nodes"][0]
    g["nodes"][root]["rotation"] = [0, 1, 0, 0]          # face the other way
    js = json.dumps(g).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    rest = b[20 + jlen:]
    total = 12 + 8 + len(js) + len(rest)
    dst.write_bytes(b[:8] + struct.pack("<I", total) + struct.pack("<I", len(js)) + b"JSON" + js + rest)
    return dst


if __name__ == "__main__":
    print(make(Path(sys.argv[1]), Path(sys.argv[2])))
