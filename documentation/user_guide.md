# AdventureTogether - End-User & Host Guide

Welcome to **AdventureTogether**, an event-based scavenger hunt platform created to empower communities to collaboratively improve open geospatial and knowledge datasets (OpenStreetMap, OpenHistoricalMap, Wikimedia Commons, Wikidata, and open source projects).

---

## 1. Participant Experience

### 1.1 The Landing Page: Profile, Tools and Events
Open the AdventureTogether web application on your phone or desktop. The landing page (`/`) has three sections. Everything you enter is stored on your device only (there are no accounts yet).

1. **Your profile**: your **Display name**, your contributor usernames and who sees your location by default. The usernames are your OpenStreetMap username (also used for OpenHistoricalMap), your Wikimedia username (Commons and Wikidata) and your GitHub username. They are optional, but they are how the harvester recognises your edits and credits them to your team, so without them your edits may not count. **Share my location on the map with** sets your default sharing tier (*Nobody*, *My team* or *Everyone in the event*, see 1.5). Changes save as you type.
2. **Tools I have**: tick the apps and accounts you have or can use: StreetComplete, EveryDoor, the OpenStreetMap web editor (iD), Wikimedia Commons (Android app or web upload), Wikidata, the OpenHistoricalMap editor, a GitHub account and Panoramax. Each has a short description and a link to get it. The map's quest panel then shows only the quests you can do (see 1.3).
3. **Your events and teams**: every active event that has not ended yet. If you have joined a team for an event, its card shows **Your team** with the team's join code (share it with friends) and a **Change team** link. Otherwise the card has a **Join or create a team** button. **Open map** opens the event map, and **Top teams** shows the event's top three.

A **Back office** link in the header and at the bottom of the page leads to the host tools (section 2).

### 1.2 Joining a Team
1. Tap **Join or create a team** on an event card, or follow an invite link from your organiser (`/events/<id>/join`).
2. Your display name and usernames are filled in from your profile (the page links back to it). You can still change them here; changes are saved to your profile and sent with the join.
3. If your teammates already created a team, enter the 6-character **Team Join Code** (e.g. `EXPLOR42`) and tap **Join Team**.
4. Or select **Create New Team**, give it a name (e.g. `Mission Cartographers`) and share the join code it shows with your squad.

Already in a team and added a username later? Join the same team again with its code to update your usernames there. A leading `@` in a username is ignored.

### 1.3 The Quest Panel, Progress & Leaderboard
The event map's sidebar lists every quest in the hunt. Each quest card shows:
- **Type and points**: an icon and short label (🗺️ OSM, 📸 Commons, 📊 Wikidata, 🧾 Statement, 📍 Check-in, 📝 Notes, 🕰️ OHM, 💻 Code, 🛣️ Imagery) and the points it is worth. The card also names the app to use, e.g. *StreetComplete / EveryDoor* for OSM tag quests or the *OHM iD editor* for OpenHistoricalMap.
- **Progress**: once you have joined a team, a bar and a count such as `3/5` show how many verified contributions your team has toward the quest's target. Completed quests are marked **✓ Done**. Without a team you see only the target (`Target: 5`).
- **Quest window**: some quests only count during a set time, e.g. `🕒 Mon 18:00–20:00` for the welcome icebreaker, shown in your device's time.
- **Inspired by**: the conference talk behind the quest, e.g. *Inspired by: OpenHistoricalMap: across the geoverse — Minh Nguyễn · Wed 11:00 · Beavis*. Tap the title to open the talk page.
- **Show on map**: pans the map to the quest's target and opens its popup. Point targets are coloured dots and area targets are light outlines in the quest type's colour. Quests without a target count anywhere inside the event perimeter.

**Only quests I can do** at the top of the panel hides quests that none of your ticked tools can complete. It is on by default once you have ticked at least one tool on the landing page, and the panel says how many quests it is hiding. Turn it off to see every quest: those you cannot do yet are greyed out with a line such as *Needs: StreetComplete, EveryDoor or OpenStreetMap web editor (iD)*. 📍 Check-in quests need no tool and always show. Without any tools ticked, every quest shows and the panel suggests ticking your tools.

