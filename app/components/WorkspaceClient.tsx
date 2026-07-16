"use client";

import type { FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { formatCurrency } from "../data";
import { BeforeAfterSlider } from "./BeforeAfterSlider";
import { ZoneGrid, type ZoneGridItem } from "./ZoneGrid";

const directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "C"] as const;
const units = ["ft", "m", "cm"] as const;
const progressStates = ["planning", "designing", "grounding", "checking", "revising", "passed", "failed", "error"] as const;
const tabs = ["shopping", "vastu"] as const;
const wizardSteps = ["Space", "Style", "Preferences", "Vastu", "Budget", "Review"] as const;
const API_BASE = process.env.NEXT_PUBLIC_FORMAOS_API_BASE ?? "http://localhost:8000";
const MIN_BUDGET = 50000;
const MAX_BUDGET = 500000;
const BUDGET_STEP = 5000;
const apiErrorStates = [
  "invalid_brief",
  "no_catalogue_results",
  "retry_exhausted",
  "graph_failure",
  "missing_api_key",
  "image_service_unavailable",
  "image_generation_failed",
  "general error",
] as const;

type Direction = (typeof directions)[number];
type Unit = (typeof units)[number];
type Tab = (typeof tabs)[number];
type ProgressState = (typeof progressStates)[number];

type CatalogueItem = {
  item_id: string;
  title: string;
  product_type: string;
  width_cm: number;
  depth_cm: number;
  height_cm?: number | null;
  material?: string | null;
  color?: string | null;
  price_inr: number;
  image_path?: string | null;
  image_available?: boolean;
  placement_zone?: Direction | null;
};

type GroundedSlot = {
  slot: { slot_id: string; category: string; purpose?: string; style_text?: string; placement_hint?: Direction | null };
  constraints?: { max_width_cm: number; max_depth_cm: number };
  placement_zone: Direction;
  selected_item?: CatalogueItem | null;
  alternatives: CatalogueItem[];
};

type VastuRuleResult = {
  rule_id: string;
  item_id: string;
  status: string;
  badge: string;
  note: string;
  rationale: string;
};

type VastuItemResult = {
  item_id: string;
  title: string;
  zone: Direction;
  badge: string;
  notes: string[];
  rule_results: VastuRuleResult[];
};

type BackendDesign = {
  design_id: string;
  session_id: string;
  project_id: string;
  project_name: string;
  user_id?: string | null;
  generated_at: string;
  room_brief: {
    room_type: string;
    width: number;
    depth: number;
    units: Unit;
    budget_inr: number;
    style_words: string[];
    constraints: string[];
    vastu_enabled: boolean;
    main_door_direction?: Direction | null;
    compass_direction?: Direction | null;
  };
  concept_image?: ConceptImage | null;
  concept_history?: ConceptRevision[];
  source_images?: string[];
  last_revision_request?: string;
  chat_messages?: Array<{ role: "user" | "assistant"; content: string }>;
  status: "passed" | "failed";
  grounder_output: { grounded_slots: GroundedSlot[] };
  critic_verdict: {
    passed: boolean;
    total_price_inr: number;
    fit: { status: string; notes: string[] };
    budget: { status: string; notes: string[] };
    sourceability: { status: string; notes: string[] };
    vastu: { status: string; notes: string[] };
    vastu_result?: { score: number; item_results: VastuItemResult[]; notes: string[] } | null;
  };
};

type DesignSummary = {
  design_id: string;
  session_id: string;
  project_id: string;
  project_name: string;
  user_id?: string | null;
  generated_at: string;
  status: string;
  room_type: string;
  total_price_inr: number;
  item_count: number;
  style_words: string[];
  preview_image_data_url?: string | null;
  preview_image_path?: string | null;
};

type StoredHomeowner = {
  id: string;
  name: string;
  email: string;
  location?: string;
  home_type?: string;
  preferred_units?: Unit;
};

type ProfileDraft = {
  name: string;
  location: string;
  homeType: string;
  preferredUnits: Unit;
};

type PhotoNote = {
  name: string;
  url: string;
  dataUrl: string;
  note: string;
};

type StyleCard = {
  label: string;
  imageSrc: string;
  cues: string;
  palette: Array<{ name: string; hex: string }>;
};

type FinishScheduleItem = {
  category: string;
  recommendation: string;
  quantity: string;
  note: string;
  colourName: string;
  hex: string;
  link: string;
  linkLabel: string;
  colourSource?: "generated_image";
  imageCrop?: { x: number; y: number; width: number; height: number };
};

type ProjectChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  createdAt: string;
};

type ConceptImage = {
  mode: "generated" | "prompt_only";
  image_prompt: string;
  image_data_url?: string | null;
  notes: string[];
  revision_id?: string | null;
  concept_history?: ConceptRevision[];
};

type RevisionProduct = Partial<CatalogueItem> & {
  category: string;
  item_id: string;
  title: string;
  imageMatch?: "closest_catalogue_match" | "not_visible";
  matchConfidence?: number | null;
};

type ConceptRevision = ConceptImage & {
  revision_id: string;
  version: number;
  label: string;
  revision_text: string;
  generated_at: string;
  source: string;
  selected_products: RevisionProduct[];
  finish_schedule?: FinishScheduleItem[];
};

class ApiRequestError extends Error {
  design?: BackendDesign;

  constructor(message: string, design?: BackendDesign) {
    super(message);
    this.design = design;
  }
}

function apiUrl(path: string) {
  return `${API_BASE}${path}`;
}

function apiFetch(path: string, init?: RequestInit) {
  return fetch(apiUrl(path), { ...init, credentials: "include" });
}

function styleWords(value: string) {
  return value
    .toLowerCase()
    .split(/[, ]+/)
    .map((word) => word.trim())
    .filter(Boolean);
}

function constraintsFrom(value: string) {
  const normalized = value.toLowerCase();
  const constraints = [];
  if (normalized.includes("kid") || normalized.includes("child")) constraints.push("kid-friendly");
  if (normalized.includes("light")) constraints.push("natural light");
  if (normalized.includes("storage")) constraints.push("extra storage");
  if (normalized.includes("open")) constraints.push("open layout");
  return constraints.length ? constraints : ["clear circulation"];
}

function cmValue(value: number, unit: Unit) {
  if (unit === "cm") return value;
  if (unit === "m") return value * 100;
  return value * 30.48;
}

function safeImagePath(item: CatalogueItem) {
  if (item.image_available && item.image_path) {
    return item.image_path.startsWith("/") ? item.image_path : `/${item.image_path}`;
  }
  return "/product-placeholder.svg";
}

function productSearchUrl(item: CatalogueItem) {
  return `https://www.amazon.in/s?k=${encodeURIComponent(`${item.title} ${item.material ?? ""} ${item.color ?? ""}`.trim())}`;
}

function safePreviewPath(summary: DesignSummary) {
  if (summary.preview_image_data_url) return summary.preview_image_data_url;
  if (summary.preview_image_path) {
    return summary.preview_image_path.startsWith("/") ? summary.preview_image_path : `/${summary.preview_image_path}`;
  }
  return "/product-placeholder.svg";
}

function selectedSlots(design: BackendDesign | null) {
  return design?.grounder_output.grounded_slots.filter((slot) => slot.selected_item) ?? [];
}

function storedMessages(design: BackendDesign): ProjectChatMessage[] {
  return (design.chat_messages ?? []).map((message, index) => ({
    id: `${design.design_id}-message-${index}`,
    role: message.role,
    text: message.content,
    createdAt: design.generated_at,
  }));
}

function selectedStyleCues(styles: string[]) {
  return styles
    .map((style) => styleCards.find((styleCard) => styleCard.label === style)?.cues)
    .filter(Boolean)
    .join("; ");
}

function selectedStylePalettes(styles: string[]) {
  return styles
    .map((style) => styleCards.find((styleCard) => styleCard.label === style))
    .filter((styleCard): styleCard is StyleCard => Boolean(styleCard));
}

