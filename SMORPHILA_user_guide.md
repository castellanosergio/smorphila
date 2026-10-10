# SMORPHILA user guide

SMORPHILA manages a morphometric project from definition to acquisition and export.
The normal starting point is the Project Hub.

## Start SMORPHILA

From the project root folder, run:

```powershell
uv run python src/start.py
```

Use the hub to create or open a project, define its structure, acquire individual
data, review record consistency, and export results.

## Create a project

1. Select **New project**.
2. Enter a project name.
3. Choose where to save the project JSON file.

SMORPHILA creates an `images` subfolder beside the JSON file. For example, saving
`C:\Projects\Example\example.json` creates `C:\Projects\Example\images`.
Place the images to be analysed in that folder. The image picker in **Acquire data**
opens there by default.

## Define the project

Select **Define project** in the Project Hub, then open an image from the definition
editor's **File** menu. Use **Project setup** to display the definition panels.

### Landmarks

Add the required landmark names, select one, and place it on the image. Landmark
names can be renamed or deleted while they are not referenced by another definition.

### Groups

Groups contain ordered, oriented landmark segments. Add a group, then add its
segments. Relative angle constraints can be selected from the angle diagram.

Use **Create idealized polyline** during acquisition to apply the group constraints
to the measured landmarks.

### Reference settings

Reference settings have two independent purposes: optional image alignment and the
analytical reference frame used for coordinates.

#### Image alignment (optional)

Use the two anchors and the vertical or horizontal alignment in the upper part of
the **Reference settings** panel to rotate the image preview. Select **Update
reference axis** to set the anchors, or select **Define from image** and click the
two placed landmarks. Select **Use image vertical default** to remove the custom
image alignment.

Image alignment is only a visual aid. It does not define the coordinate system used
for export.

#### Analytical reference frame

The analytical reference frame defines reproducible coordinates from the idealized
landmark geometry. Select:

- an **Origin landmark**, which becomes coordinate `(0, 0)`;
- two distinct axis landmarks, which define the axis direction; and
- a **Target orientation** of vertical or horizontal.

Select **Update analytical frame** to save the frame, or **Clear analytical frame**
to remove it. The axis landmarks and the origin must be defined landmarks, but the
origin may also be one of the axis landmarks.

When an analytical frame is configured, SMORPHILA first applies the landmark-group
constraints, then centres the idealized landmarks on the origin and rotates them to
the target orientation. Coordinates use an upward-positive Y axis. The same
transformation is applied to semilandmarks during export.

Use image alignment when a consistent on-screen orientation is convenient during
data entry. Use the analytical reference frame when exported coordinates must share
a consistent origin and orientation across individuals.

### Curves and semilandmarks

A curve has a unique name, a start anchor, an end anchor, and a number of intervals.
Select **Add curve** to create it.

To edit an existing curve, select it in the curve list. Its fields are populated with
the saved values. Change the interval count or anchors, then select **Update selected**.
The curve name is preserved during this update so existing individual data remains
associated with the same curve.

The configured number is the number of intervals. A curve with `n` intervals creates
`n + 1` equally spaced coordinates, including both anchor landmarks.

Save the definition project when finished.

## Acquire individual data

Select **Acquire data** in the Project Hub and use **File > Open image**.

1. Place the required landmarks.
2. Select **Landmarks > Create idealized polyline** to apply the landmark-group
   constraints.
3. To acquire a curve, select **Landmarks > Manual semilandmarks**.
4. Choose a configured curve. Both of its anchor landmarks must already be placed.
5. Click successive points along the visible anatomical curve, then double-click to
   finish.

SMORPHILA preserves the manually traced polyline and resamples it at equal distances
along its length. It does not replace the traced curve with a straight line between
the anchors.

When reopening a saved individual with landmark groups, SMORPHILA rebuilds the
idealized polyline from the saved raw landmarks. If an analytical reference frame is
configured, it is applied to the idealized landmarks and semilandmarks when
coordinates are derived for export. This keeps raw measurements and derived
coordinates in compatible coordinate systems.

Save the individual with **File > Save data**. The image is renamed to the individual
code and the individual record is stored in the project JSON.

## Review record consistency

Select **Refresh** in the Project Hub after changing project definitions or saving
individual data. The hub reloads the JSON file and updates its summary.

The **Record status** line reports compatible records and records that need review.
Select **Review inconsistent records** to see each affected individual and the reason,
such as:

- a missing landmark or curve;
- changed curve anchors;
- a changed curve interval count;
- a curve removed from the project;
- project definitions changed since acquisition.

Newly saved individuals include a fingerprint of the project definitions. Older
records without this fingerprint are shown as needing review because their definition
revision cannot be verified reliably.

## Export data

Select **Export data** in the Project Hub. Choose the individuals, landmarks, and
semilandmark curves to export, then choose TPS or TXT.

TPS files use separate sections:

```text
LM=<number of landmarks>
<landmark coordinates>
CURVES=<number of curves>
POINTS=<number of coordinates in the first curve>
<curve coordinates>
...
IMAGE=<individual code>
ID=<progressive number>
```

Landmarks are not mixed with semilandmarks in the `LM` section. Coordinates are
written with five decimal places.

TXT export is a long table with one row per landmark or semilandmark coordinate.

## Common checks

- Save the project definition before acquiring data.
- Place both curve anchors before tracing a curve.
- Use the same final curve configuration for all individuals intended for a shared
  export.
- Refresh the Project Hub after editing definitions or acquiring data.
- Review inconsistent records after any project-definition change and reprocess the
  required individuals before exporting.