Tapping a quest marker on the map opens the same details. The **Leaderboard** below the quests shows the top five teams by score with your team highlighted, and refreshes every 30 seconds together with your team's progress.

On a phone the map sits on top and the quests, leaderboard and tools are below it, so scroll down for the panel. Your own position is the larger blue dot with a white ring. Teammates are smaller teal dots and appear under **Active Teammates** (you are not listed there yourself).

### 1.4 Check-in Quests
📍 Check-in quests are verified from your location, with no editing needed: walk to the target and keep the map open in the foreground. When you are within the quest's radius, a banner such as **"You're at Capitol check-in"** appears over the map and the quest card shows **📍 You're here**. Once you have been there for the quest's minimum time (if it has one), the check-in is verified automatically, the card shows **✓ Checked in**, and your team's progress updates. Check-ins only work while location sharing is on and the app is in the foreground. Hosts can still revoke a check-in.

### 1.5 Foreground GPS & Privacy Controls
AdventureTogether protects your privacy and device battery through strict foreground tracking:
- **Foreground Only**: Coordinates are transmitted exclusively while the web tab is open and visible on your screen. When you switch apps or lock your phone, coordinate transmissions are immediately paused.
- **Privacy Tiers** (your default comes from your profile; you can change it on the map with **Share Location**):
  - **Nobody**: Your location is private and never visible to other participants.
  - **Team Only** *(Default)*: Your live marker and last-seen timestamp are shared exclusively with your teammates.
  - **Whole Quest**: Your marker is visible to all participants in the active hunt.
- **20-Minute Decay**: All locations expire from active views after 20 minutes without indefinite history retention.

### 1.6 Deep Linking into Mobile Mapping Tools
To contribute data to OpenStreetMap without tedious manual searching:
1. Tap any quest target on the interactive map or check your location.
2. Under **Mapping Tool Deep Links** in the sidebar:
   - Tap **🚀 Open in StreetComplete** (`streetcomplete://`) to resolve nearby quest surveys.
   - Tap **📍 Open in EveryDoor** (`everydoor://`) for comprehensive node and tag editing.
   - Or tap **🌐 Open OSM Web iD Editor** for desktop web editing.
3. When saving your edits in StreetComplete, EveryDoor, or iD, ensure the event's designated hashtag is included in the changeset comment (e.g. `#SFMapHunt2026`).

---

## 2. Event Host Experience

Hosts work in the **back office** at `/backoffice`, linked from the participant header and the landing page. It has a dark header with a **Back office** label and a **Participants** link back to the landing page. There is no sign-in yet: anyone with the link can use it.

### 2.1 Events List
`/backoffice` lists every event, including inactive ones, newest first. Each row shows a status badge (**Live**, **Upcoming**, **Ended** or **Inactive**), the title, hashtag, start and end in your time zone, and how many quests and teams it has. **Manage** opens the event's manage page and **Edit** its form. **+ New event** creates one.

### 2.2 Creating and Editing an Event
The event form (`/backoffice/events/new`, or **Edit event** on the manage page) asks for:
- **Title** and **Description**.
- **Slug** (optional): the event's short name in URLs. Leave it blank to have one made from the title. It is fixed once the event exists, so the edit form shows it read-only.
- **Hashtag**: the tag that identifies contributions on every platform (e.g. `FOSS4GNA2026`). A leading `#` is removed for you.
- **Starts** and **Ends**: date and time in **your browser's time zone** (shown under the fields). They are saved with that time zone's UTC offset, so set them from a device on conference time or convert first.
- **Schedule URL** (optional): the conference's pretalx/frab schedule JSON export, e.g. `https://talks.osgeo.org/foss4g-na-2026/schedule/export/schedule.json`. It powers the Quest Builder's **Inspired by** session picker. It must be an `https` link on `talks.osgeo.org` or `pretalx.com` (or a subdomain); anything else is refused with a message under the field.
- **Active**: inactive events are hidden from participants and are not harvested.
- **Perimeter**: the event area, drawn as a rectangle on the map. Click one corner, then the opposite corner (a dashed preview follows the pointer); the dashed rectangle appears and the **West**, **South**, **East** and **North** boxes fill in. Click two new corners to redraw it, or type the four edges (longitude for west/east, latitude for south/north) and the rectangle follows; the map zooms to it when you leave a box. **Clear** removes it. When editing an event whose perimeter is not a rectangle (e.g. seeded from a file), it is shown in grey and kept as-is unless you draw a new rectangle.

