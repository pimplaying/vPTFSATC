# Point this at wherever you run server/app.py.
# "localhost" only works if the server runs on the SAME machine as this
# client. For real multi-controller use, run the server somewhere all
# your controllers can reach (a shared PC on your LAN, or a small VPS),
# and put its address here.
SERVER_URL = "http://localhost:5050"

# Public - fine to embed in the distributed app (unlike the client secret,
# which stays server-side only). Get this from your Discord Application's
# General Information page.
DISCORD_CLIENT_ID = "1553461441066041374"
