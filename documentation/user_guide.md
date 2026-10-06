# AdventureTogether - End-User & Host Guide

Welcome to **AdventureTogether**, an event-based scavenger hunt platform created to empower communities to collaboratively improve open geospatial and knowledge datasets (OpenStreetMap, OpenHistoricalMap, Wikimedia Commons, Wikidata, and open source projects).

---

## 1. Participant Experience

### 1.1 Finding & Joining Hunts
1. Open the AdventureTogether web application on your mobile device or desktop.
2. Select an active hunt from the home screen or follow an invite link provided by your event organizer.
3. On the **Team Management** page:
   - Enter your **Display Name** (e.g. `Alex the Mapper`).
   - If your teammates already created a team, enter the 6-character **Team Join Code** (e.g. `EXPLOR42`) and tap **Join Team**.
   - Alternatively, select **Create New Team**, provide a group name (e.g. `Mission Cartographers`), and share the generated join code with your squad.
4. Optionally fill in **Your contributor usernames**: your OpenStreetMap username (also used for OpenHistoricalMap), your Wikimedia username (Commons and Wikidata), and your GitHub username. These are how the harvester recognises your edits and credits them to your team, so without them your edits may not count for your team. They are remembered on your device for the next event, and a leading `@` is ignored.

### 1.2 The Quest Panel, Progress & Leaderboard
The event map's sidebar lists every quest in the hunt. Each quest card shows:
- **Type and points**: an icon and short label (🗺️ OSM, 📸 Commons, 📊 Wikidata, 🧾 Statement, 📍 Check-in, 📝 Notes, 🕰️ OHM, 💻 Code, 🛣️ Imagery) and the points it is worth. The card also names the app to use, e.g. *StreetComplete / EveryDoor* for OSM tag quests or the *OHM iD editor* for OpenHistoricalMap.
- **Progress**: once you have joined a team, a bar and a count such as `3/5` show how many verified contributions your team has toward the quest's target. Completed quests are marked **✓ Done**. Without a team you see only the target (`Target: 5`).
- **Quest window**: some quests only count during a set time, e.g. `🕒 Mon 18:00–20:00` for the welcome icebreaker, shown in your device's time.
- **Inspired by**: the conference talk behind the quest, e.g. *Inspired by: OpenHistoricalMap: across the geoverse — Minh Nguyễn · Wed 11:00 · Beavis*. Tap the title to open the talk page.
- **Show on map**: pans the map to the quest's target and opens its popup. Point targets are coloured dots and area targets are light outlines in the quest type's colour. Quests without a target count anywhere inside the event perimeter.

Tapping a quest marker on the map opens the same details. The **Leaderboard** below the quests shows the top five teams by score with your team highlighted, and refreshes every 30 seconds together with your team's progress.

On a phone the map sits on top and the quests, leaderboard and tools are below it, so scroll down for the panel. Your own position is the larger blue dot with a white ring. Teammates are smaller teal dots and appear under **Active Teammates** (you are not listed there yourself).

### 1.3 Check-in Quests
📍 Check-in quests are verified from your location, with no editing needed: walk to the target and keep the map open in the foreground. When you are within the quest's radius, a banner such as **"You're at Capitol check-in"** appears over the map and the quest card shows **📍 You're here**. Once you have been there for the quest's minimum time (if it has one), the check-in is verified automatically, the card shows **✓ Checked in**, and your team's progress updates. Check-ins only work while location sharing is on and the app is in the foreground. Hosts can still revoke a check-in.

### 1.4 Foreground GPS & Privacy Controls
AdventureTogether protects your privacy and device battery through strict foreground tracking:
- **Foreground Only**: Coordinates are transmitted exclusively while the web tab is open and visible on your screen. When you switch apps or lock your phone, coordinate transmissions are immediately paused.
- **Privacy Tiers**:
  - **Nobody**: Your location is private and never visible to other participants.
  - **Team Only** *(Default)*: Your live marker and last-seen timestamp are shared exclusively with your teammates.
  - **Whole Quest**: Your marker is visible to all participants in the active hunt.
- **20-Minute Decay**: All locations expire from active views after 20 minutes without indefinite history retention.

### 1.5 Deep Linking into Mobile Mapping Tools
To contribute data to OpenStreetMap without tedious manual searching:
1. Tap any quest target on the interactive map or check your location.
2. Under **Mapping Tool Deep Links** in the sidebar:
   - Tap **🚀 Open in StreetComplete** (`streetcomplete://`) to resolve nearby quest surveys.
   - Tap **📍 Open in EveryDoor** (`everydoor://`) for comprehensive node and tag editing.
   - Or tap **🌐 Open OSM Web iD Editor** for desktop web editing.
3. When saving your edits in StreetComplete, EveryDoor, or iD, ensure the event's designated hashtag is included in the changeset comment (e.g. `#SFMapHunt2026`).

---

## 2. Event Host Experience

