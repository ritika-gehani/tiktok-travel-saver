# TikTok Travel Saver — Product Requirements

**Status:** Draft  
**Product stage:** Version 1 definition  
**Last updated:** September 2026

## Product summary

TikTok Travel Saver turns scattered travel TikToks into an organized, visual trip workspace.

A traveler creates a trip, pastes TikTok links, and lets the app extract the places, recommendations, warnings, and useful context hidden in each video. The traveler reviews the result, then explores everything by category and location instead of reopening dozens of saved videos.

The product should make trip planning feel calm and inviting. It is not a general-purpose itinerary app with TikTok bolted on; TikTok is the primary input and the reason the product exists.

## Problem

Travelers save many useful TikToks while researching a destination, but TikTok's saved collections do not turn that content into a usable plan.

The traveler still has to:

- remember which video mentioned which place
- replay videos to recover names, addresses, and advice
- reconcile spoken audio, captions, and on-screen text
- separate genuine recommendations from background locations
- see whether saved places are geographically close
- decide what belongs in the trip and what can be ignored
- share the emerging plan with travel companions

This turns the exciting part of planning into repetitive administrative work.

## Product promise

**Paste the TikToks you saved. Get a trustworthy, visual collection of places for your trip.**

Version 1 wins if a traveler can go from a pile of TikTok links to a reviewed, map-based shortlist without manually rewatching every video.

## Target user

### Primary user

A leisure traveler who discovers restaurants, neighborhoods, shops, activities, and practical advice through TikTok. They may be casually collecting ideas or actively planning a trip with fixed dates.

### Planning styles

The product should recognize two common modes without forcing either too early:

1. **Idea collector:** wants an organized shortlist by category and neighborhood, but does not want a day-by-day schedule.
2. **Itinerary planner:** wants to eventually assign places to days and arrange them into a realistic geographic route.

Version 1 primarily serves the idea collector while creating a clean path toward itinerary planning.

## Jobs to be done

- When I find a useful travel TikTok, help me save its actual recommendations without taking notes myself.
- When I return to planning later, show me everything organized by trip rather than by source video.
- When AI extracts uncertain information, let me quickly verify and correct it.
- When I have many saved places, help me understand their categories and geographic clusters.
- When I plan with other people, eventually let us shape one shared plan without losing context.

## Product principles

### TikTok in, trip knowledge out

The interface should emphasize destinations, places, and decisions. The TikTok remains visible as evidence, but it is not the final unit of organization.

### Trust before automation

AI should save work without pretending to be infallible. Every extraction has a clear review state, confidence cues, source evidence, and an easy correction path.

### Progressive structure

Users should be able to collect ideas before choosing dates or building an itinerary. Structure appears when it becomes useful, not as an onboarding tax.

### Map and list work together

Like the strongest pattern in Wanderlog, the collection and map should be two views of the same trip. Selecting a card highlights its pin; selecting a pin reveals the card.

### Calm by default

One primary action per screen, generous spacing, plain language, and staged decisions. The product should feel closer to Apple Notes or Notion than a dense booking dashboard.

### Preserve the source

Every extracted fact should remain connected to its TikTok, creator, transcript, caption, or on-screen text so the user can verify why it exists.

## Version 1 scope

### 1. Trip workspace

Users can:

- create a trip with a name and destination
- optionally add dates
- see all trips as calm, distinct blocks on the home page
- open a trip into one dedicated planning workspace

Creating a trip should ask only what is immediately useful:

- trip name
- destination
- optional dates
- planning mode: "Collect ideas" or "Build an itinerary"

The choice sets the initial view but can be changed later.

### 2. TikTok inbox

Each trip has an inbox where the user can paste one or more TikTok URLs.

For each TikTok, the existing extraction pipeline gathers:

- creator and source URL
- caption
- audio transcript
- on-screen text
- video or carousel cover
- destination summary
- places and place types
- creator notes, foods or items, warnings, and general tips
- confidence and source evidence

Processing states are visible: queued, processing, ready to review, failed.

### 3. Human review

Every processed TikTok enters **Needs review**.

The review screen should:

- show the source TikTok beside or near the extracted result
- group extracted places into compact cards
- make uncertain fields visually distinct without alarming the user
- allow editing, deleting, and adding places or notes
- allow merging duplicate places
- let the user approve the result with one clear action

The system should never require the user to inspect raw JSON.

### 4. Organized place collection

Approved places become the primary trip content.

Users can browse or filter by:

- food and drink
- sights and activities
- shopping
- neighborhoods
- stays
- practical tips
- uncategorized

Each place card includes:

- name and category
- short reason to visit
- neighborhood or area when known
- source TikTok count
- review state
- saved notes and warnings

A place may be supported by multiple TikToks. The interface should combine those sources rather than create unexplained duplicate cards.

