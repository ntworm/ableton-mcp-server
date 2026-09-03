# Can a similarity measure carry "teach it with my examples"?

Measured 2026-09-02, before building anything on it.

## Why this was measured first

The owner asked for a tool that learns from examples he marks, rather than one
that draws a groove from a catalogue. That rests entirely on a similarity
measure: given five grooves he likes, the tool has to find more like them.

The neural programme already failed at gate G5 trying to learn this. Building a
panel on an unvalidated hand-built measure would repeat the mistake that
produced the lottery, so the measure was tested first.

## The test

The real product operation, run over the packaged seed: take five grooves from
one collection as the examples, average them into a centroid, retrieve the
twenty nearest of the remaining 3,995, and count how many belong to the same
collection.

259 collections hold twelve or more grooves and were used.

## Result

| Representation | Precision at 20 | Against chance |
| --- | --- | --- |
| 16 steps × 6 pieces, velocity mass, folded to one bar | **3.5%** | 14× |
| The same plus per-cell microtiming and dynamics | **4.4%** | 18× |

Eighteen times chance sounds like signal, and it is. In absolute terms it means
five examples return fewer than one correct result out of twenty. That is not a
tool anyone would use twice.

Microtiming was added because of what the first run showed: swing and jazz
collections scored 20–30% while rock and metal scored zero, which is what
happens when the only thing a representation captures is grid position and the
only genre with a distinctive grid is swing. Adding the offsets raised the
average by a quarter and lifted two metal collections to 30%, so the axis is
real. It is not enough.

## The caveat that matters more than the number

Collection membership is a poor stand-in for "sounds alike". A groove from
`EZX_METAL` and one from `NU_METAL_ESSENTIALS` may be indistinguishable by ear,
and the measure is penalised for finding it. So this result does not prove the
similarity is bad; it proves it does not recover library provenance.

What it does prove is sharper and less comfortable: **there is no ground truth
here for what the owner means by similar.** Without one, no similarity measure
can be validated, which is the same wall the neural programme hit.

## What would break the deadlock

The judgement has to come from the owner, and the cheapest place to collect it
is the product itself: which retrieved grooves get inserted, and which get
skipped. That is a labelled pair every time he uses it.

Which leaves a chicken and egg. A tool worth using needs a measure good enough
to be worth using, and the measure needs the usage to learn from. The way
through is to ship a weak measure with a fast reject loop — show eight
candidates, make skipping one instant, and record it — rather than to keep
tuning a measure against a proxy that was never the target.

## What this does not say

It does not say the seed is wrong; the seed is 4,000 real performances and the
mapping to the owner's kit is now proven. It says that ranking them by
similarity to an example is unsolved, and that the next honest step is to
collect the judgement rather than to guess it again.
