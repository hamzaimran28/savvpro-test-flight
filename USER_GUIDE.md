# FlightHub — User guide

For **hands-on evaluation**: start backend (port **8000**) and frontend (**3000**), then walk through the steps below. Interactive API docs: http://127.0.0.1:8000/docs

---

## Using the web UI

### Search flights

1. Optionally fill **Origin**, **Destination**, and/or **Departure date**.
2. Click **Search**.  
   The results table lists flights **with at least one seat still available.** (Sold-out flights are hidden here; see **Refresh list** for the full schedule.)

### Book a flight

1. Find a row in **Available flights** and note the **flight ID**.
2. Click **Book** (or type the ID in **New booking**).
3. Enter passenger **name** and **passport** (letters and numbers only).
4. Pick an **available** seat on the seat map (**green**; your choice highlights **blue**).
5. **Confirm booking** — note the reference in the confirmation dialog.

### View bookings

1. Choose **lookup method**: booking **reference**, or passenger **full name**.
2. **Search bookings** — the table lists matches and **CONFIRMED** / **CANCELLED** status.

### Cancel a booking

1. Enter the **booking reference** in **Cancel booking**.
2. Submit — the seat becomes available again. If the booking was already cancelled or the reference is wrong, the app explains what happened instead of failing silently.

**Tip:** If the UI cannot reach the API, confirm uvicorn is running and the backend URL in the header matches your API (`http://127.0.0.1:8000`).

---

## Sample API calls (`curl`)

```bash
# adjust if your API host/port differs
BASE=http://127.0.0.1:8000
```

**List entire schedule** (includes sold-out):

```bash
curl -sS "$BASE/flights"
```

**Search — bookable flights only** (optional filters):

```bash
curl -sS -G "$BASE/flights/search" --data-urlencode "origin=NYC" --data-urlencode "destination=PAR"
```

**Create a booking:**

```bash
curl -sS -X POST "$BASE/bookings" -H "Content-Type: application/json" -d "{\"flight_id\":1,\"passenger_full_name\":\"Ada Lovelace\",\"passport_number\":\"P1234567\",\"seat_number\":\"1A\"}"
```

Replace `flight_id`, `seat_number`, and payload with values that match your seeded data.

**Lookup** (use **either** reference **or** name, not both):

```bash
curl -sS -G "$BASE/bookings" --data-urlencode "booking_reference=YOUR_REF"
```

**Cancel:**

```bash
curl -sS -X DELETE "$BASE/bookings/YOUR_REF"
```

Equivalent: `POST "$BASE/bookings/YOUR_REF/cancel"`.