### 5. Map view

The trip workspace includes a map synchronized with the place collection.

Version 1 map behavior:

- display reviewed places with coordinates
- use category-aware pins or filters
- highlight the matching card and pin together
- reveal places missing valid coordinates
- support filtering without removing data from the trip

Version 1 does not need route optimization. Its job is to help the user see clusters, distances, and neighborhoods.

### 6. Lightweight planning

Users can:

- mark places as must do, interested, or skip
- drag places into custom collections such as "Tokyo food" or "Rainy day"
- optionally assign a place to a trip day when dates exist

This supports both planning styles without requiring a complete itinerary.

## Core user journey

1. User creates "Japan 2027" and chooses "Collect ideas."
2. User pastes several TikTok links into the trip inbox.
3. The app processes each source and marks completed items "Needs review."
4. User opens a review, fixes one uncertain restaurant name, removes an irrelevant background landmark, and approves it.
5. Approved places appear in the trip collection and on the map.
6. User filters to food, notices several places cluster in Shibuya, and marks two as must do.
7. Later, the user can add dates and assign shortlisted places to days without rebuilding the trip.

## Information architecture

```text
Home
└── Trip
    ├── Overview
    ├── TikTok inbox
    ├── Places
    ├── Map
    └── Itinerary (lightweight in V1)
```

Country and city remain useful attributes and filters, but trips become the top-level container. This better matches how users think: "my Japan trip," not "my database of Japan content."

## Key screens

### Home

- welcoming headline and one "Create trip" action
- trip blocks with destination, dates, collaborator avatars later, place count, and review count
- recent activity or recently saved items
- search across trips

### Trip overview

- trip identity and progress
- fast "Paste TikTok" input
- pending-review queue
- collection and map preview
- simple category and status filters

### Review

- source context
- extracted places and notes
- confidence and evidence only where useful
- edit, merge, remove, approve

### Places and map

- responsive split view on larger screens
- easy toggle between list and map on mobile
- shared filters and selection state

## UX requirements

- Mobile-first for saving and reviewing links.
- A new user should understand the home page's primary action without instructions.
- Trip creation should take under one minute.
- Pasting a link should provide immediate acknowledgment even when extraction is slow.
- Empty states should explain the next action, not describe missing data.
- Advanced fields should stay hidden until requested.
- Destructive actions should be reversible where practical.
- Accessibility should not depend on color alone for review status or categories.

## Out of scope for Version 1

- automatic hour-by-hour itinerary generation
- route optimization
- booking and reservation imports
- budgeting and expense splitting
- real-time multi-user editing
- comments, reactions, and voting
- public trip guides or discovery feed
- native mobile applications
- browser extension or automatic TikTok account import
- fully autonomous approval of AI extractions

These are valuable, but none are required to prove the core promise.

## Version 1 success measures

Initial product metrics:

- percentage of submitted TikToks that produce at least one usable place
- median time from paste to reviewed result
- percentage of extracted places approved without editing
- percentage of users who review at least one TikTok after creating a trip
- number of reviewed places per active trip
- percentage of active trips viewed on the map

Qualitative success:

- users no longer need to reopen most source TikToks while planning
- users can explain what they saved and where it is at a glance
- review feels faster than manual note-taking
- the interface reduces planning stress rather than adding another system to maintain

## Delivery phases

### Foundation

- migrate the top-level model from countries to trips
- retain offline mode and seed data
- define trip, source, place, and source-evidence records

### Version 1A: Collect and review

- create trip flow
- trip-level TikTok inbox
- extraction states
- review and correction flow
- reviewed place collection

### Version 1B: Visualize and shortlist

- geocoding and map
- category and status filters
- must do, interested, and skip states
- duplicate-place merging
- optional day assignment

### Later

- richer day-by-day itinerary
- geographic route suggestions and optimization
- collaboration, comments, reactions, and voting
- personalized planning recommendations

## Open product decisions

- Should users paste several TikToks at once in Version 1, or add them individually?
- Should trip destination allow multiple cities or countries from the start?
- Is a place approved independently, or only when its entire source TikTok is approved?
- Which map and geocoding provider best fits cost, coverage, and licensing needs?
- Should "Collect ideas" and "Build an itinerary" be explicit modes or simply suggested starting layouts?

## Competitive reference

Wanderlog validates several useful interaction patterns:

- itinerary and map in one workspace
- places organized into flexible lists before they are assigned to days
- drag-and-drop day planning
- shared trip editing
- geographic route support

TikTok Travel Saver should borrow the clarity of those patterns, not Wanderlog's breadth. Its differentiation is the TikTok-to-trustworthy-place pipeline, source-backed AI extraction, and a review experience designed around imperfect social-video data.
