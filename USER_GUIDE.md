# FlightHub — User guide

How to use the **web UI** and the **HTTP API** with **`curl`**. Default API base: **`http://127.0.0.1:8000`**. Default UI: **`http://127.0.0.1:3000`**.

**Screenshots:** This repo does not ship screenshots; capture from a local run if you need them for internal runbooks.

---

## Web UI workflows

### Search flights

1. Open **Search flights**.
2. Optionally set **Origin**, **Destination**, and/or **Departure date** (interpreted as **UTC** day).
3. Click **Search**.  
   Only flights with **at least one open seat** (same rule as **`GET /flights/search`**) appear in **Available flights**.

### Create a booking

1. Identify a flight in **Available flights** (note **ID** and **Seats left**).
2. Click **Book** to pre-fill **Flight ID** and scroll to **New booking**, or type the ID manually.
3. Enter **Full legal name** and **Passport number** (letters and digits only).
4. Tap a **green** available seat on the **Cabin seating** map; selection shows **blue**.
5. Click **Confirm booking**.  
   A confirmation overlay shows the **booking reference**. The schedule refreshes afterward.

### Look up bookings

1. Choose **By reference** or **By passenger name**.
2. Enter the value and click **Search bookings**. Results appear in the table (status badges: **CONFIRMED** / **CANCELLED**).

### Cancel a booking

1. In **Cancel booking**, enter the **Booking reference**.
2. Click **Cancel booking**.  
   Success frees the seat; **already cancelled** or **unknown reference** are explained in an overlay (not always a fatal “error” state).

---

## API reference (`curl`)

Set a shell variable for brevity:

```bash
export BASE=http://127.0.0.1:8000
```

### `GET /flights` — list full schedule

Includes sold-out flights. `seats_available` in JSON is **derived** from confirmed bookings vs the seat catalogue.

```bash
curl -sS "${BASE}/flights" | jq .
```

---

### `GET /flights/search` — searchable, bookable-only list

Optional query params: **`origin`**, **`destination`**, **`departure_date`** (`YYYY-MM-DD`, UTC day). Omit all params to list all flights that still have inventory.

Case-insensitive **origin** / **destination** match.

```bash
# All flights that have at least one open seat (per seat-map derivation)
curl -sS "${BASE}/flights/search" | jq .

# NYC → PAR
curl -sS -G "${BASE}/flights/search" \
  --data-urlencode "origin=nyc" \
  --data-urlencode "destination=par" | jq .

# Departing on a specific UTC calendar day
curl -sS -G "${BASE}/flights/search" \
  --data-urlencode "departure_date=2026-07-02" | jq .
```

---

### `GET /flights/{flight_id}/seat-map` — cabin grid

Returns rows of tiles with `seat_number` and **`available`** (boolean).

```bash
curl -sS "${BASE}/flights/1/seat-map" | jq .
```

---

### `POST /bookings` — create booking

Body: **`flight_id`**, **`passenger_full_name`**, **`passport_number`** (letters/digits only), **`seat_number`** (canonical cabin code, e.g. `1A`).

Success: **201 Created** with **`booking_reference`**, **`booking_status`**, nested **`flight`**, etc.

```bash
curl -sS -X POST "${BASE}/bookings" \
  -H "Content-Type: application/json" \
  -d '{
    "flight_id": 1,
    "passenger_full_name": "Ada Lovelace",
    "passport_number": "P1234567",
    "seat_number": "1A"
  }' | jq .
```

Common errors: **404** unknown flight; **422** validation / invalid seat layout; **409** no seats, seat conflict, or last-seat race.

---

### `GET /bookings` — lookup (exactly one filter)

Provide **either** `booking_reference` **or** **`passenger_full_name`** — not both. Name match is **case-insensitive**.

```bash
curl -sS -G "${BASE}/bookings" \
  --data-urlencode "booking_reference=YOUR_REF_HERE" | jq .

curl -sS -G "${BASE}/bookings" \
  --data-urlencode "passenger_full_name=Ada Lovelace" | jq .
```

No filter or both filters:**422**.

---

### `DELETE /bookings/{booking_reference}` — cancel

Booking references from the API are typically URL-safe. If yours contains **`/`**, **`?`**, or **`#`**, percent-encode the path segment.

```bash
REF="YOUR_REF_HERE"
curl -sS -X DELETE "${BASE}/bookings/${REF}" | jq .
```

Success: **200** with **`booking_status`** `CANCELLED`.  
**409** if already cancelled; **404** if reference unknown.

---

### `POST /bookings/{booking_reference}/cancel` — cancel (alternative)

Same semantics as **`DELETE`** for clients that cannot send DELETE.

```bash
curl -sS -X POST "${BASE}/bookings/${REF}/cancel" | jq .
```

---

## Troubleshooting

| Symptom | Check |
|---------|--------|
| UI shows CORS/network errors | Backend running on 8000; UI origin matches CORS allowlist |
| Booking says seat unavailable | Refresh schedule and seat map; another operator may hold the seat |
| `SQLite` locks | Busy timeout is set in code; retry; avoid deleting `*.db` while servers run |
