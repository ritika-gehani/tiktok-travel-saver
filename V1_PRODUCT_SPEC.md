# TikTok Travel Saver — Version 1 Product Specification

**Audience:** Product, design, and engineering  
**Status:** Draft for implementation  
**Product intent:** Turn saved travel TikToks into a calm, trustworthy, visual trip workspace

## 1. Executive direction

Version 1 should prove one complete outcome:

> A traveler can create a trip, paste travel TikToks, review what the app understood, and leave with an organized collection of real places they can explore by category and location.

The existing extraction pipeline is a strong technical foundation. Version 1 is not a new AI research project and it is not a full itinerary planner. The work is to shape the current extraction tool into a coherent product.

The experience should feel focused and obvious:

1. Create a trip.
2. Add TikToks.
3. Review the app's interpretation.
4. Explore the resulting places.

Everything else is secondary.

## 2. Why this product exists

Travel inspiration is easy to collect and hard to recover.

A traveler may save dozens of TikToks containing restaurant names, neighborhoods, activities, warnings, and small pieces of advice. When it is time to plan, those recommendations are trapped inside separate videos. Recovering them requires rewatching content, taking notes, checking maps, removing duplicates, and remembering which creator said what.

TikTok Travel Saver performs that administrative work while preserving the human judgment that makes a trip personal.

It should not feel like a database the traveler must maintain. It should feel like their saved inspiration quietly became useful.

## 3. Current product

### What works today

The repository already provides:

- TikTok video, photo-carousel, and short-link support
- caption retrieval
- spoken-audio transcription
- on-screen text extraction
- AI extraction of destinations, places, notes, warnings, confidence, and source evidence
- local JSON persistence when credentials are absent
- Supabase persistence when configured
- seeded offline data
- home, country, city, TikTok detail, and add-TikTok pages
- save-to-library behavior
- nine HTTP tests covering the offline browse and save flow

### Current navigation

```text
Home (countries)
└── Country
    └── City
        └── TikTok
```

### Current data model

The saved TikTok is the main record. City and country are copied from its extraction result. Places remain nested inside that TikTok's extraction data.

The current model does not contain:

- a real trip entity
- trip membership
- independent place records
- editable review state
- duplicate-place relationships
- coordinates
- itinerary-day assignments

### Current experience

The home page visually presents countries as if they were trips. It has the intended light, calm direction, but the underlying links still open country and city pages.

The rest of the product retains the older dark extraction-tool design. The detail and add pages expose large amounts of extracted data directly. The information is useful, but the hierarchy makes the user interpret the pipeline instead of helping them make a travel decision.

### Current extraction result

The extraction output is close to what Version 1 needs:

- `video_summary`
- `places`
- `non_place_notes`
- `needs_user_review`
- transcript
- on-screen text
- source-evidence flags

The pipeline should remain intact initially. We should change it only when the review experience reveals a repeatable quality problem.

## 4. Product gap

The app currently answers:

> "What did we extract from this TikTok?"

Version 1 must answer:

> "What have I saved for this trip, what do I trust, and where is it?"

This requires product and data changes, not only a visual redesign.

| Area | Current behavior | Version 1 behavior |
|---|---|---|
| Top-level organization | Country | User-created trip |
| Primary saved object | TikTok | Place, supported by one or more TikToks |
| TikTok input | Single extraction page | Trip-level inbox |
| Review | Read-only result | Editable approval flow |
| Categories | Nested `place_type` text | Consistent, filterable product categories |
| Duplicate recommendations | Separate nested entries | One place with multiple sources |
| Geography | Map search query text | Coordinates and map pins |
| Planning | Browse by country and city | Shortlist, collections, optional day assignment |
| Extraction details | Always prominent | Available on demand |
| Visual system | Light home, dark interior pages | One calm, responsive system |

## 5. Version 1 product model

### Trip

The top-level workspace owned by the user.

Minimum fields:

- ID
- name
- destination label
- optional start and end dates
- planning mode
- created and updated timestamps

Planning modes:

- **Collect ideas**
- **Build an itinerary**

The mode changes the recommended starting view, not the available data. The user can switch later.

### Source

A TikTok submitted to a trip.

Minimum fields:

- ID
- trip ID
- canonical TikTok URL
- creator
- cover image
- processing state
- review state
- caption
- transcript
- on-screen text
- raw extraction result
- created and reviewed timestamps

Processing states:

- queued
- processing
- ready to review
- failed

Review states:

- needs review
- reviewed

### Place

A normalized recommendation inside a trip.

Minimum fields:

- ID
- trip ID
- name
- normalized category
- short reason to visit
- neighborhood or area
- address or map query
- latitude and longitude when resolved
- confidence
- user decision
- user notes

User decisions:

- must do
- interested
- skip
- undecided

### Place source

Connects a place to one or more TikToks and preserves:

- source ID
- original extracted name
- creator notes
- warnings
- foods or items
- evidence flags
- confidence

This relationship lets the product merge duplicate recommendations without erasing where the information came from.

## 6. Target information architecture

```text
Home
└── Trip
    ├── Overview
    ├── TikTok inbox
    ├── Places
    ├── Map
    └── Itinerary
```

Version 1 does not need five equally prominent tabs. The first release can combine Overview, inbox, and recent places into one trip page, with clear routes into review, all places, and map.

Country and city remain attributes and filters. They are no longer the application's navigation skeleton.

## 7. Core Version 1 journey

### Step 1: Create a trip

The user selects **Create trip** and provides:

- trip name
- destination
- optional dates
- planning mode

This should take less than one minute. Dates and planning mode can be skipped.

### Step 2: Add TikToks

The trip page gives the user one obvious paste field.

The user can submit a TikTok URL and immediately sees that it was accepted. Extraction continues with a visible state. A slow pipeline must not make the interface appear frozen.

Batch paste is desirable but not required for the first implementation.

### Step 3: Review

When processing completes, the source appears in the review queue.

The review screen prioritizes:

- what the video recommends
- uncertain information
- corrections the user is likely to make
- approval

The user can:

- edit a place
- remove an irrelevant place
- add a missed place
- correct notes or warnings
- merge an obvious duplicate
- approve the source

Approval promotes the accepted information into the trip's place collection.

### Step 4: Explore the trip

The trip's approved places can be:

- browsed as cards
- filtered by category
- marked must do, interested, or skip
- viewed on a map
- traced back to their source TikToks

Optional day assignment may be added after the core collection and map work.

## 8. Functional requirements

### P0: Required to call the release Version 1

#### Trips

- Create, view, rename, and delete a trip.
- Assign every new TikTok source to one trip.
- Display real trip blocks on the home page.
- Preserve existing city and country data as place attributes.

#### TikTok inbox

- Add a TikTok from inside a trip.
- Show processing and failure states.
- Prevent accidental duplicate submission of the same canonical URL within a trip.
- Retry a failed extraction.

#### Review

- Show extracted places, notes, warnings, and unresolved questions.
- Edit and remove extracted content.
- Add a missed place.
- Approve the source.
- Reopen a reviewed source for editing.
- Persist every accepted change.

#### Place collection

- Create normalized place records from approved extraction results.
- Filter places by category and user decision.
- Open a place and see all supporting TikToks.
- Preserve source-specific notes and evidence.

#### Map

- Resolve map-pinnable places to coordinates.
- Display resolved places as pins.
- Keep selected card and pin synchronized.
- Make unresolved places visible as an actionable state rather than silently dropping them.

#### Visual system

- Apply one light visual system across home, trip, inbox, review, places, map, and detail screens.
- Support mobile review and browsing.
- Use labels or icons in addition to color for state.
- Keep one primary action visually dominant on each screen.

### P1: Include if it does not delay the P0 loop

- submit several TikTok URLs together
- custom place collections
- optional assignment of a place to a trip day
- basic duplicate suggestions
- trip-level search
- category counts

## 9. View extraction process

The extraction process should remain accessible without dominating the product.

### Entry point

On a TikTok source or review screen, show a secondary button:

**View extraction process**

Do not place this above the main review action.

### Behavior

- Open a modal or full-screen sheet.
- Keep the underlying review context intact.
- Allow scrolling through the complete pipeline output.
- Close with an explicit close button, the Escape key on desktop, or a swipe/back action where appropriate on mobile.
- Restore focus to the trigger after closing.

### Content order

Present the information in understandable stages:

1. Source TikTok and creator
2. Caption
3. Audio transcript
4. On-screen text
5. AI summary
6. Extracted places and evidence
7. Items needing review

The default view should use readable sections, not raw JSON.

An additional **View raw data** disclosure may expose formatted JSON for debugging. It is tertiary and should never be required to review a TikTok.

### Purpose

The modal provides:

- transparency when the user wants to understand a result
- evidence for correcting an extraction
- useful debugging context during early product development

It is not the primary product experience.

## 10. Category system

The model may retain specific place types, but the interface should group them into a small stable set:

- Food and drink
- Sights and activities
- Shopping
- Neighborhoods
- Stays
- Practical tips
- Other

Examples:

