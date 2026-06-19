# Move 1 — Watch Two Real People Think (by hand)

Track A: The Concept Check. I act as the tool myself, before any app exists.

---

## Person 1

- **Name / consent:** _[fill name]_ — consent to record: _[yes/no]_
- **Concept tested:** Why does a backend exist? Why doesn't everything run in the browser?
- **Raw record:** _[link to audio / transcript / screenshots]_

### How it went
- **Opening:** Asked "what is a backend and why does it exist? Why not everything in the browser?"
  → She said **"no idea."**
- **Nudge (scenario):** "Forget the word backend. 10,000 people use Instagram and see each other's
  photos — where do those photos live? Could they sit only on your phone?"
  → She derived the *existence*: **"it doesn't load on my phone for sure, it is going somewhere."**
  Then slid into a label: **"something managing interface and backend design make it work."**
- **Follow-up (the exposing question):** "Drop the words backend/interface. Why must that 'somewhere'
  be a separate machine — why can't your phone and your friend's phone just talk directly?"
  → She did **not** derive the necessity. Reframed to surface:
  **"it's just a social media thing — if I posted on an app, all my friends have to be on that app."**

### Verdict
- **The sentence where understanding became a label:**
  > "something managing interface and backend design make it work"
- **Follow-up used:** why a separate machine, why not phone-to-phone?
- **Could she derive after? NO.** She has the intuition that data "goes somewhere" but cannot
  derive *why a separate, central, always-on machine is required*. Gap stayed open.

---

## Person 2 — Hansh Goel

- **Name / consent:** Hansh Goel — consent: yes (recorded, told purpose at end)
- **Concept tested:** why a backend exists → interface → API → authentication / authorization
- **Raw record:** voice memo "Andheri East.m4a" (transcribed via Groq Whisper)
- **Note:** Whisper garbled the Hindi/Hinglish opening into broken Devanagari; the English
  bulk (his derivation) transcribed cleanly and is the usable record.

### How it went
- Derived **why a backend exists** from first principles, unprompted: a server takes the load
  of multiple users, data is secured, and — his core point — a company keeps its **business
  logic private** ("otherwise anyone could copy any company easily"). Used ChatGPT as his own
  example: the big model cannot run on a user's device.
- Derived **interface** correctly: "a medium, not a specific software — a medium between the
  user and the service provider." Frontend = the interface sitting on his device.
- Derived **API** correctly: application programming interface, a medium / point of interaction
  between two objects (his phone and the servers).
- Derived **authentication vs authorization** correctly and kept them distinct: auth = proving
  you are who you claim; authz = rules/limits (free vs paid plan, rate limits). Explained the
  **API key as the authentication layer** for an external provider.
- Spontaneously named the **deterministic vs probabilistic split** himself when describing how
  he'd build a chatbot (deterministic backend APIs vs the probabilistic LLM "brain").

### Verdict
- **The sentence where understanding became a label:** none found.
- **Could he derive after?** N/A — **no gap to expose.** He derived every concept cleanly under
  repeated "how does it actually work / what's underneath" pressure. Interviewer stated on record:
  "couldn't find any loopholes... this product will not find a gap in your interface knowledge."
- **Result:** clean PASS. This is a genuine "no gap exists for this person" case.

---

## Cross-read (the Move 1 insight)
- **Did both break at the same place?** No — opposite ends of the spectrum.
  - Person 1: could not derive *why a backend exists* at all; fell back to "it's a social media thing."
  - Person 2: derived backend, interface, API, and auth/authz cleanly from first principles.
- **Pattern worth noting:** the two real people bracket the extremes (no-derivation vs
  full-derivation). Neither hit the hypothesis's sweet spot — *can define but cannot derive,
  then closes the gap once it is named*. That case has not appeared yet, which directly
  pressures the Move 2 bet and is honest signal to report.
- **Implication for Move 5:** likely need a third person who sits in the middle (defines the
  words, stalls on the why) to actually test the before→after gap-close the tool is built around.
