import type { Zone } from "./components/ZoneGrid";

export type Product = {
  id: string;
  category: string;
  name: string;
  price: number;
  width: number;
  depth: number;
  height: number;
  style: string[];
  material: string;
  finish: string;
};

export type PlanItem = {
  slot: string;
  itemId: string;
  fitNote: string;
  zone: Zone;
  vastu: string;
};

export const navItems = [
  { href: "/", label: "Overview" },
  { href: "/workspace", label: "Workspace" },
  { href: "/chat", label: "Chat" },
  { href: "/planner", label: "Planner" },
  { href: "/catalogue", label: "Catalogue" },
  { href: "/image-smoke", label: "Images" },
  { href: "/validation", label: "Validation" },
  { href: "/vastu", label: "Vastu" },
  { href: "/shopping-list", label: "Shopping List" },
  { href: "/brief", label: "Export Brief" },
  { href: "/research", label: "Research" },
  { href: "/evaluation", label: "Evaluation" },
  { href: "/roadmap", label: "Roadmap" },
];

export const products: Product[] = [
  {
    id: "SOF-101",
    category: "Sofa",
    name: "Kavya compact three-seat sofa",
    price: 32000,
    width: 208,
    depth: 88,
    height: 82,
    style: ["warm modern", "family", "minimal"],
    material: "woven fabric",
    finish: "moss grey",
  },
  {
    id: "SOF-118",
    category: "Sofa",
    name: "Nira apartment loveseat",
    price: 24500,
    width: 154,
    depth: 82,
    height: 80,
    style: ["minimal", "small apartment", "scandinavian"],
    material: "cotton blend",
    finish: "stone beige",
  },
  {
    id: "TBL-204",
    category: "Coffee table",
    name: "Aro low storage coffee table",
    price: 9400,
    width: 96,
    depth: 54,
    height: 38,
    style: ["warm modern", "storage", "family"],
    material: "engineered wood",
    finish: "walnut",
  },
  {
    id: "TBL-219",
    category: "Coffee table",
    name: "Mira round nesting table",
    price: 7200,
    width: 72,
    depth: 72,
    height: 42,
    style: ["minimal", "small apartment", "boho"],
    material: "mango wood",
    finish: "natural oak",
  },
  {
    id: "RUG-303",
    category: "Rug",
    name: "Varan handloom flatweave rug",
    price: 7800,
    width: 180,
    depth: 240,
    height: 1,
    style: ["earthy", "warm modern", "indian modern"],
    material: "cotton wool blend",
    finish: "terracotta and ivory",
  },
  {
    id: "RUG-318",
    category: "Rug",
    name: "Tala washable area rug",
    price: 5400,
    width: 150,
    depth: 210,
    height: 1,
    style: ["family", "minimal", "small apartment"],
    material: "polyester",
    finish: "charcoal grid",
  },
  {
    id: "STR-412",
    category: "Storage",
    name: "Ira low media console",
    price: 18500,
    width: 168,
    depth: 42,
    height: 54,
    style: ["warm modern", "indian modern", "minimal"],
    material: "acacia veneer",
    finish: "smoked teak",
  },
  {
    id: "STR-433",
    category: "Storage",
    name: "Duo wall shelf and cabinet",
    price: 12800,
    width: 120,
    depth: 32,
    height: 76,
    style: ["small apartment", "storage", "minimal"],
    material: "powder coated metal and wood",
    finish: "white ash",
  },
  {
    id: "LGT-504",
    category: "Lighting",
    name: "Soma brass floor lamp",
    price: 8900,
    width: 42,
    depth: 42,
    height: 152,
    style: ["warm modern", "indian modern", "earthy"],
    material: "metal and linen",
    finish: "aged brass",
  },
  {
    id: "LGT-526",
    category: "Lighting",
    name: "Luma ceramic table lamp",
    price: 4600,
    width: 28,
    depth: 28,
    height: 48,
    style: ["minimal", "boho", "small apartment"],
    material: "ceramic and cotton",
    finish: "matte cream",
  },
];

export const buildSteps = [
  "Capture room, budget, style, and optional Vastu preferences.",
  "Plan required item slots for the room type.",
  "Retrieve real catalogue items with prices and dimensions.",
  "Check footprint, budget, sourceability, and rule warnings.",
  "Revise failing plans by swapping or simplifying items.",
  "Return a visual concept and itemised designer brief.",
];

export const demoBrief = {
  roomType: "Living room",
  dimensions: "10 ft x 12 ft",
  budget: 85000,
  style: "Warm modern, kid-friendly, extra storage",
  vastu: "Opt-in guidance enabled",
  compass: "Main seating faces north or east where possible",
};

export const planItems: PlanItem[] = [
  {
    slot: "Sofa",
    itemId: "SOF-101",
    fitNote: "Fits the long wall with circulation space.",
    zone: "S",
    vastu: "Good: seating can face north.",
  },
  {
    slot: "Coffee table",
    itemId: "TBL-204",
    fitNote: "Leaves clearance between sofa and media unit.",
    zone: "C",
    vastu: "Neutral central placement.",
  },
  {
    slot: "Rug",
    itemId: "RUG-303",
    fitNote: "Anchors seating without touching all walls.",
    zone: "C",
    vastu: "Neutral central placement.",
  },
  {
    slot: "Storage",
    itemId: "STR-412",
    fitNote: "Low console fits under the preferred wall limit.",
    zone: "W",
    vastu: "Good: heavier storage in west/south zone.",
  },
  {
    slot: "Lighting",
    itemId: "LGT-504",
    fitNote: "Small footprint beside sofa.",
    zone: "SE",
    vastu: "Good: warm light in southeast corner.",
  },
];

export const attempts = [
  {
    name: "Attempt 1",
    result: "Failed",
    note: "Requested sectional exceeded room width and pushed total above budget.",
  },
  {
    name: "Attempt 2",
    result: "Passed",
    note: "Reviser swapped to a compact sofa and lowered accent lighting cost.",
  },
];

export const metrics = [
  { label: "Sourceability", value: "100%", note: "Every selected item maps to a catalogue ID." },
  { label: "Budget pass", value: "Target 90%+", note: "Finished plans should stay within the entered budget." },
  { label: "Fit pass", value: "Target 85%+", note: "Selected items must fit the room footprint and clearances." },
  { label: "Revision success", value: "Target 70%+", note: "A failed first draft should recover within the retry cap." },
];

export function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

export function productById(id: string) {
  return products.find((product) => product.id === id);
}
