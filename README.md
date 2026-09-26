# ATC Client

A shared ATC workstation: login, a live flight plan board (departures /
arrivals / all), runway & gate & heading assignment, remarks, and local
audio device selection.

## Architecture

```
server/   Flask + SQLite backend. Run ONCE, reachable by all controllers.
client/   PyQt6 desktop app. Everyone runs their own copy, pointed at
          the same server.
```

Every controller's client talks to the same server, so flight plans,
runway/gate assignments, and status changes are visible to everyone
immediately (the client polls every 5 seconds).

## Discord role-based login setup

Controllers log in with Discord; the server checks (using a bot) whether
they hold a specific role in your Discord server before letting them in.

**1. Create a Discord Application**
- Go to https://discord.com/developers/applications -> New Application.
- Under **OAuth2 -> General**: copy the **Client ID** and **Client Secret**.
- Under **OAuth2 -> General -> Redirects**: add exactly
  `http://localhost:5900/callback`

**2. Create and invite a bot**
- Same application -> **Bot** tab -> Add Bot.
- Copy the **Bot Token** (you'll only see it once - regenerate if you lose it).
- Under **Bot** settings, enable **Server Members Intent**.
- Under **OAuth2 -> URL Generator**: check scope `bot`, permission
  `View Channels` (or just enough to read members), copy the generated URL,
  open it, and invite the bot to your Discord server.

**3. Get your server ID and role ID**
- In Discord: User Settings -> Advanced -> enable **Developer Mode**.
- Right-click your server's icon -> **Copy Server ID**.
- Server Settings -> Roles -> right-click your ATC role -> **Copy Role ID**.

**4. Fill in the server's secrets**
```
cd server
copy discord_config.example.py discord_config.py
```
Open `discord_config.py` and fill in all six values from steps 1-3.

**5. Fill in the client's public Client ID**
Open `client/config.py` and set `DISCORD_CLIENT_ID` to the same Client ID
from step 1 (this one is fine to be public/distributed - unlike the
Client Secret and Bot Token, which must stay on the server only).

**6. Try it**
Start the server, then the client, click **Login with Discord** - it opens
your browser, you approve the app, and (if you have the role) you're in.



**1. Start the server** (once, on whichever machine will host it):
```
cd server
pip install -r requirements.txt
python app.py
```
Leave this running. It listens on port 5050 by default.

**2. Run the client:**
```
cd client
pip install -r requirements.txt
python main.py
```
Click **Login with Discord** - it'll open your browser for you to approve,
then bring you into the app if you have the required role.

If the server is NOT on the same machine as the client, edit
`client/config.py` and change `SERVER_URL` to the server's actual
address, e.g. `http://192.168.1.50:5050` (LAN) or your VPS's address.

## ATC radio

The ATC server uses TCP port **5050** for its API and **5051** for the
radio WebSocket relay. Allow both ports through the host firewall. Each
controller selects an island, position, and frequency in the client's
**Radio** tab, then clicks **Take Position**. Island names are editable;
frequencies must use the `123.450` format and should match your group's
agreed PTFS frequency plan. Positions expire from the directory when the
client disconnects or stops sending heartbeats.

The tracker lists active controller frequencies. Pilots select one (or
type a frequency manually), then hold **PTT** or the bound key (default
`V`) to transmit. ATC uses the matching PTT controls. ATC audio devices
are selected in **Audio Settings**; the tracker uses the computer's
default input and output devices. Install the updated requirements in
both projects to enable audio.

The radio relay currently has no transport encryption or independent
radio authentication. Use it only on a trusted network until the server
is deployed behind TLS and authentication.

## Deploying the server for real multi-controller use

`python app.py` is fine for testing but isn't meant to be a permanent
production server. Options, roughly easiest to most robust:
- Run it on a PC that's always on (e.g. your own machine, or a
  dedicated one), reachable by your controllers' network.
- Deploy it to a small VPS or a platform like Render/Railway - point
  `SERVER_URL` in every client at that address, and make sure the server's
  port is open/forwarded.
- For anything beyond a handful of concurrent controllers, put it behind
  a proper WSGI server (gunicorn/waitress) instead of Flask's built-in
  dev server - ask if you want help with that step.

## Packaging the client as an .exe + installer

Same pattern as the tracker app:
```
cd client
pip install pyinstaller
pyinstaller build.spec
```
Produces `client/dist/ATCClient.exe`. From there, an Inno Setup script
(like the tracker's `installer.iss`) can wrap it into a proper installer -
copy the tracker project's `installer.iss` over and adjust the names/paths
if you want this packaged the same way.

## Adding self-update

The tracker project's `gui/updater.py` is a drop-in pattern for this too -
copy it in, set `GITHUB_REPO`/`EXE_NAME` for this project's repo, and wire
`apply_pending_update_and_maybe_restart()` into `main()` the same way.

## Things you'll likely want to extend next

- Real authentication (this uses plain SQLite + hashed passwords - fine
  for a small community, not bank-grade security)
- Roles/permissions (e.g. only certain users can delete flight plans)
- Push updates instead of 5-second polling (WebSockets, like the tracker's
  broadcast server) for instant sync between controllers
- Linking flight plans to the live position tracker so a strip
  auto-updates once its aircraft is airborne
