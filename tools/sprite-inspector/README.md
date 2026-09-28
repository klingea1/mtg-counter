# Sprite Inspector

A standalone tool for auditioning sprite sheet animations and producing a frame map.
Not part of the counter app. Nothing in `index.html` or `server.py` depends on it.

## Running it

From the repo root, serve the folder with Python's built-in web server:

```
python -m http.server 8080
```

Then open <http://localhost:8080/tools/sprite-inspector/>. It loads
`assets/goblinsword_fixed.png` by default.

Don't use `server.py` for this. The game server deliberately serves only the app
and `assets/`, so it will 404 the inspector.

Opening the file directly from disk mostly works, but reading pixel data from an
image loaded over `file://` taints the canvas in Chrome and Safari, and the anchor
analysis needs that pixel data. If the tool reports it cannot read the sheet, either
serve the folder or drag the PNG onto the drop zone, which sidesteps the restriction.

## What it does

**Loads any sheet.** Drop a file in, or let it load the project's goblin sheet by
default. It guesses the cell size from the image dimensions, preferring square cells
around 48px. Override the guess with the two Cell fields if it picks wrong.

**Corrects anchor drift.** Sprite sheets often draw forward travel inside each cell,
so playing a frame range in place makes the character slide sideways. The tool
computes four candidate anchors per frame from pixel data and re-centres every frame
on whichever you pick:

| Anchor | What it uses | When to use it |
| --- | --- | --- |
| Legs | Horizontal centre of the bottom N rows of opaque pixels | Default. Ignores raised arms and swung weapons |
| Mass centre | Centroid of all opaque pixels | Sprites with no limbs to confuse it |
| Bounding box | Centre of the opaque bounding box | Rarely right. Jumps whenever anything extends |
| Off | Nothing | Shows the raw art, useful as a before/after |

Lock baseline pins the lowest opaque pixel to a fixed floor line, which keeps feet
planted. Turn it off when a vertical bob is intentional.

Leg rows sets how far up from the lowest pixel the legs anchor looks. It defaults to
28% of the cell height and is worth adjusting for unusual proportions.

**Exports a frame map.** Name each animation and add it. The JSON at the bottom
carries the grid, the anchor settings, and optionally a per-frame `[dx, dy]` offset
array so a renderer can apply the same correction without recomputing it.

## Controls

- Click a frame on the sheet to set the range start, shift-click to set the end
- Space toggles play, left and right arrows step
- Onion skin draws the previous frame faintly behind the current one. If the anchor
  is right, the two overlap at the anchor point
- Trim empties shrinks the current range past blank cells at either end

## Output shape

```json
{
  "sheet": "goblinsword_fixed.png",
  "frameWidth": 72, "frameHeight": 64,
  "columns": 11, "rows": 5, "frames": 55,
  "anchorX": 36, "floorY": 58, "legDepth": 18,
  "animations": {
    "walk": {
      "from": 11, "to": 18, "fps": 10,
      "pingpong": false, "flip": false,
      "anchor": "legs", "lockBaseline": true,
      "offsets": [[6,3],[7,3],[5,2]]
    }
  }
}
```

`offsets` is indexed from `from`, so `offsets[0]` belongs to the first frame of
the animation, not to frame 0 of the sheet.
