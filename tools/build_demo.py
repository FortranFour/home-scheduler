"""Build an original, fictional GLB house. No external models or textures.

Run with Python 3; Pillow is needed only to generate the room-label textures.
All mesh coordinates are baked, retaining identity node transforms for floor3dx.
"""
import io
import json
import math
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "custom_components/home_scheduler/frontend"
OUT.mkdir(parents=True, exist_ok=True)
binary = bytearray()
gltf = {"asset": {"version": "2.0", "generator": "FortranFour Home Scheduler fictional demo 0.4.0"},
        "scene": 0, "scenes": [{"nodes": []}], "nodes": [], "meshes": [], "materials": [],
        "buffers": [], "bufferViews": [], "accessors": [], "textures": [], "images": [],
        "samplers": [{"magFilter": 9729, "minFilter": 9729, "wrapS": 33071, "wrapT": 33071}],
        "extensionsUsed": ["KHR_materials_unlit"]}


def view(raw, target=None):
    binary.extend(b"\0" * ((-len(binary)) % 4))
    result = len(gltf["bufferViews"])
    value = {"buffer": 0, "byteOffset": len(binary), "byteLength": len(raw)}
    if target:
        value["target"] = target
    gltf["bufferViews"].append(value)
    binary.extend(raw)
    return result


