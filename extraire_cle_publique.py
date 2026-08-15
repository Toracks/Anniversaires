from py_vapid import Vapid
from cryptography.hazmat.primitives import serialization
import base64

# Charge la clé privée générée par `vapid --gen` (qui contient aussi la clé publique associée)
vapid = Vapid.from_file("private_key.pem")

# Le navigateur attend la clé publique dans un format bien précis :
# un "point non compressé" de courbe elliptique, encodé en base64 "url-safe"
raw_bytes = vapid.public_key.public_bytes(
    serialization.Encoding.X962,
    serialization.PublicFormat.UncompressedPoint,
)
application_server_key = base64.urlsafe_b64encode(raw_bytes).rstrip(b"=").decode("utf-8")

print("Application Server Key (à utiliser dans le JavaScript, pas secrète) :")
print(application_server_key)