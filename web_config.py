"""
Web app configuration.
IMAGES_DIR points to the folder containing OVA/ISO/vbox VM images.
By default this is the sibling 'virtual_simulations' CLI folder.
"""
import os

# Folder that contains the OVA/ISO/vbox images (the CLI folder)
IMAGES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "virtual_simulations"
)

# Web server settings
HOST = "0.0.0.0"
PORT = 8080