function finishScheduleFor(
  styles: string[],
  roomType: string,
  slots: GroundedSlot[],
  revisionText = "",
  revisionMode: "targeted" | "variation" = "targeted",
): FinishScheduleItem[] {
  const normalizedStyles = styles.map((style) => style.toLowerCase());
  const has = (style: string) => normalizedStyles.includes(style);
  let leadPalette = styleCards.find((styleCard) => styleCard.label === styles[0])?.palette ?? [
    { name: "Porcelain", hex: "#E9E5DC" }, { name: "Walnut", hex: "#76523B" }, { name: "Olive", hex: "#6F765A" },
    { name: "Charcoal", hex: "#333734" }, { name: "Burnt Rust", hex: "#B85C3E" },
  ];
  const normalizedRevision = revisionText.toLowerCase();
  const revisionPalettes = {
    calm: [
      { name: "Mineral White", hex: "#ECEDE8" }, { name: "Pale Oak", hex: "#CDBD9F" }, { name: "Eucalyptus", hex: "#82958B" },
      { name: "Soft Charcoal", hex: "#4A504D" }, { name: "Dusty Blue", hex: "#708A99" },
    ],
    warm: [
      { name: "Warm Ivory", hex: "#F3EBDD" }, { name: "Natural Walnut", hex: "#7A5740" }, { name: "Sage", hex: "#7B8668" },
      { name: "Deep Bronze", hex: "#433A32" }, { name: "Terracotta", hex: "#B85F42" },
    ],
    bright: [
      { name: "Gallery White", hex: "#F7F5EF" }, { name: "White Oak", hex: "#D9C49F" }, { name: "Sky Grey", hex: "#B9C6CA" },
      { name: "Ink", hex: "#2F3A3D" }, { name: "Soft Ochre", hex: "#C69A45" },
    ],
    alternate: [
      { name: "Soft Stone", hex: "#E2DED5" }, { name: "Smoked Oak", hex: "#80664F" }, { name: "Moss", hex: "#69745E" },
      { name: "Deep Teal", hex: "#315D5A" }, { name: "Clay", hex: "#B9684C" },
    ],
  };
  if (normalizedRevision) {
    if (/calm|quiet|soft|serene/.test(normalizedRevision)) leadPalette = revisionPalettes.calm;
    else if (/warm|cozy|cosy|earthy/.test(normalizedRevision)) leadPalette = revisionPalettes.warm;
    else if (/bright|light|airy|fresh/.test(normalizedRevision)) leadPalette = revisionPalettes.bright;
    else if (revisionMode === "variation" || /alternative|different|restyle/.test(normalizedRevision)) leadPalette = revisionPalettes.alternate;
  }
  const namedColours = [
    { pattern: /sage/, name: "Sage", hex: "#87947A" }, { pattern: /olive/, name: "Olive", hex: "#6F765A" },
    { pattern: /terracotta|rust/, name: "Terracotta", hex: "#B85F42" }, { pattern: /navy/, name: "Navy", hex: "#263B52" },
    { pattern: /teal/, name: "Deep Teal", hex: "#376B68" }, { pattern: /blue/, name: "Dusty Blue", hex: "#708A99" },
    { pattern: /green/, name: "Moss Green", hex: "#69745E" }, { pattern: /charcoal|black/, name: "Charcoal", hex: "#333734" },
    { pattern: /white|ivory/, name: "Warm White", hex: "#F3EFE5" }, { pattern: /beige|cream/, name: "Linen Beige", hex: "#D8C9B5" },
  ];
  const requestedColour = namedColours.find((colour) => colour.pattern.test(normalizedRevision));
  if (requestedColour) {
    const requestedIndex = /wall|paint/.test(normalizedRevision) ? 0 : 4;
    leadPalette = leadPalette.map((colour, index) => index === requestedIndex ? requestedColour : colour);
  }
  const [base, material, secondary, contrast, accent] = leadPalette;
  const palette = {
    wall: [base.name, base.hex],
    floor: [material.name, material.hex],
    secondary: [secondary.name, secondary.hex],
    contrast: [contrast.name, contrast.hex],
    accent: [accent.name, accent.hex],
  };
  const roomLabel = roomType.replace("_", " ");
  const selectedCategories = new Set(slots.map((slot) => slot.slot.category));
  const sourceableNote = selectedCategories.size
    ? `Coordinates with selected ${Array.from(selectedCategories).join(", ")}.`
    : "Coordinates with selected sourceable furniture once generated.";

  const schedule: FinishScheduleItem[] = [
    {
      category: "Wall paint",
      recommendation: `${palette.wall[0]} washable low-sheen emulsion`,
      quantity: "1 main wall colour + 1 optional accent",
      note: "Use low-sheen washable paint for homeowner maintenance.",
      colourName: palette.wall[0],
      hex: palette.wall[1],
      link: "https://www.asianpaints.com/colour-catalogue.html",
      linkLabel: "Open Asian Paints catalogue",
    },
    {
      category: "Flooring",
      recommendation: `${palette.floor[0]} matte wood or stone-look finish`,
      quantity: "Room floor area + 10% cutting allowance",
      note: `Choose a durable finish suited to a ${roomLabel}; confirm the sample in daylight before ordering.`,
      colourName: palette.floor[0],
      hex: palette.floor[1],
      link: "https://www.mikasafloors.com/collections/pristine",
      linkLabel: "Browse Mikasa flooring",
    },
    {
      category: "Tiles",
      recommendation: `${palette.wall[0]} or ${palette.floor[0]} matte large-format tile`,
      quantity: "Feature or wet-zone area + 12% allowance",
      note: "Use one restrained tile family so it matches the generated room instead of adding a new pattern.",
      colourName: palette.wall[0],
      hex: palette.wall[1],
      link: "https://www.kajariaceramics.com/catalogues",
      linkLabel: "Browse Kajaria tiles",
    },
    {
      category: "Window treatments",
      recommendation: has("industrial") ? "linen curtains on black rods" : "linen or cotton curtains in warm off-white",
      quantity: "1 set per window",
      note: "Keep curtain length floor-touching where practical.",
      colourName: palette.secondary[0],
      hex: palette.secondary[1],
      link: "https://www.ikea.com/in/en/cat/curtains-10700/",
      linkLabel: "Browse IKEA curtains",
    },
    {
      category: "Plants",
      recommendation: has("minimal") || has("japandi") ? "one sculptural floor plant plus one small tabletop plant" : "two floor plants plus one tabletop plant",
      quantity: "2-3 plants",
      note: "Place larger greenery near natural light and keep circulation clear.",
      colourName: palette.secondary[0],
      hex: palette.secondary[1],
      link: "https://www.ugaoo.com/collections/indoor-plants",
      linkLabel: "Browse Ugaoo plants",
    },
    {
      category: "Paintings & wall art",
      recommendation: has("classic") ? "framed landscape or botanical artwork" : has("boho") ? "woven art or earthy abstract print" : "large abstract print matched to the palette",
      quantity: "1 large piece or 2 balanced frames",
      note: `Scale art to the ${roomLabel} wall instead of using small scattered frames.`,
      colourName: palette.contrast[0],
      hex: palette.contrast[1],
      link: "https://www.ikea.com/in/en/cat/wall-art-wall-painting-10788/",
      linkLabel: "Browse paintings and wall art",
    },
    {
      category: "Showpieces",
      recommendation: has("japandi") || has("minimal") ? "ceramic vessel, stone bowl, one tray" : "ceramic vessels, books, tray, candle holder, small sculptural object",
      quantity: "3-5 objects",
      note: "Group objects in odd numbers and leave empty surface area.",
      colourName: palette.accent[0],
      hex: palette.accent[1],
      link: "https://www.ikea.com/in/en/cat/decoration-de001/",
      linkLabel: "Browse IKEA decor",
    },
    {
      category: "Soft furnishings",
      recommendation: has("boho") ? "patterned cushions, textured throw, layered rug tones" : "2-4 cushions and one throw in the selected palette",
      quantity: "3-5 pieces",
      note: sourceableNote,
      colourName: palette.accent[0],
      hex: palette.accent[1],
      link: "https://www.ikea.com/in/en/cat/textiles-tl001/",
      linkLabel: "Browse IKEA textiles",
    },
    {
      category: "Lighting layer",
      recommendation: "warm 2700K bulbs, one ambient source, one task or accent source",
      quantity: "2 lighting layers minimum",
      note: "Avoid cool white bulbs; they make generated and real rooms feel less residential.",
      colourName: "Warm White",
      hex: "#FFD8A8",
      link: "https://www.ikea.com/in/en/cat/lighting-li001/",
      linkLabel: "Browse IKEA lighting",
    },
  ];
  if (roomType === "bedroom") {
    schedule.splice(schedule.length - 1, 0, {
      category: "Bedding",
      recommendation: `${palette.secondary[0]} cotton bed linen with coordinated duvet cover, sheet, and pillowcases`,
      quantity: "1 fitted or flat sheet + 1 duvet cover + 2-4 pillowcases",
      note: "Match the mattress size and repeat the generated room's textile colour instead of introducing a new palette.",
      colourName: palette.secondary[0],
      hex: palette.secondary[1],
      link: "https://www.ikea.com/in/en/cat/bed-linen-10651/",
      linkLabel: "Browse IKEA bed linen",
    });
  }
  return schedule;
}

function DesignElementPreview({
  imageSrc,
  crop,
  alt,
}: {
  imageSrc: string;
  crop?: FinishScheduleItem["imageCrop"];
  alt: string;
}) {
  const validCrop = crop && crop.width > 0 && crop.height > 0;
  if (!validCrop) {
    return <div className="finish-design-preview full"><img src={imageSrc} alt={alt} /></div>;
  }
  return (
    <div
      className="finish-design-preview cropped"
      style={{ aspectRatio: `${crop.width * 1.5} / ${crop.height}` }}
    >
      <img
        src={imageSrc}
        alt={alt}
        style={{
          width: `${100000 / crop.width}%`,
          left: `${-100 * crop.x / crop.width}%`,
          top: `${-100 * crop.y / crop.height}%`,
        }}
      />
    </div>
  );
}

function errorMessage(payload: unknown, fallback: string) {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) return fallback;
  const detail = (payload as { detail?: { code?: string; message?: string } }).detail;
  const knownCode = apiErrorStates.find((code) => code === detail?.code);
  return knownCode ? `${knownCode}: ${detail?.message ?? fallback}` : fallback;
}

function errorDesign(payload: unknown) {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) return undefined;
  return (payload as { detail?: { design?: BackendDesign } }).detail?.design;
}

