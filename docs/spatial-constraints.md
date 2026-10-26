# Room dimensions and spatial fit

Room input limits are defined once in `shared/room-dimensions.json` and consumed by the Python backend and both frontend room controls. Width and depth must each exceed the short-side minimum, and their product must also meet the minimum area. Converting units preserves the measured dimensions. Clear height is stored when supplied; legacy records without height keep it unknown.

These are application planning limits based on the Indian Model Building Bye-Laws 2016, sections 4.3-4.5, rather than jurisdiction-specific building approval checks. Bedroom/study use the secondary habitable-room allowance, dining uses the main habitable-room baseline, and bathroom means combined bathroom/WC.

## Enforced now

- Room minimum sides, area and supplied clear height; unit-consistent maximum sides.
- ABO category, width, depth, supplied room-height and unit-price-budget filters before vector retrieval limits. Catalogue footprint dimensions must be positive and finite.
- Quantity-aware product budgets and combined floor-footprint screening. A 65% floor-coverage ceiling is a conservative application heuristic, not a building-code rule or proof of walkable circulation. Rugs, wall objects and countertop objects are not blindly summed with floor furniture.
- The critic checks room-envelope and measured-height violations. Known fit failures block image generation.
- The image prompt includes a numerical centimetre room envelope plus real catalogue dimensions, quantities and zone hints. It explicitly forbids enlarging rooms or shrinking products to force a fit.

## What is not established by these checks

An area total and nine compass zones are not a layout. Two objects can overlap even when the total area is small. Current checks do not verify exact object positions, door swings, windows, fixed plumbing, approach clearances, chair pull-out envelopes, wheelchair accessibility, or image-output scale. A missing product/height cannot be certified as fitting. ABO dimensions also need orientation and unit review; packaging dimensions must not replace product geometry.

## Architecture needed for reliable spatial control

1. Collect a measured room polygon, clear height, doors/windows, door swings, fixed fixtures and plumbing positions. Photographs alone do not establish metric geometry.
2. Retrieve catalogue candidates with verified width/depth/height and permitted rotations.
3. Solve a layout using explicit object instances `(item_id, x_cm, y_cm, z_cm, yaw_degrees)`. Represent each unit separately. Check containment, collisions and functional clearance envelopes, allowing intentional overlaps such as rugs under tables and basins over vanities.
4. If there is no feasible layout, choose smaller alternatives or remove optional products and validate again. Do not silently rescale catalogue items.
5. Render the validated scene from the measured camera. Use that render/depth/segmentation as conditioning for a compatible image-generation pipeline, or render the final image directly for strict geometry. A text-only or photo-edit prompt cannot guarantee metric fidelity.
6. Keep the validated layout as the source of truth for fit and shopping exports. Treat an unconstrained generated image as a visualization, not geometric evidence.