def accessor(values, components, kind, component_type=5126):
    raw = struct.pack("<" + ("f" if component_type == 5126 else "H") * len(values), *values)
    value = {"bufferView": view(raw, 34963 if kind == "SCALAR" else 34962), "componentType": component_type,
             "count": len(values) // components, "type": kind}
    if kind == "VEC3":
        value.update(min=[min(values[i::components]) for i in range(components)],
                     max=[max(values[i::components]) for i in range(components)])
    result = len(gltf["accessors"])
    gltf["accessors"].append(value)
    return result


def material(color, alpha=1):
    rgb = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
    result = len(gltf["materials"])
    gltf["materials"].append({"name": color, "pbrMetallicRoughness": {"baseColorFactor": [*rgb, alpha],
                             "metallicFactor": 0, "roughnessFactor": .8}, "doubleSided": True,
                             **({"alphaMode": "BLEND"} if alpha < 1 else {})})
    return result


MAT = {k: material(c) for k, c in {
    "walls": "#e0e5ec", "wallcap": "#9bb0c2", "wood": "#be956d", "bedfloor": "#b7c8d3",
    "studyfloor": "#bdc3b1", "tile": "#b9d4c8", "patio": "#a7a49b", "garage": "#a4adb8",
    "sofa": "#4f6f85", "fabric": "#b58497", "white": "#e7eced", "steel": "#718296",
    "black": "#273947", "glass": "#77bacc", "water": "#3e9ec5", "foliage": "#5b8a66",
    "lamp": "#c7b886", "fan": "#638895", "curtain": "#b38d97", "cover": "#627c96",
    "car": "#527a9e", "orange": "#e6a86c", "accent": "#ac91c3"}.items()}


FACES = [([0, 0, 1], [(-.5,-.5,.5),(.5,-.5,.5),(.5,.5,.5),(-.5,.5,.5)]),
         ([0, 0,-1], [(.5,-.5,-.5),(-.5,-.5,-.5),(-.5,.5,-.5),(.5,.5,-.5)]),
         ([-1,0,0], [(-.5,-.5,-.5),(-.5,-.5,.5),(-.5,.5,.5),(-.5,.5,-.5)]),
         ([1,0,0], [(.5,-.5,.5),(.5,-.5,-.5),(.5,.5,-.5),(.5,.5,.5)]),
         ([0,1,0], [(-.5,.5,.5),(.5,.5,.5),(.5,.5,-.5),(-.5,.5,-.5)]),
         ([0,-1,0], [(-.5,-.5,-.5),(.5,-.5,-.5),(.5,-.5,.5),(-.5,-.5,.5)])]


def cuboids(name, boxes, mat):
    positions, normals, indices = [], [], []
    for center, size, angle in boxes:
        cosine, sine = math.cos(angle), math.sin(angle)
        for normal, points in FACES:
            begin = len(positions) // 3
            for point in points:
                x,y,z = [point[i] * size[i] for i in range(3)]
                positions.extend([center[0]+x*cosine-z*sine, center[1]+y, center[2]+x*sine+z*cosine])
                normals.extend([normal[0]*cosine-normal[2]*sine,normal[1],normal[0]*sine+normal[2]*cosine])
            indices.extend([begin+i for i in (0,1,2,0,2,3)])
    add_mesh(name, positions, normals, indices, mat)


def box(name, center, size, mat, angle=0):
    cuboids(name, [(center,size,angle)], mat)


def add_mesh(name, positions, normals, indices, mat, uv=None):
    # floor3dx centers models whose horizontal coordinates start at zero.
    # Bake this offset into every mesh, preserving identity node transforms.
    positions = [value + (5.08 if i % 3 == 0 else 4.08 if i % 3 == 2 else 0)
                 for i, value in enumerate(positions)]
    attrs = {"POSITION": accessor(positions,3,"VEC3"), "NORMAL": accessor(normals,3,"VEC3")}
    if uv is not None:
        attrs["TEXCOORD_0"] = accessor(uv,2,"VEC2")
    mesh = len(gltf["meshes"])
    gltf["meshes"].append({"name": name, "primitives": [{"attributes": attrs,
                           "indices": accessor(indices,1,"SCALAR",5123), "material": mat}]})
    node = len(gltf["nodes"])
    gltf["nodes"].append({"name": name, "mesh": mesh})
    gltf["scenes"][0]["nodes"].append(node)


def cylinder(name, center, radius, height, mat, segments=24):
    positions, normals, indices = [], [], []
    for i in range(segments):
        a,b = i*math.tau/segments,(i+1)*math.tau/segments
        for normal, triangle in (
            ([0,1,0], [(0,height/2,0),(radius*math.cos(b),height/2,radius*math.sin(b)),(radius*math.cos(a),height/2,radius*math.sin(a))]),
            ([0,-1,0], [(0,-height/2,0),(radius*math.cos(a),-height/2,radius*math.sin(a)),(radius*math.cos(b),-height/2,radius*math.sin(b))]),
            ([math.cos(a),0,math.sin(a)], [(radius*math.cos(a),-height/2,radius*math.sin(a)),(radius*math.cos(a),height/2,radius*math.sin(a)),(radius*math.cos(b),height/2,radius*math.sin(b))]),
            ([math.cos(b),0,math.sin(b)], [(radius*math.cos(a),-height/2,radius*math.sin(a)),(radius*math.cos(b),height/2,radius*math.sin(b)),(radius*math.cos(b),-height/2,radius*math.sin(b))])):
            start = len(positions)//3
            for p in triangle:
                positions.extend([p[j]+center[j] for j in range(3)])
                normals.extend(normal)
            indices.extend([start,start+1,start+2])
    add_mesh(name,positions,normals,indices,mat)


def label(text,x,z):
    image = Image.new("RGBA", (512,112), (0,0,0,0))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf",48)
    except OSError:
        font = ImageFont.load_default(size=48)
    draw.text((256,56),text,font=font,anchor="mm",fill="#314959")
    png = io.BytesIO(); image.save(png,format="PNG")
    idx = len(gltf["images"]);gltf["images"].append({"bufferView":view(png.getvalue()),"mimeType":"image/png"})
    texture=len(gltf["textures"]);gltf["textures"].append({"sampler":0,"source":idx})
    mat=len(gltf["materials"])
    gltf["materials"].append({"pbrMetallicRoughness":{"baseColorTexture":{"index":texture}},
                             "alphaMode":"BLEND","doubleSided":True,"extensions":{"KHR_materials_unlit":{}}})
    w,h=1.8,.4
    add_mesh("Label_"+text.replace(" ","_"),[x-w/2,.025,z+h/2,x+w/2,.025,z+h/2,x+w/2,.025,z-h/2,x-w/2,.025,z-h/2],
             [0,1,0]*4,[0,1,2,0,2,3],mat,[0,1,1,1,1,0,0,0])


# Original four-room, roofless cutaway house with a garage and patio.
for name,c,size,mat in [
    ("LivingFloor",(-2.5,-.09,2),(5,.18,4),"wood"),
    ("KitchenFloor",(2.5,-.09,2),(5,.18,4),"tile"),
    ("BedroomFloor",(-2.5,-.09,-2),(5,.18,4),"bedfloor"),
    ("StudyFloor",(2.5,-.09,-2),(5,.18,4),"studyfloor"),
    ("GarageFloor",(6.6,-.09,2),(3.2,.18,4),"garage"),
    ("PatioFloor",(4,-.11,5.5),(8,.16,3),"patio"),
    ("PorchFloor",(-2.5,-.11,4.6),(5,.16,1.2),"wood"),
    ("BackWall",(0,.65,-4),(10,.13,.16),"walls"),
    ("BackWallLow",(0,.28,-4),(10,.56,.16),"walls"),
    ("LeftWall",(-5,.45,0),(.16,.9,8),"walls"),
    ("MiddleWall",(0,.45,-1),(.14,.9,6),"walls"),
    ("MiddleWallShort",(0,.45,3.6),(.14,.9,.8),"walls"),
    ("CrossWallWest",(-3.3,.45,0),(3.4,.9,.14),"walls"),
    ("CrossWallEast",(3.3,.45,0),(3.4,.9,.14),"walls"),
    ("GarageSide",(8.2,.6,2),(.14,1.2,4),"walls"),
    ("GarageBack",(6.6,.6,0),(3.2,1.2,.14),"walls"),
]:box(name,c,size,MAT[mat])
for text,x,z in [("Living",-2.5,3.45),("Kitchen",2.5,3.45),("Bedroom",-2.5,-.55),("Study",2.5,-.55),("Garage",6.6,3.4),("Patio",4,6.7)]:label(text,x,z)

# Living room furniture, aquarium, and a lamp used by the two scene markers.
box("SofaSeat",(-3.9,.38,1.7),(1.1,.38,2.2),MAT["sofa"])
box("SofaBack",(-4.4,.7,1.7),(.2,.8,2.2),MAT["sofa"])
box("CoffeeTable",(-2.15,.43,1.9),(1.25,.15,.8),MAT["wood"])
box("Rug",(-2.1,.012,2),(2.5,.025,2.4),MAT["fabric"])
box("AquariumStand",(-.75,.4,.65),(.9,.8,.55),MAT["wood"])
box("AquariumWater",(-.75,1,.65),(.83,.55,.48),MAT["water"])
box("AquariumPump",(-.4,.98,.67),(.16,.22,.22),MAT["steel"])
box("AccentLamp",(-1.4,1.06,.3),(.27,.3,.27),MAT["accent"])
box("AccentTable",(-1.4,.63,.3),(.7,.1,.5),MAT["wood"])

# Kitchen cabinets, island, and a wall-mounted extractor fan.
box("KitchenCabinet",(4.5,.48,1.7),(.75,.96,3.1),MAT["white"])
box("KitchenCounter",(4.5,1,1.7),(.85,.12,3.2),MAT["steel"])
box("Island",(2.4,.5,1.7),(1.5,1,.8),MAT["white"])
box("IslandTop",(2.4,1.05,1.7),(1.65,.12,.95),MAT["wood"])
box("ExtractorFrame",(3.9,1.4,.18),(.9,.75,.14),MAT["steel"])
cuboids("ExtractorBlades",[((3.9,1.4,.28),(.58,.07,.05),0),((3.9,1.4,.28),(.07,.58,.05),0)],MAT["fan"])

# Bedroom and study furniture.
box("BedFrame",(-3,.18,-2.15),(2.1,.36,2.75),MAT["wood"])
box("BedMattress",(-3,.48,-2.15),(2,.35,2.65),MAT["white"])
box("BedCover",(-3,.69,-1.6),(2,.08,1.55),MAT["fabric"])
box("PillowA",(-3.5,.71,-3.03),(.72,.16,.4),MAT["white"])
box("PillowB",(-2.5,.71,-3.03),(.72,.16,.4),MAT["white"])
box("BedsideTable",(-1.4,.4,-2.9),(.7,.8,.7),MAT["wood"])
box("StudyDesk",(3.6,.77,-2.7),(2.1,.13,1.05),MAT["wood"])
box("StudyMonitor",(3.6,1.22,-3.05),(.8,.5,.07),MAT["black"])
box("StudyChair",(3.6,.5,-1.7),(.65,.5,.65),MAT["sofa"])
box("Bookshelf",(.45,.6,-2.1),(.45,1.2,2.2),MAT["wood"])

# Named fabric meshes for animated roller blind and Roman curtains.
box("StudyWindow",(2.5,1.25,-4),(2.2,1.5,.07),MAT["glass"])
box("StudyBlind",(2.5,1.25,-3.9),(2.1,1.48,.055),MAT["cover"])
box("BedroomWindow",(-2.5,1.25,-4),(2.4,1.5,.07),MAT["glass"])
box("BedroomCurtain",(-2.5,1.25,-3.9),(2.3,1.48,.055),MAT["curtain"])
for x in (-3.7,-1.3,1.4,3.6):box("WindowFrame"+str(x),(x,1.25,-4),(.06,1.62,.12),MAT["white"])

# Garage vehicle and roll-up door; patio shutter, fountain and planters.
box("CarBody",(6.6,.55,1.9),(1.65,.65,2.7),MAT["car"])
box("CarCabin",(6.6,1.02,1.65),(1.42,.5,1.5),MAT["black"])
for x in (5.72,7.48):
    for z in (.9,2.75):box("Wheel"+str(x)+str(z),(x,.35,z),(.18,.48,.46),MAT["black"])
box("GarageDoor",(6.6,1.03,4),(2.7,2.05,.12),MAT["cover"])
box("GarageDoorFrame",(6.6,2.08,4),(2.95,.13,.18),MAT["white"])
box("PatioShutter",(1.3,1.12,4.12),(1.7,2.2,.12),MAT["cover"])
box("PatioShutterRail",(1.3,2.26,4.12),(1.85,.12,.2),MAT["white"])
cylinder("FountainBasin",(4.8,.2,5.6),.63,.35,MAT["steel"])
cylinder("FountainWater",(4.8,.39,5.6),.54,.025,MAT["water"])
cylinder("FountainJet",(4.8,.86,5.6),.035,.9,MAT["water"])
for i,x in enumerate((.45,7.4)):
    box("Planter"+str(i),(x,.22,6.05),(.65,.44,.65),MAT["wood"])
    cylinder("Plant"+str(i),(x,.63,6.05),.35,.4,MAT["foliage"])

# Light fixtures and a single mesh of ceiling-fan blades.
lamp_locations={"LivingLamp":(-2.8,2.2,2.3),"KitchenLamp":(2.2,2.2,2.6),
                "BedroomLamp":(-1.4,1.05,-2.9),"StudyLamp":(4.25,1.05,-2.7),"PorchLamp":(-4.65,1.05,4.08)}
for name,point in lamp_locations.items():cylinder(name,point,.19,.12,MAT["lamp"])
cylinder("LivingFanHub",(-1.2,2.22,2.25),.13,.17,MAT["steel"])
cuboids("LivingFanBlades",[((-1.2,2.2,2.25),(1.55,.045,.18),math.pi/7),((-1.2,2.2,2.25),(1.55,.045,.18),math.pi/7+math.pi/2)],MAT["fan"])

binary.extend(b"\0" * ((-len(binary)) % 4))
gltf["buffers"]=[{"byteLength":len(binary)}]
encoded=json.dumps(gltf,separators=(",",":")).encode()
encoded+=b" "*((-len(encoded))%4)
total=12+8+len(encoded)+8+len(binary)
glb=struct.pack("<III",0x46546c67,2,total)+struct.pack("<II",len(encoded),0x4e4f534a)+encoded+struct.pack("<II",len(binary),0x004e4942)+binary
(OUT/"demo-home.glb").write_bytes(glb)

entities=[]
for entity,name in [("light.hs_demo_living","LivingLamp"),("light.hs_demo_kitchen","KitchenLamp"),
                    ("light.hs_demo_bedroom","BedroomLamp"),("light.hs_demo_study","StudyLamp"),
                    ("light.hs_demo_porch","PorchLamp"),("light.hs_demo_accent","AccentLamp")]:
    entities.extend([{"entity":entity,"type3d":"light","object_id":name,
                      "light":{"shadow":"no","lumens":650 if name.endswith("Lamp") else 300,"distance":9,"decay":1,
                               "color":"#ffb830","offset":{"x":0,"y":-.11,"z":0},"follow_entity":"yes"}},
                     {"entity":entity,"type3d":"color","object_id":name,
                      "colorcondition":[{"state":"on","color":"entity_color"},{"state":"off","color":"#637180"}]}])
entities.extend([
    {"entity":"fan.hs_demo_ceiling","type3d":"rotate","object_id":"LivingFanBlades","rotate":{"axis":"y","round_per_second":1,"hinge":"LivingFanHub"}},
    {"entity":"fan.hs_demo_exhaust","type3d":"rotate","object_id":"ExtractorBlades","rotate":{"axis":"z","round_per_second":1.5}},
    {"entity":"switch.hs_demo_fountain","type3d":"hide","object_id":"FountainJet","hide":{"state":"off"}},
    {"entity":"switch.hs_demo_fountain","type3d":"color","object_id":"FountainWater","colorcondition":[{"state":"on","color":"#18c7e0"},{"state":"off","color":"#627788"}]},
    {"entity":"switch.hs_demo_aquarium","type3d":"color","object_id":"AquariumPump","colorcondition":[{"state":"on","color":"#18c7e0"},{"state":"off","color":"#435260"}]},
    {"entity":"cover.hs_demo_blind","type3d":"shade","object_id":"StudyBlind","shade":{"invert":"no"}},
    {"entity":"cover.hs_demo_curtain","type3d":"shade","object_id":"BedroomCurtain","shade":{"invert":"no"}},
    {"entity":"cover.hs_demo_garage","type3d":"cover","object_id":"GarageDoor","cover":{"pane":"GarageDoor","side":"up"}},
    {"entity":"cover.hs_demo_shutter","type3d":"cover","object_id":"PatioShutter","cover":{"pane":"PatioShutter","side":"up"}},
])
config={"type":"custom:floor3dx-card","name":"Fictional demo home","path":"/home_scheduler/","objfile":"demo-home.glb",
        "header":"no","shadow":"no","click":"no","selectionMode":"no","editModeNotifications":"no","pro_skill":"mobile",
        "globalLightPower":.75,"backgroundColor":"#dce6ee",
        "camera_position":{"x":9,"y":13.5,"z":12.5},"camera_target":{"x":0,"y":0,"z":.8},
        "north":{"x":0,"z":-1},"entities":entities,
        "daylight":{"sun_entity":"sun.hs_demo_sun","weather_entity":"weather.hs_demo_weather","time_entity":"input_number.hs_demo_hour",
                    "ambient":{"day":.7,"night":.16},"hemisphere":"yes",
                    "background":{"day":"#dce6ee","dusk":"#a1aabf","night":"#1b293c"}}}
(OUT/"demo-home.json").write_text(json.dumps(config,indent=2)+"\n")
print(json.dumps({"glb_bytes":len(glb),"objects":len(gltf["nodes"]),"mapped_entries":len(entities),"external_assets":0}))