const styleCards: StyleCard[] = [
  {
    label: "Modern",
    imageSrc: "/style-images/modern.png",
    cues: "clean lines, warm neutrals, walnut, black metal, restrained art",
    palette: [
      { name: "Porcelain", hex: "#E9E5DC" }, { name: "Walnut", hex: "#76523B" }, { name: "Olive", hex: "#6F765A" },
      { name: "Charcoal", hex: "#333734" }, { name: "Burnt Rust", hex: "#B85C3E" },
    ],
  },
  {
    label: "Minimal",
    imageSrc: "/style-images/minimal.png",
    cues: "negative space, pale oak, linen, hidden storage, very few objects",
    palette: [
      { name: "Chalk", hex: "#F4F1E8" }, { name: "Pale Oak", hex: "#D4C09D" }, { name: "Mushroom", hex: "#B4A99A" },
      { name: "Graphite", hex: "#3B403D" }, { name: "Soft Sage", hex: "#89917D" },
    ],
  },
  {
    label: "Scandinavian",
    imageSrc: "/style-images/scandinavian.png",
    cues: "light wood, wool, soft grey, airy storage, cozy practical layers",
    palette: [
      { name: "Nordic White", hex: "#F4F3EE" }, { name: "Blonde Oak", hex: "#D6BE96" }, { name: "Mist", hex: "#B7C1BD" },
      { name: "Fjord Blue", hex: "#728A96" }, { name: "Soft Ochre", hex: "#C49A4A" },
    ],
  },
  {
    label: "Boho",
    imageSrc: "/style-images/boho.png",
    cues: "rattan, jute, terracotta, patterned textiles, plants, collected decor",
    palette: [
      { name: "Warm Ivory", hex: "#F1E7D4" }, { name: "Terracotta", hex: "#B85F42" }, { name: "Saffron", hex: "#D39A35" },
      { name: "Deep Teal", hex: "#376B68" }, { name: "Leaf Green", hex: "#52634A" },
    ],
  },
  {
    label: "Contemporary",
    imageSrc: "/style-images/contemporary.png",
    cues: "curved forms, statement lighting, abstract art, mixed stone and wood",
    palette: [
      { name: "Soft Taupe", hex: "#C8BAAA" }, { name: "American Walnut", hex: "#77533B" }, { name: "Ink", hex: "#30363A" },
      { name: "Burnt Rust", hex: "#A8563D" }, { name: "Mineral Blue", hex: "#647D86" },
    ],
  },
  {
    label: "Classic",
    imageSrc: "/style-images/classic.png",
    cues: "symmetry, carved wood, brass, framed art, tailored upholstery",
    palette: [
      { name: "Soft Cream", hex: "#F2E8D5" }, { name: "Warm Walnut", hex: "#76513A" }, { name: "Heritage Navy", hex: "#34465B" },
      { name: "Oxblood", hex: "#743E3D" }, { name: "Antique Brass", hex: "#B08D57" },
    ],
  },
  {
    label: "Japandi",
    imageSrc: "/style-images/japandi.png",
    cues: "low furniture, slatted wood, linen, clay, stone, muted earth tones",
    palette: [
      { name: "Limewash", hex: "#D9CFBD" }, { name: "Natural Oak", hex: "#C4A477" }, { name: "Clay", hex: "#A8684E" },
      { name: "Muted Olive", hex: "#727760" }, { name: "Sumi Ink", hex: "#343635" },
    ],
  },
  {
    label: "Industrial",
    imageSrc: "/style-images/industrial.png",
    cues: "cognac leather, black steel, brick, concrete, reclaimed wood",
    palette: [
      { name: "Concrete", hex: "#A7A39D" }, { name: "Black Steel", hex: "#282B2C" }, { name: "Cognac", hex: "#9A5F3D" },
      { name: "Brick", hex: "#8E4937" }, { name: "Aged Brass", hex: "#A4844C" },
    ],
  },
];
const styleOptions = styleCards.map((styleCard) => styleCard.label);
const preferenceOptions = ["More storage", "Natural light", "Open layout", "Greenery", "Warm tones", "Modern look", "Smart lighting", "Kid friendly"];

function newProjectId() {
  return `project-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function newChatMessage(role: ProjectChatMessage["role"], text: string): ProjectChatMessage {
  return {
    id: `msg-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    role,
    text,
    createdAt: new Date().toISOString(),
  };
}

