# Vendor labels from the Superior Drummer 3 databases

Databases read: 186 of 190 found.
Files labelled: 109554; parsed for pitch content: 103096.
Collections given a vendor articulation entry: 168, covering 1000 pitch overrides.

## Genre, an axis the folder taxonomy does not have

| Genre | Files |
|---|---|
| Pop/Rock/Country | 57670 |
| Metal | 21672 |
| Latin | 10014 |
| Jazz | 4206 |
| Funk | 3485 |
| Blues | 2800 |
| Soul | 2278 |
| Electronic | 2036 |
| Fusion | 1832 |
| Hip Hop | 954 |
| Experimental | 782 |
| Disco | 753 |
| Modern R&B | 491 |
| Reggae | 422 |
| Orchestral | 159 |

Files carrying a vendor tempo: 109554 (100.0%).

## Play-style tags

| Tag | Files |
|---|---|
| Standard | 94665 |
| Normal Time | 89854 |
| Straight | 87184 |
| Hard Hits | 85504 |
| Beat | 77298 |
| Swing | 39592 |
| Fill | 33461 |
| Medium Hits | 20929 |
| Half Time | 14664 |
| Percussion | 8239 |
| Double Kick | 6834 |
| Double Time | 5037 |
| Soft Hits | 3564 |
| Shuffle | 3125 |
| Two Beat | 2387 |
| Blastbeat | 1708 |
| Trainbeat | 1303 |
| March | 736 |
| Swirls | 378 |
| Hands | 338 |
| Ending | 268 |
| Special | 249 |
| D Beat | 226 |
| Polyrhythm | 196 |
| Jam Track | 190 |
| Twist | 112 |
| Brushes | 77 |
| EZX Specials | 63 |
| Snare Roll | 61 |
| Cymbal Swell | 60 |

## Disagreements left unapplied

An override is applied only where General MIDI leaves the pitch unresolved.
Where the two disagree on a pitch General MIDI already names, the vendor
vocabulary is usually coarser - one `Ride` piece covering the bell, one
`Crash` covering splash and china - so applying it would lose detail. These
cases are recorded rather than acted on.

| General MIDI | Vendor kit piece | Would become | Collections |
|---|---|---|---|
| `ride_bell` | Ride | `ride` | 111 |
| `snare` | Kick | `kick` | 25 |
| `splash` | Crash | `crash` | 9 |
| `kick` | Snare | `snare` | 8 |
| `tom_high` | Crash | `crash` | 2 |
| `snare` | Cowbell | `cowbell` | 2 |
| `splash` | Kick | `kick` | 1 |
| `china` | Crash | `crash` | 1 |
| `ride` | Hi-Hat Pedal | `hat_pedal` | 1 |
| `tom_high` | Tambourine | `tambourine` | 1 |
| `kick` | Crash | `crash` | 1 |
| `snare` | Crash | `crash` | 1 |
| `snare` | Cajon | `other_percussion` | 1 |
| `kick` | Sidestick | `rim` | 1 |
| `hat_closed` | Cajon | `other_percussion` | 1 |
| `crash` | Small Shakers | `other_percussion` | 1 |
| `tom_high` | Small Shakers | `other_percussion` | 1 |
| `tambourine` | Ride Crash | `ride` | 1 |
| `tom_low` | Bongo | `other_percussion` | 1 |
| `ride_bell` | Cowbell | `cowbell` | 1 |

Per-file labels are written outside the repository, to `C:\Users\Usuario\AppData\Local\AbletonMCPServer\groove-vendor-labels\vendor_labels.jsonl`.