### 2.1 Creating Hunts & Drawing Bounding Perimeters
1. In the Django Admin or Host Portal, create a new event.
2. Provide:
   - **Title & Description**: Detailed instructions and rules for the hunt.
   - **Start & End Time**: The active time window for the event.
   - **Hashtag**: The unique tag to identify contributions across platforms (e.g. `SFMapHunt2026`).
   - **Bounding Perimeter**: GeoJSON polygon defining the geographic boundaries of the event.
   - **Schedule URL** (optional): the conference's pretalx/frab schedule JSON export, e.g. `https://talks.osgeo.org/foss4g-na-2026/schedule/export/schedule.json`. It powers the Quest Builder's **Inspired by** session picker.

### 2.2 Quest Builder & Criteria Configuration
1. Open `/events/<id>/host/builder` to access the interactive **Quest Builder**. On a phone the map is above the form.
2. Enter a title and instructions, then pick a **Quest Type**. A short description of what participants must do, and which app they will use, appears under the picker. The rule inputs change with the type:

   | Type | Rule inputs |
   |---|---|
   | 🗺️ OpenStreetMap tags | Required tags as `key = value` rows (`*` or a blank value means any value), contributions needed, *Require the event hashtag* (on by default), and a match radius in metres (default 300) once a target point is pinned |
   | 📸 Wikimedia Commons photo | Optional Commons category, contributions needed |
   | 📊 Wikidata edit | Contributions needed |
   | 🧾 Wikidata statement | Item id (e.g. `Q111393295`) and the properties to add (e.g. `P84, P571`), contributions needed |
   | 📍 Location check-in | Check-in radius in metres (default 50) and minimum minutes on site (default 0). Needs a pinned target point. |
   | 📝 OpenStreetMap Note | Contributions needed |
   | 🕰️ OpenHistoricalMap feature | Required tags (default `start_date = *`), contributions needed |
   | 💻 Open source contribution | Pull requests and/or issues, optional allowed GitHub owners (e.g. `OSGeo, qgis`), contributions needed |
   | 🛣️ Street-level imagery | Contributions needed. **Coming soon**: not verified yet, so these quests are saved as inactive and hidden from participants. |

   "Contributions needed" is the quest's `target_count`: e.g. 5 for "add opening hours to 5 cafes".
3. Set the point value.
4. Optionally set a **Quest window** (From / Until) to limit when the quest counts, e.g. Monday 18:00–20:00 for an icebreaker check-in. The times are in your browser's time zone, so set them from a device on conference time.
5. Optionally pick the talk behind the quest under **Inspired by**:
   - If the event has a schedule URL, type part of a title or speaker name to filter the programme, then tap a session. The chosen session is shown with its speakers, time and room. Tap **Change** to pick another.
   - If the event has no schedule URL, the builder says *"Set a schedule URL on the event to pick sessions"*. If the schedule cannot be fetched, it shows an error. Either way, or for things not in the programme (socials, workshops), use **Not in the schedule? Enter it by hand** to type a title and an optional link.
6. Choose the target: click the map inside the blue perimeter to pin a point (drag the pin to adjust), or tick **Use whole event area** for quests that count anywhere in the perimeter.
7. Tap **Add Quest Challenge**.

The **Existing Quests** list under the form shows each quest's type, points, and whether it is inactive. **Delete** removes a quest after a confirmation. Team progress on that quest is lost.

### 2.3 Verification Dashboard & Review Workflow
1. Navigate to `/events/<id>/host/verify` to open the **Host Verification Portal**.
2. The background harvester automatically polls OSM, OpenHistoricalMap, OSM Notes, Wikimedia Commons, Wikidata and GitHub for contributions tagged with the event hashtag. Check-ins are recorded from location pings. Use **Source Platform** to filter by platform; each platform has its own badge.
3. For each submission:
   - Inspect the **Diff Preview** to review added/modified tags and coordinates.
   - Click the external link (e.g. `#1456789 ↗`) to view the live changeset, file, revision or pull request. The date under it is when the contribution was made on that platform.
   - **Elements** shows how many distinct contributions the submission counts for (e.g. `3 elements` for three cafes tagged in one changeset).
   - Check the **Verify** button. A team's progress on a quest is the sum of its verified elements, and the quest's points are awarded once, when progress reaches the quest's target. Un-verifying takes them back if progress drops below the target.
   - Click **progress** under a team name to see that team's count, target and awarded points for every quest.

<!-- BEGIN: check-in quests -->
## Check-in quests

Some quests only ask you to be somewhere: the Welcome Icebreaker, the west steps of the Capitol, a memorial in Capitol Park. These are **check-in quests**, and you complete them just by going there with AdventureTogether open on your phone. Start location sharing on the event map and keep the tab in the foreground as you arrive. Once your location lands inside the quest's circle (usually 50 m, or anywhere inside the outlined area), the quest shows as **in range**. Most check-ins count straight away. Some ask you to stay a few minutes, so keep the app open until the quest shows **verified**; if you leave for more than about ten minutes before then, the timer starts again. Check-ins only count while the quest is open, so a quest set for Monday evening will not count on Monday morning. Your team gets the points automatically; if you haven't joined a team yet, your visit is still recorded, and your team is credited the next time you check in at that spot (while the quest is still open) after joining. Choosing **Nobody** for your location visibility hides your marker from other participants but still lets you check in. Hosts can see check-ins and may remove one that looks wrong.
<!-- END: check-in quests -->