- restaurant, café, bakery, bar → Food and drink
- museum, temple, park, tour → Sights and activities
- market, boutique, mall → Shopping
- district, street, neighborhood → Neighborhoods
- hotel, hostel, resort → Stays

The original extracted type should be preserved even when the product displays a broader category.

## 11. Design direction

### Emotional goal

Planning should feel lighter after using the product.

The design should communicate:

- calm
- momentum
- trust
- a sense of discovery

### Interface principles

- Show the user's travel content before product chrome.
- Prefer progressive disclosure over long pages.
- Use plain language instead of pipeline terminology.
- Make waiting states feel intentional.
- Keep extracted evidence nearby but visually secondary.
- Use motion to explain state changes, not decorate them.
- Avoid dense dashboards, excessive badges, and competing calls to action.
- Design mobile and desktop layouts for their contexts rather than simply shrinking desktop.

### Primary actions by screen

| Screen | Primary action |
|---|---|
| Home | Create trip |
| Trip | Paste TikTok |
| Inbox item | Review |
| Review | Approve |
| Place | Choose must do / interested / skip |
| Map | Select or filter places |

## 12. What Version 1 will not do

- generate a complete hour-by-hour itinerary
- optimize routes
- import reservations
- manage budgets
- provide real-time collaboration
- support comments, reactions, or group voting
- publish public guides
- import a user's entire TikTok account
- automatically trust every extracted result

These features can follow only after the collect-review-explore loop is reliable and pleasant.

## 13. Acceptance criteria

Version 1 is complete when a new user can:

1. Create a trip without providing dates.
2. Paste a supported TikTok URL into that trip.
3. Understand whether processing is active, complete, or failed.
4. Review the extracted places without reading raw JSON.
5. Open **View extraction process**, inspect all source material, and return to the same review state.
6. Correct an extraction and persist the correction.
7. Approve the TikTok.
8. Find the approved places in one trip-level collection.
9. Filter the collection by a stable category.
10. View resolved places on a synchronized map.
11. Trace any place back to its source TikTok.
12. Complete the core flow on a mobile viewport.

## 14. Recommended implementation order

### Milestone 1: Product foundation

- add trip records and trip membership
- migrate or adapt existing saved TikToks
- replace country-as-trip navigation
- establish the shared light visual system

### Milestone 2: Inbox and review

- move TikTok submission into a trip
- persist processing state
- build editable review
- add the extraction-process modal
- implement approval and reopening

### Milestone 3: Place collection

- normalize approved places
- connect places to one or more sources
- add categories, decisions, filters, and source traceability

### Milestone 4: Map and refinement

- geocode approved places
- build synchronized place and map views
- handle unresolved locations
- complete responsive and accessibility passes

## 15. Technical work implied by the product

The existing extraction pipeline remains the ingestion layer. The primary engineering changes are:

- database schema for trips, sources, places, and place-source relationships
- migration path for current TikTok rows
- APIs for trip CRUD, processing state, review edits, approval, and place decisions
- background or asynchronous representation of extraction work
- canonical URL and duplicate handling
- place normalization and geocoding
- shared design tokens and reusable UI components
- responsive layouts and accessible modal behavior

Supabase should be treated as the production backend. The local JSON path should continue to support development and demonstrations with equivalent behavior where practical.

## 16. Product risks

### Extraction trust

If the result is frequently wrong, a polished interface will not create value. Review corrections should be measured and used to improve prompts and normalization.

### Duplicate places

TikToks may name the same place differently. Aggressive automatic merging can be as harmful as no merging. Version 1 should prefer suggestions and user confirmation.

### Geocoding ambiguity

Names without city or country context may resolve incorrectly. The product must show unresolved or uncertain locations instead of silently pinning the wrong place.

### Scope expansion

Itinerary generation and collaboration are compelling but can consume the release. The first proof is that users prefer this workflow to rewatching and manually organizing saved TikToks.

## 17. Success signals

Quantitative:

- submitted TikToks that yield at least one approved place
- median time from submission to approval
- percentage of extracted places edited or removed
- reviewed sources per active trip
- approved places viewed on the map
- users who return to an existing trip

Qualitative:

- users can understand a trip without reopening most videos
- users trust the app because evidence is available when needed
- users describe the experience as simpler than manual note-taking
- the interface makes trip planning feel inviting rather than administrative

## 18. Decisions still required

- Whether batch paste is P0 or P1.
- Whether a trip can contain multiple countries in the initial release.
- Whether approval happens for an entire TikTok or independently per place.
- Which map and geocoding provider to use.
- Whether planning mode is an explicit onboarding choice or inferred from user actions.

These decisions do not block the first engineering milestone: establishing real trips and replacing country-as-trip navigation.
