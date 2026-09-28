# Asset credits

The files in this folder are not covered by the MIT license in the repo root.
Each one carries its own license, listed below.

## goblinsword_fixed.png

**[LPC] Goblin**, graphic artist Stephen "Redshrike" Challener, contributor
William.Thompsonj. <https://opengameart.org/content/lpc-goblin>

The original is offered under several licenses (CC-BY 4.0, CC-BY 3.0, GPL 3.0,
GPL 2.0, OGA-BY 3.0). This project uses it under
[CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/).

**Changes made to the original `goblinsword.png`:**

- Each cell was widened from 64×64 to 72×64 (sheet 704×320 to 792×320), adding
  8px of empty space on the right of every cell. Frame count and order are
  unchanged: 49 frames, 11 columns.
- The sword tip on the thrust frames overflowed its cell into the next one.
  The stray pixels (21px sitting in frame 20 that belong to frame 19, and 5px
  sitting in frame 21 that belong to frame 20) were moved back onto the frame
  that owns them and erased from the neighbouring cell.

No pixels of the character art were redrawn. The modified sheet is released
under the same CC-BY 4.0 license.
