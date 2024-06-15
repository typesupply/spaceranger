import yaml
from pathlib import Path
import shutil
from mojo.extensions import ExtensionBundle

root = Path(__file__).parent

with open(root / "info.yaml") as yamlFile:
    infoData = yaml.safe_load(yamlFile)
with open(root / "build.yaml") as yamlFile:
    buildData = yaml.safe_load(yamlFile)

bundle = ExtensionBundle(
    **infoData,
    license=buildData.get("license", ""),
    requirements=buildData.get("requirements", "") or ""
)

destPath = root / "build" / buildData.get("extensionPath", f"{bundle.name}.roboFontExt")

htmlFolder = buildData.get("htmlFolder")
if htmlFolder is not None:
    htmlFolder = root / htmlFolder

resourcesFolder = buildData.get("resourcesFolder")
if resourcesFolder is not None:
    resourcesFolder = root / resourcesFolder

bundle.save(
    destPath=destPath,
    libFolder=root / buildData["libFolder"],
    htmlFolder=htmlFolder,
    resourcesFolder=resourcesFolder,
)

if bundle.validationErrors():
    print("ERROR!")
    print(f"Could not build {bundle.name}.")
    print(bundle.validationErrors())
else:
    success, infoMessage = bundle.install(showMessages=False)
    if not success:
        print("ERROR!")
        print(f"Could not install {bundle.name}.")
        print(infoMessage)
    else:
        print(f"Built and installed {bundle.name}.")
        print("Restart RoboFont.")