export function WorkspaceClient() {
  const router = useRouter();
  const [homeowner, setHomeowner] = useState<StoredHomeowner | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileError, setProfileError] = useState("");
  const [profileDraft, setProfileDraft] = useState<ProfileDraft>({ name: "", location: "", homeType: "apartment", preferredUnits: "ft" });
  const [authLoading, setAuthLoading] = useState(true);
  const [step, setStep] = useState(0);
  const [activeTab, setActiveTab] = useState<Tab>("shopping");
  const [progress, setProgress] = useState<ProgressState>("planning");
  const [sessionId, setSessionId] = useState("");
  const [currentProjectId, setCurrentProjectId] = useState(() => newProjectId());
  const [design, setDesign] = useState<BackendDesign | null>(null);
  const [conceptImage, setConceptImage] = useState<ConceptImage | null>(null);
  const [selectedRevisionId, setSelectedRevisionId] = useState("");
  const [savedDesigns, setSavedDesigns] = useState<DesignSummary[]>([]);
  const [projectChats, setProjectChats] = useState<Record<string, ProjectChatMessage[]>>({});
  const [photos, setPhotos] = useState<PhotoNote[]>([]);
  const [loading, setLoading] = useState(false);
  const [conceptLoading, setConceptLoading] = useState(false);
  const [selectingItemId, setSelectingItemId] = useState("");
  const [deletingProjectId, setDeletingProjectId] = useState("");
  const [error, setError] = useState("");
  const [roomType, setRoomType] = useState("living_room");
  const [unit, setUnit] = useState<Unit>("ft");
  const [width, setWidth] = useState(14);
  const [depth, setDepth] = useState(18);
  const [height, setHeight] = useState(10);
  const [budget, setBudget] = useState(245000);
  const [budgetInput, setBudgetInput] = useState("245000");
  const [selectedStyles, setSelectedStyles] = useState(["Modern"]);
  const [selectedPreferences, setSelectedPreferences] = useState(["More storage", "Natural light", "Greenery"]);
  const [vastuEnabled, setVastuEnabled] = useState(true);
  const [mainDoor, setMainDoor] = useState<Direction>("N");
  const [compass, setCompass] = useState<Direction>("N");
  const [chatInput, setChatInput] = useState("Make this calmer and keep the same budget.");

  const style = [...selectedStyles, ...selectedPreferences].join(" ");
  const designGoal = `Design my ${roomType.replace("_", " ")} with ${selectedStyles.join(", ")} style.`;
  const message = `Create a saved design with ${selectedPreferences.join(", ")}.`;
  const dimensionsLabel = `${depth} ft x ${width} ft x ${height} ft`;
  const projectName = `${roomType.replace("_", " ")} - ${selectedStyles.slice(0, 2).join(", ") || "New design"}`;
  const photoNotes = photos.map((photo) => `${photo.name}: ${photo.note}`);
  const slots = selectedSlots(design);
  const budgetStatus = design?.critic_verdict.budget.status ?? "waiting";
  const vastuScore = design?.critic_verdict.vastu_result?.score ?? 0;
  const styleCueText = selectedStyleCues(selectedStyles);
  const stylePalettes = selectedStylePalettes(selectedStyles);
  const leadStylePalette = stylePalettes[0];
  const palettePrompt = leadStylePalette
    ? `${leadStylePalette.label}: ${leadStylePalette.palette.map((colour) => `${colour.name} ${colour.hex}`).join(", ")}`
    : "";
  const sourceImage = design?.source_images?.[0] ?? photos[0]?.dataUrl ?? null;
  const conceptHistory = design?.concept_history ?? conceptImage?.concept_history ?? [];
  const selectedRevision = conceptHistory.find((revision) => revision.revision_id === selectedRevisionId) ?? conceptHistory.at(-1);
  const selectedRevisionIndex = selectedRevision
    ? conceptHistory.findIndex((revision) => revision.revision_id === selectedRevision.revision_id)
    : -1;
  const displayedConcept = selectedRevision ?? conceptImage;
  const comparisonImage = selectedRevisionIndex > 0
    ? conceptHistory[selectedRevisionIndex - 1]?.image_data_url ?? sourceImage
    : sourceImage;
  const displayedProducts: RevisionProduct[] = selectedRevision?.selected_products ?? slots.map((slot) => ({
    ...(slot.selected_item as CatalogueItem),
    category: slot.slot.category,
  }));
  const displayedSlots: GroundedSlot[] = selectedRevision?.selected_products?.length
    ? selectedRevision.selected_products.map((product) => {
      const currentSlot = slots.find((slot) => slot.slot.category === product.category || slot.selected_item?.item_id === product.item_id);
      const isCurrentSelection = currentSlot?.selected_item?.item_id === product.item_id;
      return {
        slot: currentSlot?.slot ?? { slot_id: `revision-${product.item_id}`, category: product.category },
        constraints: currentSlot?.constraints,
        placement_zone: (product.placement_zone ?? currentSlot?.placement_zone ?? "C") as Direction,
        selected_item: product as CatalogueItem,
        alternatives: isCurrentSelection ? currentSlot?.alternatives ?? [] : [],
      };
    })
    : slots;
  const visibleTotal = displayedSlots.reduce((sum, slot) => sum + (slot.selected_item?.price_inr ?? 0), 0);
  const backendTotal = selectedRevision?.selected_products?.length ? visibleTotal : design?.critic_verdict.total_price_inr ?? 0;
  const exactTotal = design ? visibleTotal === backendTotal : false;
  const budgetPercent = budget > 0 ? Math.min(100, Math.round(((design ? backendTotal : budget) / budget) * 100)) : 0;
  const finishSchedule = selectedRevision?.finish_schedule?.length
    ? selectedRevision.finish_schedule
    : finishScheduleFor(selectedStyles, roomType, displayedSlots, selectedRevision?.revision_text);
  const widthCm = Math.round(cmValue(width, unit));
  const depthCm = Math.round(cmValue(depth, unit));
  const zoneItems: ZoneGridItem[] = displayedSlots.map((slot) => ({
    slot: slot.slot.category.replaceAll("_", " "),
    detail: slot.selected_item?.title ?? slot.slot.category,
    zone: slot.placement_zone,
  }));
  const ruleResults = useMemo(() => {
    return design?.critic_verdict.vastu_result?.item_results.flatMap((item) => item.rule_results) ?? [];
  }, [design]);
  const projectCards = useMemo(() => {
    const latestByProject = new Map<string, DesignSummary>();
    for (const savedDesign of savedDesigns) {
      const existing = latestByProject.get(savedDesign.project_id);
      if (!existing || new Date(savedDesign.generated_at) > new Date(existing.generated_at)) {
        latestByProject.set(savedDesign.project_id, savedDesign);
      }
    }
    return Array.from(latestByProject.values()).sort(
      (left, right) => new Date(right.generated_at).getTime() - new Date(left.generated_at).getTime(),
    );
  }, [savedDesigns]);
  const activeProjectMessages = projectChats[currentProjectId] ?? [];

  const roomBrief = {
    room_type: roomType,
    width,
    depth,
    units: unit,
    budget_inr: budget,
    style_words: styleWords(style),
    constraints: constraintsFrom(style),
    vastu_enabled: vastuEnabled,
    main_door_direction: mainDoor,
    compass_direction: compass,
  };

  useEffect(() => {
    let active = true;
    apiFetch("/api/auth/me")
      .then(async (response) => {
        if (!response.ok) {
          router.replace("/login?next=/workspace");
          return;
        }
        const payload = await response.json();
        if (!active) return;
        setHomeowner(payload.user);
        if (units.includes(payload.user.preferred_units)) setUnit(payload.user.preferred_units);
        await refreshSavedDesigns(payload.user).catch((caught) => {
          if (active) setError(caught instanceof Error ? caught.message : "Could not load saved projects.");
        });
      })
      .catch(() => {
        if (active) setError("We could not connect to your account. Check that the backend is running.");
      })
      .finally(() => {
        if (active) setAuthLoading(false);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    setBudgetInput(String(budget));
  }, [budget]);

  function updateBudgetFromSlider(value: number) {
    setBudget(value);
    setBudgetInput(String(value));
  }

  function updateBudgetInput(value: string) {
    setBudgetInput(value);
    const parsed = Number(value);
    if (Number.isFinite(parsed) && parsed >= MIN_BUDGET && parsed <= MAX_BUDGET) {
      setBudget(Math.round(parsed));
    }
  }

  function commitBudgetInput() {
    const parsed = Number(budgetInput);
    const normalized = Number.isFinite(parsed)
      ? Math.min(MAX_BUDGET, Math.max(MIN_BUDGET, Math.round(parsed)))
      : budget;
    setBudget(normalized);
    setBudgetInput(String(normalized));
  }

  function updateProjectChat(projectId: string, updater: (messages: ProjectChatMessage[]) => ProjectChatMessage[]) {
    setProjectChats((current) => {
      const next = { ...current, [projectId]: updater(current[projectId] ?? []) };
      return next;
    });
  }

  function appendProjectMessage(projectId: string, role: ProjectChatMessage["role"], text: string) {
    updateProjectChat(projectId, (messages) => [...messages, newChatMessage(role, text)]);
  }

  async function parseResponse(response: Response) {
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new ApiRequestError(errorMessage(payload, "API request failed"), errorDesign(payload));
    return payload;
  }

  async function refreshSavedDesigns(user = homeowner) {
    if (!user) {
      setSavedDesigns([]);
      return;
    }
    const response = await apiFetch(`/api/designs?user_id=${encodeURIComponent(user.id)}`);
    const payload = await parseResponse(response);
    setSavedDesigns(payload.designs ?? []);
  }

  function toggleOption(value: string, selected: string[], setter: (values: string[]) => void, limit?: number) {
    if (selected.includes(value)) {
      setter(selected.filter((item) => item !== value));
      return;
    }
    if (limit && selected.length >= limit) return;
    setter([...selected, value]);
  }

  async function fileToDataUrl(file: File) {
    return await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
  }

  async function handlePhotos(files: FileList | null) {
    if (!files) return;
    const selected = await Promise.all(Array.from(files).slice(0, 4).map(async (file) => ({
      name: file.name,
      url: URL.createObjectURL(file),
      dataUrl: await fileToDataUrl(file),
      note: "Uploaded room photo to preserve architecture, light, and existing layout.",
    })));
    setPhotos((current) => [...current, ...selected].slice(0, 4));
  }

  async function loadDesign(designId: string) {
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch(`/api/design/${designId}`);
      const payload = await parseResponse(response);
      setDesign(payload.design);
      setSessionId(payload.design.session_id);
      setCurrentProjectId(payload.design.project_id);
      setConceptImage(payload.design.concept_image ?? null);
      setSelectedRevisionId(payload.design.concept_history?.at(-1)?.revision_id ?? payload.design.concept_image?.revision_id ?? "");
      setRoomType(payload.design.room_brief.room_type);
      setWidth(payload.design.room_brief.width);
      setDepth(payload.design.room_brief.depth);
      setUnit(payload.design.room_brief.units);
      setBudget(payload.design.room_brief.budget_inr);
      setSelectedStyles(payload.design.room_brief.style_words.length ? payload.design.room_brief.style_words : ["Modern"]);
      setSelectedPreferences(payload.design.room_brief.constraints.length ? payload.design.room_brief.constraints : ["More storage"]);
      setVastuEnabled(payload.design.room_brief.vastu_enabled);
      setMainDoor((payload.design.room_brief.main_door_direction ?? "N") as Direction);
      setCompass((payload.design.room_brief.compass_direction ?? "N") as Direction);
      updateProjectChat(payload.design.project_id, () => storedMessages(payload.design).length ? storedMessages(payload.design) : [
        newChatMessage("assistant", `Loaded ${payload.design.project_name}. Ask for a revision to continue this project chat.`),
      ]);
      setProgress(payload.design.status === "failed" ? "failed" : "passed");
      setActiveTab(payload.design.room_brief.vastu_enabled ? "vastu" : "shopping");
      setStep(5);
    } catch (caught) {
      setProgress("error");
      setError(caught instanceof Error ? caught.message : "general error");
    } finally {
      setLoading(false);
    }
  }

  async function generateConcept(
    sourceDesign = design,
    revisionText = "",
    baseRevisionId = selectedRevisionId,
    revisionMode: "targeted" | "variation" = "targeted",
  ) {
    if (!sourceDesign) return;
    setConceptLoading(true);
    try {
      const revisionSchedule = finishScheduleFor(
        selectedStyles,
        roomType,
        selectedSlots(sourceDesign),
        revisionText,
        revisionMode,
      );
      const scheduledPalette = revisionSchedule
        .filter((item, index, items) => items.findIndex((candidate) => candidate.hex === item.hex) === index)
        .slice(0, 5)
        .map((item) => `${item.colourName} ${item.hex}`)
        .join(", ");
      const response = await apiFetch("/api/concept-image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          design_id: sourceDesign.design_id,
          base_revision_id: revisionText && baseRevisionId ? baseRevisionId : undefined,
          revision_mode: revisionMode,
          project_type: photos.length || sourceDesign.source_images?.length ? "renovation" : "new_space",
          room_type: roomType,
          dimensions: dimensionsLabel,
          style_words: styleWords(style),
          constraints: constraintsFrom(style),
          questionnaire: {
            mood: selectedStyles.join(", "),
            style_cues: styleCueText,
            colour_palette: revisionText ? scheduledPalette : palettePrompt,
            colour_distribution: "Use a 55% dominant base, 20% natural material tone, 15% secondary hue, and two 5% accents. Show at least four palette colours in the room.",
            material_schedule: revisionSchedule.map((item) => `${item.category}: ${item.recommendation}; ${item.colourName} ${item.hex}`).join(" | "),
            homeowner_location: homeowner?.location || "not provided",
            home_type: homeowner?.home_type || "not provided",
            priority: selectedPreferences.join(", "),
            avoid: "clutter, wrong scale, unrealistic furniture",
            lifestyle: "homeowner-led design",
          },
          photo_notes: photoNotes,
          photo_data_urls: photos.map((photo) => photo.dataUrl),
          revision_text: revisionText,
          finish_schedule: revisionSchedule,
          vastu_enabled: vastuEnabled,
          grounded_design: sourceDesign,
        }),
      });
      const payload = await parseResponse(response);
      const nextConcept = payload.image_data_url ? payload : sourceDesign.concept_image ?? payload;
      const nextHistory = payload.concept_history ?? sourceDesign.concept_history ?? [];
      setConceptImage(nextConcept);
      setSelectedRevisionId(payload.revision_id ?? nextHistory.at(-1)?.revision_id ?? "");
      setDesign({
        ...sourceDesign,
        source_images: photos.length ? photos.slice(0, 2).map((photo) => photo.dataUrl) : sourceDesign.source_images,
        concept_image: nextConcept,
        concept_history: nextHistory,
        last_revision_request: payload.image_data_url ? "" : sourceDesign.last_revision_request,
      });
      return payload as ConceptImage;
    } finally {
      setConceptLoading(false);
    }
  }

  function startNewProject() {
    setCurrentProjectId(newProjectId());
    setSessionId("");
    setDesign(null);
    setConceptImage(null);
    setSelectedRevisionId("");
    setConceptLoading(false);
    setPhotos([]);
    setUnit(homeowner?.preferred_units && units.includes(homeowner.preferred_units) ? homeowner.preferred_units : "ft");
    setActiveTab("shopping");
    setProgress("planning");
    setError("");
    setChatInput("Make this calmer and keep the same budget.");
    setStep(0);
  }

  async function deleteProject(projectId: string, projectName: string) {
    if (!window.confirm(`Delete ${projectName} and its complete chat and design history? This cannot be undone.`)) return;
    setDeletingProjectId(projectId);
    setError("");
    try {
      const response = await apiFetch(`/api/projects/${encodeURIComponent(projectId)}`, { method: "DELETE" });
      await parseResponse(response);
      setSavedDesigns((current) => current.filter((savedDesign) => savedDesign.project_id !== projectId));
      setProjectChats((current) => {
        const next = { ...current };
        delete next[projectId];
        return next;
      });
      if (projectId === currentProjectId) startNewProject();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete this project.");
    } finally {
      setDeletingProjectId("");
    }
  }

  async function startDesign() {
    if (!homeowner) {
      setError("sign_in_required: sign in so YourSpace can save this design to your account");
      return;
    }
    if (design && !displayedConcept?.image_data_url) {
      setLoading(true);
      setError("");
      setProgress("designing");
      appendProjectMessage(design.project_id, "assistant", "The room plan is saved. I am generating its first visual now.");
      try {
        const imagePayload = await generateConcept(design);
        setProgress(imagePayload?.mode === "generated" ? "passed" : "error");
        appendProjectMessage(
          design.project_id,
          "assistant",
          imagePayload?.mode === "generated"
            ? "The generated room image is ready and saved as the first version."
            : imagePayload?.notes?.[0] ?? "The image service is not currently available.",
        );
        await refreshSavedDesigns().catch(() => undefined);
      } catch (caught) {
        setProgress("error");
        setError(caught instanceof Error ? caught.message : "Image generation failed.");
      } finally {
        setLoading(false);
      }
      return;
    }
    if (design) {
      await reviseDesign(
        "Create a clearly different coordinated design alternative for this selected version. Keep the exact room architecture, camera, openings, built-ins, functional layout, and exact approved furniture products, but visibly restyle the palette, wall treatment, textiles, curtains, lighting treatment, artwork, plants, and decor.",
        false,
        "variation",
      );
      return;
    }
    setLoading(true);
    setError("");
    setDesign(null);
    setConceptImage(null);
    setSelectedRevisionId("");
    setProgress("planning");
    const projectId = currentProjectId;
    const firstMessage = [
      designGoal,
      `Dimensions: ${dimensionsLabel}.`,
      `Style: ${selectedStyles.join(", ")}.`,
      `Preferences: ${selectedPreferences.join(", ")}.`,
      `Photo notes: ${photoNotes.join("; ") || "no photos uploaded"}.`,
      message,
    ].join(" ");
    updateProjectChat(projectId, () => [
      newChatMessage("user", firstMessage),
      newChatMessage("assistant", "I am checking dimensions, budget, style, catalogue items, and room constraints for this project."),
    ]);
    try {
      const sessionResponse = await apiFetch("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ brief: roomBrief, user_id: homeowner.id, project_id: projectId, project_name: projectName }),
      });
      const sessionPayload = await parseResponse(sessionResponse);
      setSessionId(sessionPayload.session_id);

      setProgress("designing");
      const chatResponse = await apiFetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionPayload.session_id,
          message: firstMessage,
          max_retries: 2,
        }),
      });
      setProgress("grounding");
      const chatPayload = await parseResponse(chatResponse);
      setProgress("checking");
      setDesign(chatPayload.design);
      await refreshSavedDesigns().catch(() => undefined);
      setProgress(chatPayload.design?.status === "failed" ? "failed" : "passed");
      appendProjectMessage(projectId, "assistant", "The sourceable plan is ready. I am generating the final room image now.");
      const imagePayload = await generateConcept(chatPayload.design);
      appendProjectMessage(projectId, "assistant", imagePayload?.mode === "generated" ? "The generated room image is ready." : "The image prompt is ready, but the backend image key is not configured.");
      setActiveTab(vastuEnabled ? "vastu" : "shopping");
      await refreshSavedDesigns();
    } catch (caught) {
      if (caught instanceof ApiRequestError && caught.design) {
        setDesign(caught.design);
        await refreshSavedDesigns().catch(() => undefined);
      }
      setProgress("error");
      setError(caught instanceof Error ? caught.message : "general error");
    } finally {
      setLoading(false);
    }
  }

  async function reviseDesign(
    messageOverride = "",
    refreshProducts = false,
    revisionMode: "targeted" | "variation" = "targeted",
  ) {
    if (!design) return;
    const trimmedMessage = (messageOverride || chatInput).trim();
    if (!trimmedMessage) return;
    setLoading(true);
    setError("");
    setProgress("revising");
    const baseRevisionId = selectedRevisionId;
    const projectId = design.project_id || currentProjectId;
    const normalizedRevision = trimmedMessage.toLowerCase();
    const mentionsProduct = slots.some((slot) => normalizedRevision.includes(slot.slot.category.replaceAll("_", " ")))
      || /\b(furniture|furnishings|products|catalogue|sofa|chair|table|bed|desk|rug|mirror|cabinet|shelf|lighting)\b/.test(normalizedRevision);
    const requestsChange = /\b(change|replace|swap|refresh|update|make|different|new|another)\b/.test(normalizedRevision);
    const refreshRequested = refreshProducts || (mentionsProduct && requestsChange);
    appendProjectMessage(projectId, "user", trimmedMessage);
    try {
      const response = await apiFetch(`/api/design/${design.design_id}/revise`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: trimmedMessage, max_retries: 2, refresh_products: refreshRequested }),
      });
      const payload = await parseResponse(response);
      setDesign(payload.design);
      await refreshSavedDesigns().catch(() => undefined);
      appendProjectMessage(
        projectId,
        "assistant",
        refreshRequested
          ? "I am updating the matching catalogue furniture first, then synchronizing the room image and shopping list."
          : revisionMode === "variation"
          ? "I am creating a visibly different design alternative while keeping this room's architecture and viewpoint fixed."
          : "I am applying only that revision to the current room image. The room shell and approved shopping list will stay fixed.",
      );
      const imagePayload = await generateConcept(payload.design, trimmedMessage, baseRevisionId, revisionMode);
      setProgress(payload.design?.status === "failed" ? "failed" : "passed");
      appendProjectMessage(
        projectId,
        "assistant",
        imagePayload?.mode === "generated"
          ? "The revised generated image is ready and saved as a new version."
          : imagePayload?.notes?.[0] ?? "The revision is saved, but the image service is not currently available. You can retry without losing the request.",
      );
      if (!messageOverride) setChatInput("");
      await refreshSavedDesigns();
    } catch (caught) {
      setProgress("error");
      const message = caught instanceof Error ? caught.message : "Image generation failed.";
      appendProjectMessage(projectId, "assistant", `The revised image was not generated: ${message} Your previous version is still saved and unchanged.`);
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  async function retryPendingRevision() {
    const pendingRevision = design?.last_revision_request?.trim();
    if (!design || !pendingRevision) return;
    setLoading(true);
    setError("");
    setProgress("revising");
    try {
      const imagePayload = await generateConcept(design, pendingRevision);
      setProgress(imagePayload?.mode === "generated" ? "passed" : "error");
      appendProjectMessage(
        design.project_id,
        "assistant",
        imagePayload?.mode === "generated"
          ? "The pending revision is now generated and saved as a new version."
          : imagePayload?.notes?.[0] ?? "The image service is still unavailable.",
      );
      await refreshSavedDesigns();
    } catch (caught) {
      setProgress("error");
      setError(caught instanceof Error ? caught.message : "Could not retry this image revision.");
    } finally {
      setLoading(false);
    }
  }

  async function selectAlternative(slot: GroundedSlot, item: CatalogueItem) {
    if (!design || selectingItemId) return;
    setSelectingItemId(item.item_id);
    setError("");
    try {
      const response = await apiFetch(`/api/design/${design.design_id}/select-item`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slot_id: slot.slot.slot_id, item_id: item.item_id }),
      });
      const payload = await parseResponse(response);
      setDesign(payload.design);
      updateProjectChat(payload.design.project_id, () => storedMessages(payload.design));
      appendProjectMessage(design.project_id, "assistant", "Furniture updated, fit and budget rechecked. I am refreshing the room image to match the selected item.");
      const imagePayload = await generateConcept(payload.design, `Replace only the ${slot.slot.category} with the newly selected exact catalogue item ${item.title}. Preserve the room, camera, architecture, and every other selected item.`);
      appendProjectMessage(design.project_id, "assistant", imagePayload?.mode === "generated" ? "The room image now matches the updated furniture plan." : "The furniture plan is saved; image generation is waiting for the configured image key.");
      await refreshSavedDesigns();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not update this furniture item.");
    } finally {
      setSelectingItemId("");
    }
  }

  async function signOut() {
    await apiFetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    router.replace("/");
  }

  function openProfile() {
    if (!homeowner) return;
    setProfileDraft({
      name: homeowner.name,
      location: homeowner.location ?? "",
      homeType: homeowner.home_type ?? "apartment",
      preferredUnits: homeowner.preferred_units && units.includes(homeowner.preferred_units) ? homeowner.preferred_units : "ft",
    });
    setProfileError("");
    setProfileOpen(true);
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setProfileSaving(true);
    setProfileError("");
    try {
      const response = await apiFetch("/api/auth/profile", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: profileDraft.name.trim(),
          location: profileDraft.location.trim(),
          home_type: profileDraft.homeType,
          preferred_units: profileDraft.preferredUnits,
        }),
      });
      const payload = await parseResponse(response);
      setHomeowner(payload.user);
      if (!design) setUnit(payload.user.preferred_units);
      setProfileOpen(false);
    } catch (caught) {
      setProfileError(caught instanceof Error ? caught.message : "Could not update your profile.");
    } finally {
      setProfileSaving(false);
    }
  }

  function nextStep(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (step === 4) commitBudgetInput();
    if (step < wizardSteps.length - 1) setStep(step + 1);
  }

  function previousStep() {
    if (step > 0) setStep(step - 1);
  }

  function showVastuResults() {
    setActiveTab("vastu");
    window.requestAnimationFrame(() => document.getElementById("vastu-results")?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  if (authLoading) {
    return <section className="ys-app-shell ys-auth-loading" aria-live="polite">Opening your private design studio...</section>;
  }

  if (!homeowner) {
    return (
      <section className="ys-app-shell workspace-login-required">
        <h1>Sign in to open your projects</h1>
        <p>Your saved rooms and recommendations are available only inside your account.</p>
        <Link className="ys-solid-button" href="/login?next=/workspace">Go to sign in</Link>
      </section>
    );
  }

  return (
    <section className="ys-app-shell" aria-label="FormaOS design workspace">
      <div className="ys-brand-row">
        <Link className="ys-logo" href="/">
          <img className="ys-logo-image" src="/yourspace-logo.png" alt="" />
          <strong>YourSpace</strong>
        </Link>
        <div className="ys-user-mini">
          <button className="ys-profile-trigger" type="button" onClick={openProfile} aria-label="Edit homeowner profile">
            <span className="ys-user-avatar" aria-hidden="true">{homeowner.name.slice(0, 1).toUpperCase()}</span>
            <span><strong>{homeowner.name}</strong><small>{homeowner.location || homeowner.email}</small></span>
          </button>
          <button className="ys-signout-button" type="button" onClick={signOut}>Sign out</button>
        </div>
      </div>

      <div className="ys-product-layout">
        <aside className="ys-project-rail" aria-label="Your projects">
          <button className="ys-new-project" type="button" onClick={startNewProject}>+ New project</button>
          <div className="ys-project-rail-heading"><strong>Projects</strong><span>{projectCards.length}</span></div>
          <div className="ys-project-rail-list">
            {projectCards.length ? projectCards.map((savedProject) => (
              <div key={savedProject.project_id} className={`ys-project-row ${savedProject.project_id === currentProjectId ? "active" : ""}`}>
                <button className="ys-project-open" type="button" onClick={() => loadDesign(savedProject.design_id)}>
                  <img src={safePreviewPath(savedProject)} alt="" onError={(event) => { event.currentTarget.src = "/product-placeholder.svg"; }} />
                  <span><strong>{savedProject.project_name}</strong><small>{savedProject.item_count} items · {new Date(savedProject.generated_at).toLocaleDateString()}</small></span>
                </button>
                <button
                  className="ys-project-delete"
                  type="button"
                  onClick={() => deleteProject(savedProject.project_id, savedProject.project_name)}
                  disabled={deletingProjectId === savedProject.project_id}
                  aria-label={`Delete ${savedProject.project_name} chat and project`}
                  title="Delete chat"
                >
                  {deletingProjectId === savedProject.project_id ? "..." : "Delete"}
                </button>
              </div>
            )) : <p>No saved projects yet. Start with your first room.</p>}
          </div>
        </aside>

        <div className="ys-product-main">
      <div className="ys-stepper" aria-label="Design intake progress">
        {wizardSteps.map((label, index) => (
          <button key={label} type="button" disabled={index > step} className={index === step ? "active" : index < step ? "done" : ""} onClick={() => { if (index <= step) setStep(index); }}>
            <span>{index + 1}</span>
            {label}
          </button>
        ))}
      </div>

      <div className="ys-progress-markers" aria-hidden="true">
        {progressStates.map((state) => (
          <span key={state}>{state}</span>
        ))}
        <span>Versioned concept history</span>
        <span>Design workspace tabs</span>
        <span>Shopping list</span>
        <span>Empty design state</span>
      </div>

      {step < 5 ? (
        <form className="ys-wizard-card" onSubmit={nextStep}>
          {step === 0 ? (
            <section className="ys-step-layout">
              <div>
                <h1>Let's get to know your space</h1>
                <p>Upload photos and add room dimensions.</p>
                <label className="ys-upload">
                  <input type="file" accept="image/*" multiple onChange={(event) => handlePhotos(event.target.files)} />
                  <span>Upload photos</span>
                  <small>Drag and drop or click to browse</small>
                </label>
                <div className="ys-photo-strip">
                  {photos.length ? photos.map((photo, index) => (
                    <img key={`${photo.name}-${index}`} src={photo.url} alt={`Uploaded room photo ${index + 1}`} />
                  )) : (
                    <div className="ys-photo-empty">Upload photos of your actual room before generating.</div>
                  )}
                  <button type="button" onClick={() => document.querySelector<HTMLInputElement>(".ys-upload input")?.click()}>+ Add more</button>
                </div>
              </div>
              <div className="ys-form-grid">
                <strong>Room dimensions</strong>
                <label>
                  Length
                  <input value={depth} type="number" min="1" onChange={(event) => setDepth(Number(event.target.value))} />
                  <span>{unit}</span>
                </label>
                <label>
                  Width
                  <input value={width} type="number" min="1" onChange={(event) => setWidth(Number(event.target.value))} />
                  <span>{unit}</span>
                </label>
                <label>
                  Height
                  <input value={height} type="number" min="1" onChange={(event) => setHeight(Number(event.target.value))} />
                  <span>{unit}</span>
                </label>
                <label>
                  Units
                  <select value={unit} onChange={(event) => setUnit(event.target.value as Unit)}>
                    {units.map((option) => (
                      <option key={option} value={option}>{option}</option>
                    ))}
                  </select>
                </label>
                <label className="wide">
                  Room type
                  <select value={roomType} onChange={(event) => setRoomType(event.target.value)}>
                    <option value="living_room">Living room</option>
                    <option value="bedroom">Master bedroom</option>
                    <option value="study">Home office</option>
                  </select>
                </label>
              </div>
            </section>
          ) : null}

          {step === 1 ? (
            <section>
              <h1>What's your style?</h1>
              <p>Choose up to 3 styles you love.</p>
              <div className="ys-style-grid">
                {styleCards.map((styleCard) => (
                  <button key={styleCard.label} type="button" className={selectedStyles.includes(styleCard.label) ? "selected" : ""} onClick={() => toggleOption(styleCard.label, selectedStyles, setSelectedStyles, 3)}>
                    <img src={styleCard.imageSrc} alt={`${styleCard.label} interior style`} />
                    <span>{styleCard.label}</span>
                    <small>{styleCard.cues}</small>
                    <span className="ys-style-swatches" aria-label={`${styleCard.label} colour palette`}>
                      {styleCard.palette.map((colour) => <i key={colour.hex} style={{ backgroundColor: colour.hex }} title={`${colour.name} ${colour.hex}`} />)}
                    </span>
                  </button>
                ))}
              </div>
              <div className="ys-selected-palette" aria-label="Selected design colour direction">
                <strong>{leadStylePalette?.label ?? "Selected"} lead palette</strong>
                <div>
                  {(leadStylePalette?.palette ?? []).map((colour, index) => (
                    <span key={`${colour.hex}-${index}`}><i style={{ backgroundColor: colour.hex }} /><small>{colour.name}</small></span>
                  ))}
                </div>
              </div>
            </section>
          ) : null}

          {step === 2 ? (
            <section>
              <h1>What matters most to you?</h1>
              <p>Select your preferences.</p>
              <div className="ys-pref-grid">
                {preferenceOptions.map((option) => (
                  <button key={option} type="button" className={selectedPreferences.includes(option) ? "selected" : ""} onClick={() => toggleOption(option, selectedPreferences, setSelectedPreferences)}>
                    <span>{option.slice(0, 2)}</span>
                    {option}
                  </button>
                ))}
              </div>
            </section>
          ) : null}

          {step === 3 ? (
            <section className="ys-vastu-step">
              <div className="ys-vastu-step-heading">
                <div><span className="eyebrow">Placement intelligence</span><h1>Design with Vastu guidance?</h1><p>Set the room orientation used for furniture placement and the final Vastu score.</p></div>
                <label className="ys-vastu-toggle">
                  <input type="checkbox" checked={vastuEnabled} onChange={(event) => setVastuEnabled(event.target.checked)} />
                  <span aria-hidden="true" />
                  <strong>{vastuEnabled ? "Vastu on" : "Vastu off"}</strong>
                </label>
              </div>
              <div className={vastuEnabled ? "ys-vastu-config" : "ys-vastu-config disabled"}>
                <div>
                  <strong>Main door direction</strong>
                  <p>Select where the room entrance sits.</p>
                  <div className="ys-direction-grid" aria-label="Main door direction">
                    {["NW", "N", "NE", "W", "C", "E", "SW", "S", "SE"].map((direction) => (
                      <button key={direction} type="button" disabled={!vastuEnabled || direction === "C"} className={mainDoor === direction ? "selected" : ""} onClick={() => setMainDoor(direction as Direction)}>{direction === "C" ? "Center" : direction}</button>
                    ))}
                  </div>
                </div>
                <div className="ys-vastu-principles">
                  <strong>Placement priorities</strong>
                  <div><span>NE</span><p><b>Light & calm</b>Natural light, plants, and open visual space.</p></div>
                  <div><span>SW</span><p><b>Stability</b>Heavy storage and anchored furniture.</p></div>
                  <div><span>C</span><p><b>Clear center</b>Unblocked circulation through the room.</p></div>
                  <label>North reference<select disabled={!vastuEnabled} value={compass} onChange={(event) => setCompass(event.target.value as Direction)}>{directions.filter((direction) => direction !== "C").map((direction) => <option key={direction} value={direction}>{direction}</option>)}</select></label>
                </div>
              </div>
            </section>
          ) : null}

          {step === 4 ? (
            <section className="ys-budget-step">
              <h1>What's your budget?</h1>
              <p>Set your comfortable budget range.</p>
              <label className="ys-budget-input-wrap">
                <span>INR</span>
                <input
                  type="number"
                  inputMode="numeric"
                  min={MIN_BUDGET}
                  max={MAX_BUDGET}
                  step={1000}
                  value={budgetInput}
                  onChange={(event) => updateBudgetInput(event.target.value)}
                  onBlur={commitBudgetInput}
                  aria-label="Interior design budget in Indian rupees"
                />
              </label>
              <div className="ys-budget-value" aria-live="polite">{formatCurrency(budget)}</div>
              <input
                type="range"
                min={MIN_BUDGET}
                max={MAX_BUDGET}
                step={BUDGET_STEP}
                value={budget}
                onChange={(event) => updateBudgetFromSlider(Number(event.target.value))}
                aria-label="Budget slider"
              />
              <div className="ys-range-labels">
                <span>{formatCurrency(MIN_BUDGET)}</span>
                <span>{formatCurrency(MAX_BUDGET)}</span>
              </div>
              <p className="ys-hint">We'll recommend furniture items that fit your budget.</p>
            </section>
          ) : null}

          <div className="ys-wizard-actions">
            {step > 0 ? <button className="secondary-button" type="button" onClick={previousStep}>Back</button> : <span />}
            <button className="primary-button" type="submit">Next</button>
          </div>
        </form>
      ) : (
        <section className="ys-review-grid">
          <div className="ys-review-card">
            <h1>Almost there!</h1>
            <p>Review your details before we design.</p>
            <dl>
              <div><dt>Room type</dt><dd>{roomType.replace("_", " ")}</dd></div>
              <div><dt>Dimensions</dt><dd>{dimensionsLabel}</dd></div>
              <div><dt>Style</dt><dd>{selectedStyles.join(", ")}</dd></div>
              <div className="ys-review-palette"><dt>Palette</dt><dd>{stylePalettes[0]?.palette.map((colour) => <i key={colour.hex} style={{ backgroundColor: colour.hex }} title={`${colour.name} ${colour.hex}`} />)}</dd></div>
              <div><dt>Preferences</dt><dd>{selectedPreferences.join(", ")}</dd></div>
              <div><dt>Vastu</dt><dd>{vastuEnabled ? `Enabled · door ${mainDoor} · compass ${compass}` : "Not requested"}</dd></div>
              <div><dt>Budget</dt><dd>{formatCurrency(budget)}</dd></div>
            </dl>
            <div className="ys-wizard-actions">
              <button className="secondary-button" type="button" onClick={previousStep}>Back</button>
              <button className="primary-button" type="button" onClick={startDesign} disabled={loading}>
                {loading ? "Generating..." : design ? displayedConcept?.image_data_url ? "Regenerate selected version" : "Generate room image" : "Generate designs"}
              </button>
            </div>
            {error ? <p className="workspace-error" role="alert">{error}</p> : null}
          </div>

          <div className="ys-chat-card" aria-label="Project chat">
            <div className="ys-projects-heading">
              <h2>Project Chat</h2>
              <span>{projectName}</span>
            </div>
            <div className="ys-chat-thread">
              {activeProjectMessages.length ? activeProjectMessages.map((chatMessage) => (
                <article key={chatMessage.id} className={chatMessage.role === "user" ? "ys-chat-message user" : "ys-chat-message assistant"}>
                  <span>{chatMessage.role === "user" ? "You" : "YourSpace"}</span>
                  <p>{chatMessage.text}</p>
                </article>
              )) : (
                <div className="ys-chat-empty">This project has its own chat. Generate a design or load a saved project to start.</div>
              )}
              {conceptLoading ? (
                <article className="ys-chat-message assistant ys-chat-generating" aria-label="Image generation in progress">
                  <span>YourSpace</span>
                  <div className="ys-chat-generation-preview" aria-hidden="true"><i /><i /><i /></div>
                  <p>{progress === "revising" ? "Applying your revision while preserving this room and its approved items." : "Generating the room design from your photo and approved shopping list."}</p>
                </article>
              ) : null}
            </div>
          </div>

          <div className="ys-results-card">
            <div className="workspace-toolbar">
              <div>
                <span className="eyebrow">Checked design</span>
                <h1>{design ? "Generated concept" : "Waiting for design"}</h1>
              </div>
              <div className="workspace-facts" aria-label="Core plan facts">
                <span>{widthCm} x {depthCm} cm</span>
                <span>{design ? formatCurrency(backendTotal) : "No total"} total</span>
                <span>{budgetStatus} budget</span>
              </div>
            </div>

            {!design ? (
              <div className="workspace-empty-state" aria-label="Empty design state">Your generated concept, selected items, checks, and saved version appear here.</div>
            ) : null}

            <section className="concept-panel" aria-label="Generated interior concept">
              <div className="concept-heading">
                <div>
                  <span className="eyebrow">Final visual concept</span>
                  <h2>{conceptLoading ? "Generating image" : displayedConcept?.mode === "generated" ? selectedRevision?.label ?? "Generated image" : "Image generation brief"}</h2>
                </div>
                <span className={displayedConcept?.mode === "generated" && !conceptLoading ? "status hard" : "status soft"}>{conceptLoading ? "Working" : displayedConcept?.mode === "generated" ? "Image ready" : "Prompt ready"}</span>
              </div>
              {conceptHistory.length ? (
                <div className="concept-version-toolbar" aria-label="Design version navigation">
                  <button type="button" disabled={selectedRevisionIndex <= 0} onClick={() => setSelectedRevisionId(conceptHistory[selectedRevisionIndex - 1]?.revision_id ?? "")}>Previous</button>
                  <span><strong>{selectedRevision?.label}</strong><small>Version {selectedRevisionIndex + 1} of {conceptHistory.length}</small></span>
                  <button type="button" disabled={selectedRevisionIndex < 0 || selectedRevisionIndex >= conceptHistory.length - 1} onClick={() => setSelectedRevisionId(conceptHistory[selectedRevisionIndex + 1]?.revision_id ?? "")}>Next</button>
                </div>
              ) : null}
              {conceptLoading ? (
                <div className="concept-loading-card" aria-label="Image generation in progress">
                  <div className="concept-loading-frame">
                    <span />
                    <span />
                    <span />
                  </div>
                  <p>Generating your room image</p>
                </div>
              ) : null}
              {!conceptLoading && displayedConcept?.image_data_url && comparisonImage ? (
                <div className="concept-comparison" aria-label="Compare the selected design with its previous version">
                  <BeforeAfterSlider
                    beforeSrc={comparisonImage}
                    afterSrc={displayedConcept.image_data_url}
                    beforeAlt={selectedRevisionIndex > 0 ? "Previous generated design version" : "Uploaded room before redesign"}
                    afterAlt="Selected generated design version"
                    className="concept-before-after"
                  />
                </div>
              ) : null}
              {!conceptLoading && displayedConcept?.image_data_url && !comparisonImage ? <img className="concept-image" src={displayedConcept.image_data_url} alt="Generated interior design concept" /> : null}
              {!conceptLoading && displayedConcept && !displayedConcept.image_data_url ? <pre>{displayedConcept.image_prompt}</pre> : null}
              {design ? (
                <div className="design-intelligence-strip" aria-label="Design summary">
                  <div className="design-palette-summary">
                    <span>Colour direction</span>
                    <strong>{selectedStyles.slice(0, 2).join(" + ")}</strong>
                    <div>{stylePalettes[0]?.palette.map((colour) => <i key={colour.hex} style={{ backgroundColor: colour.hex }} title={`${colour.name} ${colour.hex}`} />)}</div>
                  </div>
                  <button type="button" className={vastuEnabled ? "vastu-summary active" : "vastu-summary"} onClick={showVastuResults} disabled={!vastuEnabled}>
                    <span>Vastu score</span><strong>{vastuEnabled ? `${vastuScore}/100` : "Off"}</strong><small>{vastuEnabled ? "View placement plan" : "Not requested"}</small>
                  </button>
                  <div><span>Sourceable plan</span><strong>{displayedSlots.length} items</strong><small>{formatCurrency(backendTotal)}</small></div>
                </div>
              ) : null}
              {conceptHistory.length ? (
                <section className="concept-revisions" aria-label="All generated design revisions">
                  <div className="concept-revisions-heading">
                    <div><span className="eyebrow">Saved versions</span><h3>Design revisions</h3></div>
                    <span>{conceptHistory.length} {conceptHistory.length === 1 ? "version" : "versions"}</span>
                  </div>
                  <div className="concept-revision-list">
                    {conceptHistory.map((revision) => (
                      <button
                        key={revision.revision_id}
                        type="button"
                        className={revision.revision_id === selectedRevision?.revision_id ? "active" : ""}
                        onClick={() => setSelectedRevisionId(revision.revision_id)}
                      >
                        <img src={revision.image_data_url ?? "/product-placeholder.svg"} alt="" />
                        <span><strong>{revision.label}</strong><small>{revision.revision_text}</small></span>
                      </button>
                    ))}
                  </div>
                  <div className="revision-product-set">
                    <div><strong>Furniture saved with this version</strong><span>{displayedProducts.length} catalogue items</span></div>
                    <div className="revision-product-list">
                      {displayedProducts.map((item) => (
                        <article key={`${selectedRevision?.revision_id ?? "current"}-${item.item_id}`}>
                          <img src={safeImagePath(item as CatalogueItem)} alt={item.title} onError={(event) => { event.currentTarget.src = "/product-placeholder.svg"; }} />
                          <span><small>{item.category}</small><strong>{item.title}</strong><code>{item.item_id}</code></span>
                        </article>
                      ))}
                    </div>
                  </div>
                </section>
              ) : null}
              {design ? (
                <form className="studio-action-row" onSubmit={(event) => { event.preventDefault(); reviseDesign(); }}>
                  <input value={chatInput} onChange={(event) => setChatInput(event.target.value)} aria-label="Revision message" placeholder="Describe one change to this design" />
                  <button className="primary-button" type="submit" disabled={loading || conceptLoading || !chatInput.trim()}>{progress === "revising" || conceptLoading ? "Revising..." : "Send revision"}</button>
                  {design.last_revision_request ? <button className="secondary-button" type="button" disabled={loading || conceptLoading} onClick={retryPendingRevision}>Retry pending image</button> : null}
                  <a
                    className="secondary-button"
                    href={`/design/${design.design_id}/brief${selectedRevision?.revision_id ? `?revision_id=${encodeURIComponent(selectedRevision.revision_id)}` : ""}`}
                  >
                    Export selected version
                  </a>
                  <button className="secondary-button" type="button" disabled={loading || conceptLoading} onClick={() => reviseDesign("Refresh every furniture match for this room, then synchronize the image with the corrected catalogue list. Keep the room architecture and camera angle fixed, but make each visible furniture item match its supplied product reference.", true)}>Refresh furniture & image</button>
                </form>
              ) : null}
            </section>

            <div className="workspace-tabs" role="tablist" aria-label="Design workspace tabs">
              {tabs.map((tab) => (
                <button key={tab} disabled={!design} className={activeTab === tab ? "workspace-tab active" : "workspace-tab"} type="button" onClick={() => { if (design) setActiveTab(tab); }}>
                  {tab === "vastu" ? `Vastu & checks${vastuEnabled ? ` · ${vastuScore}` : ""}` : "Shopping & materials"}
                </button>
              ))}
            </div>

            {activeTab === "vastu" ? (
              <div className="design-checks-panel" id="vastu-results" aria-label="Vastu and project design checks">
                <div className="design-checks-heading">
                  <div><span className="eyebrow">Practical review</span><h2>What YourSpace checked</h2></div>
                  <span className={design?.critic_verdict.passed ? "status hard" : "status soft"}>{design?.critic_verdict.passed ? "Ready to use" : "Needs attention"}</span>
                </div>
                  <div className="design-check-grid">
                    {[
                      { label: "Room fit", status: design?.critic_verdict.fit.status, passLabel: "Fits room", failLabel: "Review size", warnLabel: "Check fit", note: design?.critic_verdict.fit.notes.join(" ") || `${slots.length} selected items stay within their approved room footprints.` },
                      { label: "Budget", status: design?.critic_verdict.budget.status, passLabel: "On budget", failLabel: "Over budget", warnLabel: "Review", note: design?.critic_verdict.budget.notes.join(" ") || `${formatCurrency(backendTotal)} total stays within your ${formatCurrency(budget)} budget.` },
                      { label: "Real products", status: design?.critic_verdict.sourceability.status, passLabel: "Verified", failLabel: "Missing item", warnLabel: "Review", note: design?.critic_verdict.sourceability.notes.join(" ") || "Every selected furniture item has a catalogue ID, dimensions, price, and product image." },
                      { label: "Vastu guidance", status: design?.critic_verdict.vastu.status, passLabel: "Aligned", failLabel: "Review", warnLabel: "Advisory", skippedLabel: "Not requested", note: design?.critic_verdict.vastu.notes.join(" ") || (vastuEnabled ? "The selected placement plan has no blocking Vastu concerns." : "Vastu was not requested for this project.") },
                    ].map((check) => (
                      <article key={check.label}>
                        <span className={check.status === "pass" ? "check-dot pass" : check.status === "fail" ? "check-dot fail" : "check-dot warn"} aria-hidden="true" />
                        <div><strong>{check.label}</strong><p>{check.note}</p></div>
                        <b>{check.status === "pass" ? check.passLabel : check.status === "fail" ? check.failLabel : check.status === "warn" ? check.warnLabel : check.status === "skipped" ? check.skippedLabel ?? "Not required" : "Waiting"}</b>
                      </article>
                    ))}
                </div>
                {vastuEnabled ? (
                  <div className="workspace-vastu-panel">
                    <ZoneGrid items={zoneItems} />
                    <aside className="vastu-notes">
                      <div className="score-card"><strong>{vastuScore}</strong><p>Vastu placement score</p></div>
                      {ruleResults.slice(0, 4).map((rule) => (
                        <article className="workspace-rule-card" key={`${rule.rule_id}-${rule.item_id}`}><strong>{rule.status === "pass" ? "Placed well" : "Review placement"}</strong><p>{rule.note}</p><p>{rule.rationale}</p></article>
                      ))}
                    </aside>
                  </div>
                ) : null}
              </div>
            ) : null}

            {activeTab === "shopping" ? (
              <div className="workspace-shopping-panel" aria-label="Shopping list">
                <div className="budget-panel workspace-budget">
                  <div><span>Total</span><strong>{formatCurrency(backendTotal)}</strong></div>
                  <div><span>Budget</span><strong>{formatCurrency(budget)}</strong></div>
                  <div className="budget-bar" aria-label="Budget bar status"><span style={{ width: `${budgetPercent}%` }} /></div>
                  <p>{budgetStatus} budget. Displayed total {exactTotal ? "matches" : "does not match"} backend item sum.</p>
                </div>
                <div className="shopping-list">
                  {displayedSlots.map((slot) => {
                    const item = slot.selected_item as CatalogueItem;
                    const revisionProduct = item as RevisionProduct;
                    const vastuBadge = design?.critic_verdict.vastu_result?.item_results.find((result) => result.item_id === item.item_id)?.badge;
                    const imageMatchLabel = revisionProduct.imageMatch === "closest_catalogue_match"
                      ? "closest visual match"
                      : revisionProduct.imageMatch === "not_visible"
                        ? "planned · not clearly visible"
                        : "selected and fit checked";
                    return (
                      <article className="product-row shopping-product" key={`shopping-${item.item_id}`}>
                        <img className="shopping-product-image" src={safeImagePath(item)} alt={item.title} onError={(event) => { event.currentTarget.src = "/product-placeholder.svg"; }} />
                        <div className="shopping-product-copy">
                          <div className="shopping-product-heading">
                            <div><span className="product-category">{slot.slot.category}</span><h3>{item.title}</h3></div>
                            <strong>{formatCurrency(item.price_inr)}</strong>
                          </div>
                          <p className="shopping-item-id">Catalogue ID {item.item_id} · {imageMatchLabel}</p>
                          <dl className="shopping-product-specs">
                            <div><dt>Dimensions</dt><dd>{item.width_cm} × {item.depth_cm} × {item.height_cm ?? "n/a"} cm</dd></div>
                            <div><dt>Material</dt><dd>{item.material ?? "Not specified"}</dd></div>
                            <div><dt>Colour</dt><dd>{item.color ?? "Not specified"}</dd></div>
                            <div><dt>Placement</dt><dd>Zone {slot.placement_zone}{vastuEnabled ? ` · ${vastuBadge ?? design?.critic_verdict.vastu.status}` : ""}</dd></div>
                          </dl>
                          <p className="shopping-product-reason">{slot.slot.style_text || `${selectedStyles.join(" and ")} styling`} · approved for a maximum {slot.constraints?.max_width_cm ?? item.width_cm} × {slot.constraints?.max_depth_cm ?? item.depth_cm} cm footprint.</p>
                          <div className="shopping-product-actions">
                            <a href={productSearchUrl(item)} target="_blank" rel="noreferrer">Find similar product</a>
                            <span>{revisionProduct.imageMatch === "closest_catalogue_match"
                              ? "Selected by comparing this catalogue image with the visible object in the generated room."
                              : revisionProduct.imageMatch === "not_visible"
                                ? "This planned item remains in the room specification but cannot be verified in this render."
                                : "This catalogue selection was supplied to the image model as a product reference."}</span>
                          </div>
                          {slot.alternatives.length ? (
                            <div className="shopping-alternatives">
                              <span>Approved alternatives</span>
                              <div>
                                {slot.alternatives.slice(0, 3).map((alternative) => (
                                  <button key={alternative.item_id} type="button" disabled={Boolean(selectingItemId)} onClick={() => selectAlternative(slot, alternative)}>
                                    <img src={safeImagePath(alternative)} alt="" onError={(event) => { event.currentTarget.src = "/product-placeholder.svg"; }} />
                                    <span>{alternative.title}</span>
                                    <strong>{selectingItemId === alternative.item_id ? "Updating..." : "Use this"}</strong>
                                  </button>
                                ))}
                              </div>
                            </div>
                          ) : null}
                        </div>
                      </article>
                    );
                  })}
                </div>
                <section className="finish-schedule" aria-label="Complete materials and decor schedule">
                  <div>
                    <span className="eyebrow">Complete material list</span>
                    <h2>Finishes, styling, and decor</h2>
                    {finishSchedule.some((item) => item.colourSource === "generated_image") ? (
                      <p className="finish-schedule-source">Colours sampled from {selectedRevision?.label ?? "the selected design"}</p>
                    ) : null}
                  </div>
                  <div className="finish-schedule-grid">
                    {finishSchedule.map((item) => {
                      const visualCategory = item.category === "Paintings & wall art" || item.category === "Wall art" || item.category === "Bedding";
                      const visualLabel = item.category === "Bedding" ? "bedding" : "painting";
                      return (
                        <article key={item.category}>
                          <div className="finish-heading"><span>{item.category}</span><i style={{ backgroundColor: item.hex }} aria-label={`${item.colourName} ${item.hex}`} /></div>
                          <h3>{item.recommendation}</h3>
                          {visualCategory && displayedConcept?.image_data_url ? (
                            <details className="finish-visual-disclosure">
                              <summary>View {visualLabel} in design</summary>
                              <DesignElementPreview imageSrc={displayedConcept.image_data_url} crop={item.imageCrop} alt={`${item.category} shown in the selected design`} />
                            </details>
                          ) : null}
                          <p className="finish-colour"><b>{item.colourName}</b><code>{item.hex}</code></p>
                          <strong>{item.quantity}</strong>
                          <p>{item.note}</p>
                          <a href={item.link} target="_blank" rel="noreferrer">{item.linkLabel}</a>
                        </article>
                      );
                    })}
                  </div>
                </section>
              </div>
            ) : null}
          </div>
        </section>
      )}
        </div>
      </div>
      {profileOpen ? (
        <div className="ys-profile-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setProfileOpen(false); }}>
          <section className="ys-profile-dialog" role="dialog" aria-modal="true" aria-labelledby="profile-title">
            <div className="ys-profile-heading">
              <div><span className="eyebrow">Homeowner account</span><h2 id="profile-title">Edit profile</h2></div>
              <button type="button" onClick={() => setProfileOpen(false)} aria-label="Close profile">×</button>
            </div>
            <form onSubmit={saveProfile}>
              <label>Full name<input required minLength={2} maxLength={80} value={profileDraft.name} onChange={(event) => setProfileDraft((current) => ({ ...current, name: event.target.value }))} /></label>
              <label>Email address<input type="email" value={homeowner.email} disabled aria-describedby="profile-email-note" /></label>
              <small id="profile-email-note">Your email remains the sign-in identifier.</small>
              <label>Location<input maxLength={120} value={profileDraft.location} onChange={(event) => setProfileDraft((current) => ({ ...current, location: event.target.value }))} placeholder="City, state or region" /></label>
              <label>Home type<select value={profileDraft.homeType} onChange={(event) => setProfileDraft((current) => ({ ...current, homeType: event.target.value }))}><option value="apartment">Apartment</option><option value="house">House</option><option value="condo">Condo</option><option value="townhouse">Townhouse</option><option value="other">Other</option></select></label>
              <fieldset>
                <legend>Preferred measurements</legend>
                <div className="ys-profile-units">
                  {units.map((option) => <label key={option} className={profileDraft.preferredUnits === option ? "selected" : ""}><input type="radio" name="preferred-units" value={option} checked={profileDraft.preferredUnits === option} onChange={() => setProfileDraft((current) => ({ ...current, preferredUnits: option }))} />{option}</label>)}
                </div>
              </fieldset>
              {profileError ? <p className="workspace-error" role="alert">{profileError}</p> : null}
              <div className="ys-profile-actions"><button className="secondary-button" type="button" onClick={() => setProfileOpen(false)}>Cancel</button><button className="primary-button" type="submit" disabled={profileSaving}>{profileSaving ? "Saving..." : "Save profile"}</button></div>
            </form>
          </section>
        </div>
      ) : null}
    </section>
  );
}
