from pyhafas import HafasClient
from pyhafas.profile import DBProfile

client = HafasClient(DBProfile())
locations = client.locations("Aue Agricolastr.")
for loc in locations:
    print(f"Name: {loc.name}, ID: {loc.id}")
