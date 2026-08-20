"""timedate - the Az'arch timedate package (the LibreWolf default home page).

A small local Flask website that shows the current time (hour/minute/seconds) and a calendar
(day/month/year), served at localhost:49154. It runs in the background as a systemd service
that starts at boot, and LibreWolf lands on it on startup / Home / new tab. The timezone
follows the SYSTEM live (app.py reads /etc/localtime on every request). A PURE-PYTHON app --
nothing to compile.

Modules:
    timedate                install paths, the systemd service, emit_plan() (the build wiring)
    app                     the Flask application (routes + the live time/calendar data)
    page                    the HTML page renderer
    assets                  presentation assets (the analog-clock SVG, stylesheet, client script)
"""