Problems are shown under the field concerned, both the form's own checks (missing title, end before start, incomplete perimeter) and the server's. After saving you land on the event's manage page.

### 2.3 Managing an Event
`/backoffice/events/<id>` shows the event's title, hashtag, status and dates, an **Active** switch (takes effect immediately), **Edit event** and **Participant map ↗**, and four tabs:
- **Overview**: how many harvested submissions are **waiting for verification** (with a link to review them), the quest count, the full **Leaderboard**, **Harvest** and the participant links (map and join page) to share. **🔄 Poll external APIs now** runs the harvesters immediately instead of waiting for the schedule, then shows a table per platform (*harvested, created, updated, matched, errors*) and any warnings, e.g. a rate limit. Only platforms the event's active quests need are polled, and inactive events cannot be polled.
- **Quests**: the Quest Builder (2.4).
- **Verification**: the verification portal (2.5).
- **Teams**: every team with its **join code**, member count and score, and each member's display name with the OSM, Wikimedia and GitHub usernames they gave (or *no usernames given*: their edits cannot be credited until they add one). **Create team** makes a team and shows its join code, e.g. to pre-create a team per table at a workshop and hand out the codes.

The old host addresses `/events/<id>/host/builder` and `/events/<id>/host/verify` still work and redirect to the Quests and Verification tabs.

### 2.4 Quest Builder & Criteria Configuration
1. Open the event's **Quests** tab in the back office (`/backoffice/events/<id>/quests`) to access the interactive **Quest Builder**. On a phone the map is above the form.
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
3. Set the point value. Leave **Active** ticked for the quest to be visible to participants; untick it to save the quest paused.
4. Optionally set a **Quest window** (From / Until) to limit when the quest counts, e.g. Monday 18:00–20:00 for an icebreaker check-in. The times are in your browser's time zone, so set them from a device on conference time.
5. Optionally pick the talk behind the quest under **Inspired by**:
   - If the event has a schedule URL, type part of a title or speaker name to filter the programme, then tap a session. The chosen session is shown with its speakers, time and room. Tap **Change** to pick another.
   - If the event has no schedule URL, the builder says *"Set a schedule URL on the event to pick sessions"*. If the schedule cannot be fetched, it shows an error. Either way, or for things not in the programme (socials, workshops), use **Not in the schedule? Enter it by hand** to type a title and an optional link.
6. Choose the target: click the map inside the blue perimeter to pin a point (drag the pin to adjust), or tick **Use whole event area** for quests that count anywhere in the perimeter.
7. Tap **Add Quest Challenge**.

The **Existing Quests** list under the form shows each quest's type, points, and whether it is inactive. **Delete** removes a quest after a confirmation. Team progress on that quest is lost.

To change a quest, tap **Edit** next to it in the list. The form switches to **Edit quest: <title>**, filled in with the quest's current settings, and the quest is highlighted in the list. A point target shows as a draggable pin, and the map moves to it. Quests seeded with an area target (a polygon or several points) say *"Area target (polygon) set from the seed file, kept as is"*. That area is kept unless you click the map, which replaces it with a single point once you confirm. Changing the quest type resets only the rule inputs. Tap **Save changes** to update the quest, or **Cancel** to go back to an empty form. To pause a quest without losing team progress, untick **Active** and save; participants stop seeing it until you tick it again.

### 2.5 Verification Dashboard & Review Workflow
1. Open the event's **Verification** tab in the back office (`/backoffice/events/<id>/verify`) to open the **Host Verification Portal**.
2. The background harvester automatically polls OSM, OpenHistoricalMap, OSM Notes, Wikimedia Commons, Wikidata, GitHub, Mangrove Reviews and MapRoulette for contributions in the event area and window (most platforms are matched by the event hashtag; Wikidata, MapRoulette and check-ins are matched by the participant's usernames). Check-ins are recorded from location pings. Use **Source Platform** to filter by platform; each platform has its own badge.
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
